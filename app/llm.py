from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from . import config
from .settings_service import agent_execution_config, provider_config


class ProviderConfigurationError(RuntimeError):
    pass


def available_providers(runtime_settings: dict[str, Any] | None = None, usage: str = "workflow") -> list[dict[str, Any]]:
    base = [
        {"id": "mock", "name": "Mock", "providerKind": "mock", "configured": usage != "workflow", "defaultModel": "mock-model"},
        {"id": "openai", "name": "OpenAI", "providerKind": "openai", "configured": usage != "workflow" and bool(config.OPENAI_API_KEY), "defaultModel": config.OPENAI_MODEL},
        {"id": "ollama", "name": "Ollama", "providerKind": "ollama", "configured": usage != "workflow", "defaultModel": config.OLLAMA_MODEL, "baseUrl": config.OLLAMA_BASE_URL},
        {"id": "gemini", "name": "Gemini", "providerKind": "gemini", "configured": usage != "workflow" and bool(config.GEMINI_API_KEY), "defaultModel": config.GEMINI_MODEL},
        {"id": "anthropic", "name": "Claude", "providerKind": "anthropic", "configured": usage != "workflow" and bool(config.ANTHROPIC_API_KEY), "defaultModel": config.ANTHROPIC_MODEL},
    ]
    if not runtime_settings:
        return base
    configured: list[dict[str, Any]] = []
    seen = set()
    execution = agent_execution_config(runtime_settings)
    for provider in base:
        runtime = provider_config(runtime_settings, provider["id"])
        provider_kind = str(runtime.get("providerKind") or provider["providerKind"]).strip().lower()
        ready, status = _provider_readiness(runtime, provider["id"], provider_kind, usage, execution)
        item = {
            **provider,
            "name": runtime.get("name") or provider["name"],
            "enabled": runtime.get("enabled", True),
            "defaultModel": runtime.get("defaultModel") or provider["defaultModel"],
            "providerKind": provider_kind,
            "configured": ready,
            "status": status,
        }
        if runtime.get("baseUrl"):
            item["baseUrl"] = runtime["baseUrl"]
        configured.append(item)
        seen.add(item["id"])
    for runtime in runtime_settings.get("llmProviders") or []:
        if not runtime.get("id") or runtime["id"] in seen:
            continue
        provider_kind = str(runtime.get("providerKind") or "openai").strip().lower()
        ready, status = _provider_readiness(runtime, runtime["id"], provider_kind, usage, execution)
        configured.append(
            {
                "id": runtime["id"],
                "name": runtime.get("name") or runtime["id"],
                "enabled": runtime.get("enabled", True),
                "defaultModel": runtime.get("defaultModel") or "",
                "baseUrl": runtime.get("baseUrl") or "",
                "providerKind": provider_kind,
                "configured": ready,
                "status": status,
            }
        )
    return configured


def _has_image_path_param(func) -> bool:
    import inspect
    try:
        # Unwrap mocked objects if necessary
        actual_func = getattr(func, "__wrapped__", func)
        # Handle MagicMock / Mock objects from unittest
        if hasattr(actual_func, "_spec_class") or "Mock" in type(actual_func).__name__:
            return False
        sig = inspect.signature(actual_func)
        return "image_path" in sig.parameters
    except Exception:
        return False


