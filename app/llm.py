from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from . import config


def available_providers() -> list[dict[str, Any]]:
    return [
        {"id": "mock", "name": "Mock", "configured": True, "defaultModel": "mock-model"},
        {"id": "openai", "name": "OpenAI", "configured": bool(config.OPENAI_API_KEY), "defaultModel": config.OPENAI_MODEL},
        {"id": "ollama", "name": "Ollama", "configured": True, "defaultModel": config.OLLAMA_MODEL, "baseUrl": config.OLLAMA_BASE_URL},
        {"id": "gemini", "name": "Gemini", "configured": bool(config.GEMINI_API_KEY), "defaultModel": config.GEMINI_MODEL},
        {"id": "anthropic", "name": "Claude", "configured": bool(config.ANTHROPIC_API_KEY), "defaultModel": config.ANTHROPIC_MODEL},
    ]


async def call_llm(provider: str | None = None, model: str | None = None, temperature: Any = None, prompt: str = "") -> str:
    provider_id = _normalize_provider(provider, model)
    if provider_id == "mock":
        return mock_llm(model=model, temperature=temperature, prompt=prompt)
    if provider_id == "openai":
        if not config.OPENAI_API_KEY:
            return mock_llm(model=model or config.OPENAI_MODEL, temperature=temperature, prompt=prompt)
        return await _call_openai(model=model, temperature=temperature, prompt=prompt)
    if provider_id == "ollama":
        return await _call_ollama(model=model, temperature=temperature, prompt=prompt)
    if provider_id == "gemini":
        if not config.GEMINI_API_KEY:
            return mock_llm(model=model or config.GEMINI_MODEL, temperature=temperature, prompt=prompt)
        return await _call_gemini(model=model, temperature=temperature, prompt=prompt)
    if provider_id in {"anthropic", "claude"}:
        if not config.ANTHROPIC_API_KEY:
            return mock_llm(model=model or config.ANTHROPIC_MODEL, temperature=temperature, prompt=prompt)
        return await _call_anthropic(model=model, temperature=temperature, prompt=prompt)
    return mock_llm(model=model, temperature=temperature, prompt=prompt)


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


async def _call_openai(model: str | None, temperature: Any, prompt: str) -> str:
    numeric_temperature = _to_number(temperature, 0.2)
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            },
            json={
                "model": model or config.OPENAI_MODEL or "gpt-4.1-mini",
                "temperature": numeric_temperature,
                "input": prompt,
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI error {response.status_code}: {response.text}")
    data = response.json()
    return data.get("output_text") or json.dumps(data, ensure_ascii=False, indent=2)


async def _call_ollama(model: str | None, temperature: Any, prompt: str) -> str:
    numeric_temperature = _to_number(temperature, 0.2)
    selected_model = (model or config.OLLAMA_MODEL).removeprefix("ollama/")
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
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


async def _call_gemini(model: str | None, temperature: Any, prompt: str) -> str:
    numeric_temperature = _to_number(temperature, 0.2)
    selected_model = model or config.GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            url,
            params={"key": config.GEMINI_API_KEY},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": numeric_temperature},
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini error {response.status_code}: {response.text}")
    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts)
    return text or json.dumps(data, ensure_ascii=False, indent=2)


async def _call_anthropic(model: str | None, temperature: Any, prompt: str) -> str:
    numeric_temperature = _to_number(temperature, 0.2)
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model or config.ANTHROPIC_MODEL,
                "temperature": numeric_temperature,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Claude error {response.status_code}: {response.text}")
    data = response.json()
    content = data.get("content") or []
    text = "".join(item.get("text", "") for item in content if item.get("type") == "text")
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
