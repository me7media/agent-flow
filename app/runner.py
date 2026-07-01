from __future__ import annotations

import os
import re
import time
import json
from pathlib import PurePosixPath
from datetime import datetime, timezone
from typing import Any, Callable

from .iot import IoTContextBuilder
from .iot_runtime import execute_iot_action
from .llm import ProviderConfigurationError, call_llm
from .settings_service import agent_execution_config
from .workspace import git_info, read_text_file, scan_folder, write_text_file

EventHandler = Callable[[dict[str, Any]], Any]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps_safe(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _agent_context(agent: dict[str, Any], skills: list[dict[str, Any]], mcps: list[dict[str, Any]]) -> dict[str, Any]:
    agent_skills = [skill for skill in skills if skill.get("id") in (agent.get("skills") or [])]
    agent_mcps = [mcp for mcp in mcps if mcp.get("id") in (agent.get("mcps") or [])]
    return {
        "skillIds": [skill.get("id") for skill in agent_skills],
        "skillsText": "\n".join(f"- {skill.get('name')}: {skill.get('description')}" for skill in agent_skills) or "- No skills",
        "mcpsText": "\n".join(
            f"- {mcp.get('name')}: {mcp.get('endpoint') or ''} - {mcp.get('description')}" for mcp in agent_mcps
        )
        or "- No MCP connectors",
    }


def _has_any(agent: dict[str, Any], ids: list[str]) -> bool:
    return any(skill_id in ids for skill_id in (agent.get("skills") or []))


def _should_scan(agent: dict[str, Any]) -> bool:
    return _has_any(
        agent,
        ["folder_scan", "file_read", "developer", "coder", "file_manager", "git_status", "codebase_map", "repo_indexer", "dependency_audit", "patch_writer", "terminal_plan"],
    )


def _has_git(agent: dict[str, Any]) -> bool:
    return _has_any(agent, ["git_status", "git_patch", "git_commit_plan", "release_notes"]) or "git-mcp" in (agent.get("mcps") or [])


def _can_write_artifact(agent: dict[str, Any]) -> bool:
    return _has_any(
        agent,
        ["developer", "coder", "file_manager", "file_write", "docs", "git_patch", "code_generation", "patch_writer", "qa", "security", "summary", "code_review", "folder_scan"],
    )


def _can_write_source_files(agent: dict[str, Any]) -> bool:
    return _has_any(agent, ["developer", "coder", "file_manager", "file_write", "git_patch", "code_generation", "patch_writer"])


def _can_write_test_files(agent: dict[str, Any]) -> bool:
    return _can_write_source_files(agent) or _has_any(agent, ["qa", "tester", "test_runner", "test_runner_plan"])


def _can_write_doc_files(agent: dict[str, Any]) -> bool:
    return _can_write_source_files(agent) or _has_any(agent, ["docs", "writer", "release_notes"])


def _is_test_path(path: str) -> bool:
    value = path.lower()
    name = PurePosixPath(value).name
    return value.startswith("tests/") or "/tests/" in value or name.startswith("test_") or name.endswith(("_test.py", ".test.js", ".test.mjs", ".spec.js", ".spec.ts"))


def _is_doc_path(path: str) -> bool:
    value = path.lower()
    return value == "readme.md" or value.startswith("docs/") or value.endswith((".md", ".mdx", ".rst"))


def _file_block_write_reason(agent: dict[str, Any], path: str) -> str | None:
    if _can_write_source_files(agent):
        return None
    if _is_test_path(path) and _can_write_test_files(agent):
        return None
    if _is_doc_path(path) and _can_write_doc_files(agent):
        return None
    return (
        "agent is not allowed to write this file type; source/config writes require developer/file_write skills, "
        "QA may write tests, and docs agents may write Markdown/docs"
    )


def _safe_name(text: str | None) -> str:
    value = re.sub(r"[^a-z0-9а-яіїєґ]+", "-", str(text or "agent").lower(), flags=re.IGNORECASE)
    return value.strip("-")[:60] or "agent"


def _clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = fallback
    return max(minimum, min(numeric, maximum))


def _normalize_loop_groups(loop_groups: list[dict[str, Any]] | None, flow_length: int) -> list[dict[str, Any]]:
    groups = []
    for group in loop_groups or []:
        normalized = dict(group)
        normalized["start"] = max(0, int(group.get("start", 0) or 0))
        normalized["end"] = min(flow_length - 1, int(group.get("end", 0) or 0))
        normalized["loops"] = _clamp_int(group.get("loops", 2), 2, 20, 2)
        if normalized["start"] < normalized["end"] < flow_length:
            groups.append(normalized)
    return sorted(groups, key=lambda item: (item["start"], -item["end"]))


def _extract_file_blocks(output: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    text = str(output or "")
    for match in re.finditer(r'```file\s+path=["\']([^"\']+)["\']\n([\s\S]*?)```', text):
        blocks.append({"path": match.group(1).strip(), "content": match.group(2).removesuffix("\n")})
    for match in re.finditer(r"FILE:\s*([^\n]+)\n```(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)```", text):
        blocks.append({"path": match.group(1).strip(), "content": match.group(2).removesuffix("\n")})
    return [
        block
        for block in blocks
        if block["path"] and ".." not in block["path"] and not block["path"].startswith("/") and not block["path"].startswith("~")
    ]


async def _emit(on_event: EventHandler | None, event: dict[str, Any]) -> None:
    if not on_event:
        return
    result = on_event(event)
    if hasattr(result, "__await__"):
        await result


def _should_write_directly(runtime_settings: dict[str, Any] | None) -> bool:
    execution = agent_execution_config(runtime_settings)
    mode = str(execution.get("fileWriteMode") or "").lower()
    if mode:
        return mode == "direct"
    return (os.getenv("AGENT_ALLOW_DIRECT_FILE_WRITES") or "").lower() == "true"


def _max_file_blocks(runtime_settings: dict[str, Any] | None) -> int:
    execution = agent_execution_config(runtime_settings)
    return _clamp_int(execution.get("maxFileBlocks", 20), 1, 100, 20)


async def _execute_step_iot_actions(
    step: dict[str, Any],
    agent: dict[str, Any],
    runtime_settings: dict[str, Any] | None,
    on_event: EventHandler | None,
) -> list[dict[str, Any]]:
    command = str(step.get("iotCommand") or "").strip()
    action_ids = step.get("iotActionIds") or agent.get("iotActionIds") or []
    if not command or not action_ids:
        return []
    results = []
    for action_id in action_ids:
        await _emit(on_event, {"type": "tool", "agentName": agent.get("name"), "tool": "iot_action", "message": f"Executing IoT action {action_id}:{command}"})
        result = await execute_iot_action(
            str(action_id),
            command,
            runtime_settings,
            approved=bool(step.get("iotApproved")),
            dry_run=step.get("iotDryRun") if isinstance(step.get("iotDryRun"), bool) else None,
        )
        results.append(result)
        await _emit(
            on_event,
            {
                "type": "iot_action",
                "agentName": agent.get("name"),
                "actionId": action_id,
                "command": command,
                "result": result,
                "message": result.get("message") or f"IoT action {action_id}:{command} finished.",
            },
        )
    return results


async def _write_generated_file_blocks(
    agent: dict[str, Any],
    workspace_root: str,
    output: str,
    runtime_settings: dict[str, Any] | None,
    on_event: EventHandler | None,
) -> list[str]:
    blocks = _extract_file_blocks(output)
    if not workspace_root or not blocks:
        return []
    direct_writes = _should_write_directly(runtime_settings)
    written: list[str] = []
    for block in blocks[: _max_file_blocks(runtime_settings)]:
        reason = _file_block_write_reason(agent, block["path"])
        if reason:
            await _emit(on_event, {"type": "warning", "agentName": agent.get("name"), "message": f"Skipped file block {block['path']}: {reason}"})
            continue
        target_path = block["path"] if direct_writes else f"agent-flow-output/generated/{_safe_name(agent.get('name'))}/{block['path']}"
        try:
            path = write_text_file(workspace_root, target_path, block["content"])
        except Exception as exc:
            await _emit(on_event, {"type": "warning", "message": f"Generated file write failed: {target_path}: {exc}"})
            continue
        written.append(path)
        mode = "source file written" if direct_writes else "generated file staged for review"
        await _emit(on_event, {"type": "artifact", "agentName": agent.get("name"), "path": path, "message": f"{mode}: {path}"})
    return written


async def _write_agent_artifact(
    agent: dict[str, Any],
    workspace_root: str,
    output: str,
    index: int,
    global_loop: int,
    group_loop: int | None,
    local_loop: int,
    project_context: str,
    on_event: EventHandler | None,
) -> str | None:
    if not workspace_root or not _can_write_artifact(agent):
        return None
    filename = f"{index + 1:02d}-{_safe_name(agent.get('name'))}-L{global_loop}{f'-G{group_loop}' if group_loop else ''}-S{local_loop}.md"
    path = f"agent-flow-output/{filename}"
    content = (
        f"# {agent.get('name')}\n\nGenerated at: {_iso_now()}\n\n## Agent role\n\n"
        f"{agent.get('role') or '-'}\n\n## Output\n\n{output}\n"
    )
    try:
        written_path = write_text_file(workspace_root, path, content)
        await _emit(on_event, {"type": "artifact", "agentName": agent.get("name"), "path": written_path, "message": f"Markdown artifact written: {path}"})
    except Exception as exc:
        await _emit(on_event, {"type": "warning", "message": f"Artifact write failed for {agent.get('name')}: {exc}"})
        written_path = None

    if _has_any(agent, ["folder_scan", "codebase_map"]) and project_context:
        map_path = f"agent-flow-output/codebase-map-{int(time.time() * 1000)}.md"
        try:
            write_text_file(workspace_root, map_path, f"# Codebase map\n\n{project_context}")
            await _emit(on_event, {"type": "artifact", "agentName": agent.get("name"), "path": map_path, "message": f"Codebase map written: {map_path}"})
        except Exception:
            pass
    return written_path


async def _run_single_step(
    step: dict[str, Any],
    index: int,
    agent: dict[str, Any],
    skills: list[dict[str, Any]],
    mcps: list[dict[str, Any]],
    task: str,
    workspace_root: str,
    previous_output: str,
    global_loop: int,
    group_loop: int | None,
    local_loop: int,
    runtime_settings: dict[str, Any] | None,
    on_event: EventHandler | None,
) -> dict[str, Any]:
    ctx = _agent_context(agent, skills, mcps)
    project_context = ""
    iot_context = IoTContextBuilder(runtime_settings).context_for_step(step, agent)
    agent_name = agent.get("name")

    await _emit(
        on_event,
        {
            "type": "step_start",
            "step": index + 1,
            "agentName": agent_name,
            "loop": global_loop,
            "groupLoop": group_loop,
            "stepLoop": local_loop,
            "message": f"{agent_name} started.",
        },
    )

    if workspace_root and _should_scan(agent):
        await _emit(on_event, {"type": "tool", "agentName": agent_name, "tool": "folder_scan", "message": "Scanning workspace folder..."})
        try:
            tree = scan_folder(workspace_root, ".", 5)
        except Exception as exc:
            tree = f"Folder scan failed: {exc}"
        project_context += f"\n\nWORKSPACE TREE:\n{tree}"

    if workspace_root and _has_any(agent, ["file_read", "developer", "codebase_map"]):
        for candidate in ["package.json", "pyproject.toml", "requirements.txt", "README.md", "app/main.py", "app/runner.py", "src/main.jsx", "src/App.jsx", "src/App.tsx"]:
            try:
                content = read_text_file(workspace_root, candidate)
            except Exception:
                content = None
            if content:
                project_context += f"\n\nFILE SNAPSHOT: {candidate}\n{content[:12000]}"

    if workspace_root and _has_git(agent):
        await _emit(on_event, {"type": "tool", "agentName": agent_name, "tool": "git_info", "message": "Reading safe git status/log/diff stat..."})
        try:
            git = git_info(workspace_root)
        except Exception as exc:
            git = {"status": f"Git failed: {exc}"}
        project_context += (
            f"\n\nGIT CONTEXT:\nBranch: {git.get('branch') or '-'}\nLast commit: {git.get('lastCommit') or '-'}\n"
            f"Status:\n{git.get('status') or 'clean'}\nDiff stat:\n{git.get('diff') or '-'}"
        )

    if step.get("iotCommand") and step.get("iotToolOnly", True):
        started_at = _iso_now()
        results = await _execute_step_iot_actions(step, agent, runtime_settings, on_event)
        output = json_dumps_safe({"iotCommand": step.get("iotCommand"), "iotResults": results})
        log = {
            "step": index + 1,
            "loop": global_loop,
            "groupLoop": group_loop,
            "stepLoop": local_loop,
            "agentId": agent.get("id"),
            "agentName": agent_name,
            "startedAt": started_at,
            "finishedAt": _iso_now(),
            "artifactPath": None,
            "generatedFiles": [],
            "iotSourceIds": step.get("iotSourceIds") or agent.get("iotSourceIds") or [],
            "iotActionIds": step.get("iotActionIds") or agent.get("iotActionIds") or [],
            "iotResults": results,
            "output": output,
            "error": next((item.get("message") or "iot_action_failed" for item in results if not item.get("ok")), None),
        }
        await _emit(on_event, {"type": "step_done", "log": log, "message": f"{agent_name} finished IoT command."})
        return log

    incoming_output = "" if step.get("dependsOnPrevious") is False else previous_output
    direct_writes = _should_write_directly(runtime_settings)
    write_mode = (
        "DIRECT WRITE MODE IS ENABLED FROM RUNTIME SETTINGS. When code changes are required, output complete file blocks using real project-relative paths such as app/services/example.py, src/components/Example.jsx, tests/test_example.py or nested folders that should be created. The backend will write these files directly."
        if direct_writes
        else "DIRECT WRITE MODE IS SET TO REVIEW/STAGING. Still output complete file blocks with the intended real project-relative paths. The backend will stage them under agent-flow-output/generated/<agent>/ for human review instead of overwriting source files."
    )
    
    # Fetch live IoT source payloads during flow execution
    source_ids = step.get("iotSourceIds") or agent.get("iotSourceIds") or []
    live_source_data = []
    image_path = None
    
    if source_ids:
        from .iot_runtime import read_iot_source
        for source_id in source_ids:
            try:
                await _emit(on_event, {"type": "tool", "agentName": agent_name, "tool": "iot_read", "message": f"Reading IoT source {source_id}..."})
                reading = await read_iot_source(str(source_id), runtime_settings)
                if reading.get("ok"):
                    payload = reading.get("payload")
                    live_source_data.append(
                        f"Live reading for source '{source_id}':\n"
                        f"Status: {reading.get('status')}\n"
                        f"Data: {json.dumps(payload, ensure_ascii=False)}"
                    )
                    # If this is a video camera feed and has captured an image
                    if reading.get("dataType") == "video" and reading.get("imagePath"):
                        img_relative = reading.get("imagePath")
                        resolved_img_path = os.path.join(workspace_root, img_relative)
                        if os.path.exists(resolved_img_path):
                            image_path = resolved_img_path
                else:
                    live_source_data.append(
                        f"Live reading for source '{source_id}' failed: {reading.get('message')}"
                    )
            except Exception as e:
                live_source_data.append(f"Could not read source '{source_id}': {e}")

    iot_context_block = f"\n\n{iot_context}" if iot_context else ""
    if live_source_data:
        iot_context_block += "\n\nLIVE SOURCE READINGS:\n" + "\n---\n".join(live_source_data)

    prompt = (
        f"{agent.get('systemPrompt') or ''}\n\nAGENT ROLE:\n{agent.get('role')}\n\nAGENT SKILLS:\n{ctx['skillsText']}\n\n"
        f"CONNECTED MCP:\n{ctx['mcpsText']}\n\nUSER TASK:\n{task}\n\nSTEP COMMENT / EXTRA PROMPT:\n{step.get('note') or '-'}\n\n"
        f"PREVIOUS OUTPUT:\n{incoming_output or '-'}{project_context}{iot_context_block}\n\nIMPORTANT EXECUTION RULES:\n"
        "- Return concrete, actionable output.\n- Do not answer with generic text. Produce real deliverables.\n"
        "- If you are a developer, include exact files, patch plan, and full code blocks.\n"
        "- If this is an IoT workflow, identify the source signal, confidence, allowed device action, approval requirement and safe fallback.\n"
        f"- {write_mode}\n"
        "- To create files, use this exact format and relative paths only:\n\n"
        '```file path="src/example.js"\ncontent here\n```\n\n'
        "- File block permissions are role-aware: developer/file-write agents may write source/config, QA may write tests, and docs agents may write Markdown/docs.\n"
        "- Do not wrap implementation-only changes only in Markdown. Use file blocks for code, tests, config and folders that should exist.\n"
        "- Keep dependencies minimal and explain commands.\n"
    )

    started_at = _iso_now()
    await _emit(on_event, {"type": "llm_start", "agentName": agent_name, "message": "Calling model/provider..."})
    try:
        output = await call_llm(
            provider=agent.get("provider"),
            model=agent.get("model"),
            temperature=agent.get("temperature"),
            prompt=prompt,
            runtime_settings=runtime_settings,
            usage="workflow",
            image_path=image_path,
        )
    except ProviderConfigurationError as exc:
        output = str(exc)
        log = {
            "step": index + 1,
            "loop": global_loop,
            "groupLoop": group_loop,
            "stepLoop": local_loop,
            "agentId": agent.get("id"),
            "agentName": agent_name,
            "startedAt": started_at,
            "finishedAt": _iso_now(),
            "artifactPath": None,
            "generatedFiles": [],
            "iotSourceIds": step.get("iotSourceIds") or agent.get("iotSourceIds") or [],
            "iotActionIds": step.get("iotActionIds") or agent.get("iotActionIds") or [],
            "output": output,
            "error": "provider_not_configured",
        }
        await _emit(on_event, {"type": "error", "agentName": agent_name, "error": output, "message": output})
        await _emit(on_event, {"type": "step_done", "log": log, "message": f"{agent_name} failed: provider is not configured."})
        return log
    artifact_path = await _write_agent_artifact(agent, workspace_root, output, index, global_loop, group_loop, local_loop, project_context, on_event)
    generated_files = await _write_generated_file_blocks(agent, workspace_root, output, runtime_settings, on_event)
    log = {
        "step": index + 1,
        "loop": global_loop,
        "groupLoop": group_loop,
        "stepLoop": local_loop,
        "agentId": agent.get("id"),
        "agentName": agent_name,
        "startedAt": started_at,
        "finishedAt": _iso_now(),
        "artifactPath": artifact_path,
        "generatedFiles": generated_files,
        "iotSourceIds": step.get("iotSourceIds") or agent.get("iotSourceIds") or [],
        "iotActionIds": step.get("iotActionIds") or agent.get("iotActionIds") or [],
        "output": output,
    }
    await _emit(on_event, {"type": "step_done", "log": log, "message": f"{agent_name} finished."})
    return log


async def _missing_agent_log(
    step: dict[str, Any],
    index: int,
    global_loop: int,
    group_loop: int | None,
    local_loop: int,
    on_event: EventHandler | None,
) -> dict[str, Any]:
    missing_id = step.get("agentId")
    message = f"Step {index + 1} skipped: agent not found: {missing_id}"
    await _emit(on_event, {"type": "warning", "step": index + 1, "agentId": missing_id, "message": message})
    return {
        "step": index + 1,
        "loop": global_loop,
        "groupLoop": group_loop,
        "stepLoop": local_loop,
        "agentId": missing_id,
        "agentName": "Missing agent",
        "startedAt": _iso_now(),
        "finishedAt": _iso_now(),
        "artifactPath": None,
        "generatedFiles": [],
        "iotSourceIds": step.get("iotSourceIds") or [],
        "iotActionIds": step.get("iotActionIds") or [],
        "output": message,
        "error": "agent_not_found",
    }


async def run_flow(
    flow: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    mcps: list[dict[str, Any]],
    task: str,
    loops: Any = 1,
    workspace_root: str = "",
    loop_groups: list[dict[str, Any]] | None = None,
    runtime_settings: dict[str, Any] | None = None,
    on_event: EventHandler | None = None,
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    previous_output = ""
    max_loops = _clamp_int(loops, 1, 10, 1)
    groups = _normalize_loop_groups(loop_groups, len(flow))
    await _emit(on_event, {"type": "run_start", "message": f"Run started: {len(flow)} steps, {max_loops} chain loop(s), {len(groups)} loop group(s)."})

    for global_loop in range(1, max_loops + 1):
        await _emit(on_event, {"type": "chain_loop_start", "loop": global_loop, "message": f"Chain loop {global_loop}/{max_loops}"})
        index = 0
        while index < len(flow):
            group = next((item for item in groups if item["start"] == index), None)
            if group:
                group_label = group.get("name") or f"{group['start'] + 1}-{group['end'] + 1}"
                await _emit(on_event, {"type": "group_start", "group": group, "message": f"Loop group {group_label} started ({group['loops']}x)."})
                for group_loop in range(1, group["loops"] + 1):
                    await _emit(on_event, {"type": "group_cycle_start", "group": group, "groupLoop": group_loop, "message": f"Group cycle {group_loop}/{group['loops']}"})
                    for group_index in range(group["start"], group["end"] + 1):
                        step = flow[group_index]
                        agent = next((item for item in agents if item.get("id") == step.get("agentId")), None)
                        if not agent:
                            log = await _missing_agent_log(step, group_index, global_loop, group_loop, 1, on_event)
                            previous_output = log["output"]
                            logs.append({**log, "loopGroupId": group.get("id"), "loopGroupName": group.get("name") or f"Steps {group['start'] + 1}-{group['end'] + 1}"})
                            continue
                        for local_loop in range(1, _clamp_int(step.get("loops", 1), 1, 10, 1) + 1):
                            log = await _run_single_step(
                                step,
                                group_index,
                                agent,
                                skills,
                                mcps,
                                task,
                                workspace_root,
                                previous_output,
                                global_loop,
                                group_loop,
                                local_loop,
                                runtime_settings,
                                on_event,
                            )
                            previous_output = log["output"]
                            logs.append({**log, "loopGroupId": group.get("id"), "loopGroupName": group.get("name") or f"Steps {group['start'] + 1}-{group['end'] + 1}"})
                await _emit(on_event, {"type": "group_done", "group": group, "message": "Loop group finished."})
                index = group["end"] + 1
                continue

            step = flow[index]
            agent = next((item for item in agents if item.get("id") == step.get("agentId")), None)
            if not agent:
                log = await _missing_agent_log(step, index, global_loop, None, 1, on_event)
                previous_output = log["output"]
                logs.append(log)
                index += 1
                continue
            for local_loop in range(1, _clamp_int(step.get("loops", 1), 1, 10, 1) + 1):
                log = await _run_single_step(
                    step,
                    index,
                    agent,
                    skills,
                    mcps,
                    task,
                    workspace_root,
                    previous_output,
                    global_loop,
                    None,
                    local_loop,
                    runtime_settings,
                    on_event,
                )
                previous_output = log["output"]
                logs.append(log)
            index += 1

    await _emit(on_event, {"type": "run_done", "message": f"Run finished with {len(logs)} executed step(s).", "logs": logs})
    return logs