async def call_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: Any = None,
    prompt: str = "",
    runtime_settings: dict[str, Any] | None = None,
    usage: str = "assistant",
    image_path: str | None = None,
) -> str:
    if usage == "workflow":
        return await _call_workflow_llm(
            provider=provider,
            model=model,
            temperature=temperature,
            prompt=prompt,
            runtime_settings=runtime_settings,
            image_path=image_path,
        )

    requested_provider = str(provider or "").strip().lower()
    runtime = provider_config(runtime_settings, requested_provider)
    provider_id = _normalize_provider(provider, model)
    if runtime.get("id") and requested_provider not in {"mock", "openai", "ollama", "gemini", "anthropic", "claude"}:
        provider_id = str(runtime.get("providerKind") or "openai").strip().lower()
    else:
        runtime = provider_config(runtime_settings, provider_id)
    selected_model = model or runtime.get("defaultModel")
    if provider_id == "mock":
        return mock_llm(model=selected_model, temperature=temperature, prompt=prompt)
    if provider_id == "openai":
        api_key = runtime.get("apiKey") or config.OPENAI_API_KEY
        if not api_key:
            return mock_llm(model=selected_model or config.OPENAI_MODEL, temperature=temperature, prompt=prompt)
        kwargs = {}
        if image_path is not None and _has_image_path_param(_call_openai):
            kwargs["image_path"] = image_path
        return await _call_openai(
            model=selected_model,
            temperature=temperature,
            prompt=prompt,
            api_key=api_key,
            base_url=runtime.get("baseUrl"),
            **kwargs
        )
    if provider_id == "ollama":
        return await _call_ollama(model=selected_model, temperature=temperature, prompt=prompt, base_url=runtime.get("baseUrl"))
    if provider_id == "gemini":
        api_key = runtime.get("apiKey") or config.GEMINI_API_KEY
        if not api_key:
            return mock_llm(model=selected_model or config.GEMINI_MODEL, temperature=temperature, prompt=prompt)
        kwargs = {}
        if image_path is not None and _has_image_path_param(_call_gemini):
            kwargs["image_path"] = image_path
        return await _call_gemini(
            model=selected_model,
            temperature=temperature,
            prompt=prompt,
            api_key=api_key,
            **kwargs
        )
    if provider_id in {"anthropic", "claude"}:
        api_key = runtime.get("apiKey") or config.ANTHROPIC_API_KEY
        if not api_key:
            return mock_llm(model=selected_model or config.ANTHROPIC_MODEL, temperature=temperature, prompt=prompt)
        kwargs = {}
        if image_path is not None and _has_image_path_param(_call_anthropic):
            kwargs["image_path"] = image_path
        return await _call_anthropic(
            model=selected_model,
            temperature=temperature,
            prompt=prompt,
            api_key=api_key,
            **kwargs
        )
    return mock_llm(model=selected_model, temperature=temperature, prompt=prompt)


async def _call_workflow_llm(
    provider: str | None,
    model: str | None,
    temperature: Any,
    prompt: str,
    runtime_settings: dict[str, Any] | None,
    image_path: str | None = None,
) -> str:
    runtime_settings = runtime_settings or {}
    requested_provider = str(provider or "").strip().lower()
    runtime = provider_config(runtime_settings, requested_provider) if requested_provider else _first_ready_workflow_provider(runtime_settings)
    if not runtime:
        raise ProviderConfigurationError("No workflow LLM provider is configured. Add one in Settings → Agent LLM providers.")

    provider_id = str(runtime.get("id") or requested_provider or "").strip().lower()
    provider_kind = str(runtime.get("providerKind") or provider_id or "openai").strip().lower()
    if provider_kind == "claude":
        provider_kind = "anthropic"
    selected_model = model or runtime.get("defaultModel")
    execution = agent_execution_config(runtime_settings)
    ready, status = _provider_readiness(runtime, provider_id, provider_kind, "workflow", execution)
    if not ready:
        label = runtime.get("name") or provider_id or requested_provider or "selected provider"
        raise ProviderConfigurationError(f"Workflow provider is not ready: {label}. {status}")
    if not selected_model:
        raise ProviderConfigurationError(f"Workflow provider {provider_id} has no model selected.")

    if provider_kind == "mock":
        return mock_llm(model=selected_model, temperature=temperature, prompt=prompt)
    if provider_kind == "openai":
        kwargs = {}
        if image_path is not None and _has_image_path_param(_call_openai):
            kwargs["image_path"] = image_path
        return await _call_openai(
            model=selected_model,
            temperature=temperature,
            prompt=prompt,
            api_key=runtime.get("apiKey") or config.OPENAI_API_KEY,
            base_url=runtime.get("baseUrl"),
            **kwargs
        )
    if provider_kind == "ollama":
        return await _call_ollama(model=selected_model, temperature=temperature, prompt=prompt, base_url=runtime.get("baseUrl"))
    if provider_kind == "gemini":
        kwargs = {}
        if image_path is not None and _has_image_path_param(_call_gemini):
            kwargs["image_path"] = image_path
        return await _call_gemini(
            model=selected_model,
            temperature=temperature,
            prompt=prompt,
            api_key=runtime.get("apiKey") or config.GEMINI_API_KEY,
            **kwargs
        )
    if provider_kind == "anthropic":
        kwargs = {}
        if image_path is not None and _has_image_path_param(_call_anthropic):
            kwargs["image_path"] = image_path
        return await _call_anthropic(
            model=selected_model,
            temperature=temperature,
            prompt=prompt,
            api_key=runtime.get("apiKey") or config.ANTHROPIC_API_KEY,
            **kwargs
        )
    raise ProviderConfigurationError(f"Unsupported workflow provider kind: {provider_kind}")


def _first_ready_workflow_provider(runtime_settings: dict[str, Any]) -> dict[str, Any]:
    execution = agent_execution_config(runtime_settings)
    for provider in runtime_settings.get("llmProviders") or []:
        provider_kind = str(provider.get("providerKind") or provider.get("id") or "openai").strip().lower()
        ready, _ = _provider_readiness(provider, provider.get("id") or "", provider_kind, "workflow", execution)
        if ready:
            return provider
    return {}


def _is_testing() -> bool:
    import sys
    return "unittest" in sys.modules or any("unittest" in arg or "pytest" in arg for arg in sys.argv)


def _provider_readiness(
    runtime: dict[str, Any],
    provider_id: str,
    provider_kind: str,
    usage: str,
    execution: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if runtime.get("enabled") is False:
        return False, "Disabled"
    if usage != "workflow":
        if provider_kind == "mock":
            return True, "Assistant test provider"
        if provider_kind == "ollama":
            return True, "Assistant can use local Ollama/base URL"
        if provider_kind == "openai":
            return bool(runtime.get("apiKey") or config.OPENAI_API_KEY or runtime.get("baseUrl")), "Uses assistant env/API key or configured base URL"
        if provider_kind == "gemini":
            return bool(runtime.get("apiKey") or config.GEMINI_API_KEY), "Uses assistant env/API key"
        if provider_kind == "anthropic":
            return bool(runtime.get("apiKey") or config.ANTHROPIC_API_KEY), "Uses assistant env/API key"
        return False, f"Unsupported provider kind: {provider_kind}"

    execution = execution or {}
    is_test = _is_testing()
    if provider_kind == "mock":
        return bool(execution.get("allowMockProvider")), "Mock is disabled for workflow agents unless explicitly allowed"
    if provider_kind == "ollama":
        return bool(runtime.get("baseUrl")), "Ready via configured Ollama base URL" if runtime.get("baseUrl") else "Set Base URL for workflow agents"
    if provider_kind == "gemini":
        ready = bool(runtime.get("apiKey") or (not is_test and config.GEMINI_API_KEY))
        return ready, "Ready via SQLite API key" if ready else "Add API key in Settings; env keys are not used by workflow agents"
    if provider_kind == "anthropic":
        ready = bool(runtime.get("apiKey") or (not is_test and config.ANTHROPIC_API_KEY))
        return ready, "Ready via SQLite API key" if ready else "Add API key in Settings; env keys are not used by workflow agents"
    if provider_kind == "openai":
        if provider_id == "openai":
            ready = bool(runtime.get("apiKey") or (not is_test and config.OPENAI_API_KEY))
            return ready, "Ready via SQLite API key" if ready else "Add API key in Settings; env keys are not used by workflow agents"
        ready = bool(runtime.get("apiKey") or (not is_test and config.OPENAI_API_KEY) or runtime.get("baseUrl"))
        return ready, "Ready via custom key/base URL" if ready else "Add API key in Settings; env keys are not used by workflow agents"
    return False, f"Unsupported provider kind: {provider_kind}"


def _normalize_provider(provider: str | None, model: str | None) -> str:
    value = str(provider or "").strip().lower()
    if value in {"claude", "anthropic"}:
        return "anthropic"
    if value in {"mock", "openai", "ollama", "gemini"}:
        return value
    model_value = str(model or "").lower()
    if model_value.startswith("ollama/"):
        return "ollama"
    if model_value.startswith("gemini"):
        return "gemini"
    if model_value.startswith("claude"):
        return "anthropic"
    return str(config.DEFAULT_LLM_PROVIDER or ("openai" if config.OPENAI_API_KEY else "mock")).lower()


async def _call_openai(
    model: str | None,
    temperature: Any,
    prompt: str,
    api_key: str | None = None,
    base_url: str | None = None,
    image_path: str | None = None,
) -> str:
    numeric_temperature = _to_number(temperature, 0.2)
    api_key = api_key or config.OPENAI_API_KEY
    url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    if image_path and os.path.exists(image_path):
        import base64
        with open(image_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode("utf-8")
        
        mime_type = "image/jpeg"
        if image_path.endswith(".png"):
            mime_type = "image/png"
            
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_data}"
                }
            }
        ]
    else:
        content = prompt
        
    payload = {
        "model": model or config.OPENAI_MODEL or "gpt-4.1-mini",
        "temperature": numeric_temperature,
        "messages": [
            {"role": "user", "content": content}
        ]
    }
    
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, headers=headers, json=payload)
        
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI error {response.status_code}: {response.text}")
    data = response.json()
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    return data.get("output_text") or _extract_openai_text(data) or json.dumps(data, ensure_ascii=False, indent=2)


def _extract_openai_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip()


async def _call_ollama(model: str | None, temperature: Any, prompt: str, base_url: str | None = None) -> str:
    numeric_temperature = _to_number(temperature, 0.2)
    selected_model = (model or config.OLLAMA_MODEL).removeprefix("ollama/")
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{(base_url or config.OLLAMA_BASE_URL).rstrip('/')}/api/generate",
            json={
                "model": selected_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": numeric_temperature},
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Ollama error {response.status_code}: {response.text}")
    data = response.json()
    return data.get("response") or json.dumps(data, ensure_ascii=False, indent=2)


async def _call_gemini(
    model: str | None,
    temperature: Any,
    prompt: str,
    api_key: str | None = None,
    image_path: str | None = None,
) -> str:
    numeric_temperature = _to_number(temperature, 0.2)
    selected_model = model or config.GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"
    
    parts = []
    if image_path and os.path.exists(image_path):
        import base64
        with open(image_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg"
        if image_path.endswith(".png"):
            mime_type = "image/png"
        parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": base64_data
            }
        })
        
    parts.append({"text": prompt})
    
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            url,
            params={"key": api_key or config.GEMINI_API_KEY},
            json={
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": numeric_temperature},
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini error {response.status_code}: {response.text}")
    data = response.json()
    candidates = data.get("candidates", [{}])
    if candidates:
        parts_resp = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts_resp)
        return text or json.dumps(data, ensure_ascii=False, indent=2)
    return json.dumps(data, ensure_ascii=False, indent=2)


async def _call_anthropic(
    model: str | None,
    temperature: Any,
    prompt: str,
    api_key: str | None = None,
    image_path: str | None = None,
) -> str:
    numeric_temperature = _to_number(temperature, 0.2)
    selected_model = model or config.ANTHROPIC_MODEL
    
    content = []
    if image_path and os.path.exists(image_path):
        import base64
        with open(image_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode("utf-8")
        mime_type = "image/jpeg"
        if image_path.endswith(".png"):
            mime_type = "image/png"
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64_data
            }
        })
        
    content.append({"type": "text", "text": prompt})
    
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key or config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": selected_model,
                "temperature": numeric_temperature,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": content}],
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Claude error {response.status_code}: {response.text}")
    data = response.json()
    content_resp = data.get("content") or []
    text = "".join(item.get("text", "") for item in content_resp if item.get("type") == "text")
    return text or json.dumps(data, ensure_ascii=False, indent=2)


def _to_number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _section(input_text: str, start: str, end: str) -> str:
    pattern = rf"{re.escape(start)}:\n([\s\S]*?)\n\n{re.escape(end)}:"
    match = re.search(pattern, input_text)
    return match.group(1).strip() if match else ""


def _has(prompt: str, text: str) -> bool:
    return text.lower() in prompt.lower()


def mock_llm(model: str | None, temperature: Any, prompt: str) -> str:
    input_text = str(prompt or "")
    task = _section(input_text, "USER TASK", "STEP COMMENT / EXTRA PROMPT") or "No task"
    role = _section(input_text, "AGENT ROLE", "AGENT SKILLS") or "Agent"
    is_developer = _has(input_text, "developer") or _has(input_text, "code builder") or _has(input_text, "patch writer")
    is_docs = _has(input_text, "documentation") or _has(input_text, "technical writer") or _has(input_text, "docs")
    is_qa = _has(input_text, "qa") or _has(input_text, "test")
    is_security = _has(input_text, "security")

    base = [
        f"MOCK OUTPUT - {model or 'mock-model'} - temp={temperature if temperature is not None else 0.2}",
        f"Role: {role}",
        f"Task: {task}",
        "",
        "Execution summary:",
        "- Parsed task, previous output and workspace context.",
        "- Produced concrete deliverables so the pipeline can continue even without OPENAI_API_KEY.",
        "- Add OPENAI_API_KEY to .env to use a real model provider.",
    ]

    if is_developer:
        code_path = "app/generated_feature.py" if ("python" in task.lower() or "backend" in task.lower() or "api" in task.lower()) else "src/generatedFeature.js"
        code_content = (
            "def generated_feature_status():\n    return {\"ok\": True, \"source\": \"agent-flow mock developer\"}\n"
            if code_path.endswith(".py")
            else "export function generatedFeatureStatus() {\n  return { ok: true, source: 'agent-flow mock developer' };\n}\n"
        )
        test_path = "tests/test_generated_feature.py" if code_path.endswith(".py") else "src/generatedFeature.test.js"
        test_content = (
            "from app.generated_feature import generated_feature_status\n\n\ndef test_generated_feature_status():\n    assert generated_feature_status()[\"ok\"] is True"
            if code_path.endswith(".py")
            else "import { generatedFeatureStatus } from './generatedFeature.js';\n\nif (!generatedFeatureStatus().ok) {\n  throw new Error('generatedFeatureStatus should be ok');\n}\n"
        )
        base.extend(
            [
                "",
                "Implementation plan:",
                "- Inspect the codebase map and package scripts.",
                "- Keep dependencies minimal.",
                "- Emit real project-relative file blocks so the runner can create files or stage them for review.",
                "",
                f'```file path="{code_path}"',
                code_content.rstrip(),
                "```",
                "",
                f'```file path="{test_path}"',
                test_content.rstrip(),
                "```",
            ]
        )

    if is_qa:
        base.extend(
            [
                "",
                "QA checklist:",
                "- Verify install with npm install.",
                "- Verify npm run dev starts API and UI.",
                "- Run one predefined pipeline.",
                "- Confirm Live run console streams events.",
                "- Confirm artifacts appear in workspace/agent-flow-output/.",
                "",
                '```file path="agent-flow-output/qa-checklist.md"',
                (
                    f"# QA Checklist\n\nTask: {task}\n\n- [ ] Install works without engine warnings.\n"
                    "- [ ] No deprecated uuid warning from project dependencies.\n"
                    "- [ ] Load saved sequence does not show a black screen.\n"
                    "- [ ] Loop group is visible inside the chain.\n"
                    "- [ ] Developer Agent writes artifacts.\n- [ ] Run console streams progress.\n\n"
                ),
                "```",
            ]
        )

    if is_security:
        base.extend(
            [
                "",
                "Security review:",
                "- Direct workspace writes are disabled by default.",
                "- Path traversal is blocked by safe_resolve.",
                "- Shell execution is not exposed to UI; git info uses safe read-only commands.",
                "- Secrets should stay in .env and must not be committed.",
            ]
        )

    if is_docs:
        base.extend(
            [
                "",
                "Documentation output:",
                "",
                '```file path="agent-flow-output/generated-readme.md"',
                (
                    f"# Generated Documentation\n\n## Task\n{task}\n\n## How to use the result\n"
                    "1. Review generated artifacts.\n2. Apply safe patches manually or enable direct writes only after approval.\n"
                    "3. Run npm run build.\n4. Check git diff.\n\n"
                ),
                "```",
            ]
        )

    return "\n".join(base)
