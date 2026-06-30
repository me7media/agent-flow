from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import config


SETTINGS_ID = "runtime-settings"
SECRET_MASK = "••••••••"


def default_runtime_settings() -> dict[str, Any]:
    return {
        "id": SETTINGS_ID,
        "name": "Runtime settings",
        "agentExecution": {
            "fileWriteMode": "review",
            "maxFileBlocks": 20,
        },
        "llmProviders": [
            {"id": "mock", "name": "Mock", "providerKind": "mock", "enabled": True, "defaultModel": "mock-model", "apiKey": "", "baseUrl": ""},
            {"id": "openai", "name": "OpenAI", "providerKind": "openai", "enabled": True, "defaultModel": config.OPENAI_MODEL, "apiKey": "", "baseUrl": ""},
            {"id": "ollama", "name": "Ollama", "providerKind": "ollama", "enabled": True, "defaultModel": config.OLLAMA_MODEL, "apiKey": "", "baseUrl": config.OLLAMA_BASE_URL},
            {"id": "gemini", "name": "Gemini", "providerKind": "gemini", "enabled": True, "defaultModel": config.GEMINI_MODEL, "apiKey": "", "baseUrl": ""},
            {"id": "anthropic", "name": "Claude", "providerKind": "anthropic", "enabled": True, "defaultModel": config.ANTHROPIC_MODEL, "apiKey": "", "baseUrl": ""},
        ],
        "iotSources": [
            {
                "id": "front-yard-camera",
                "name": "Front yard camera",
                "kind": "camera",
                "transport": "wifi/rtsp",
                "endpoint": "rtsp://camera.local/stream",
                "dataType": "video",
                "enabled": True,
                "description": "Demo camera source for gesture recognition near the gate.",
            },
            {
                "id": "porch-microphone",
                "name": "Porch microphone",
                "kind": "microphone",
                "transport": "usb/audio",
                "endpoint": "local://audio/porch",
                "dataType": "audio",
                "enabled": False,
                "description": "Audio input source for voice or sound-event workflows.",
            },
            {
                "id": "garden-motion-sensor",
                "name": "Garden motion sensor",
                "kind": "sensor",
                "transport": "mqtt/wifi",
                "endpoint": "mqtt://iot.local/sensors/garden-motion",
                "dataType": "boolean",
                "enabled": True,
                "description": "Motion sensor event stream used by demo IoT pipelines.",
            },
        ],
        "iotActions": [
            {
                "id": "driveway-gate",
                "name": "Driveway gate controller",
                "kind": "gate",
                "transport": "wifi/http",
                "endpoint": "http://iot.local/gate",
                "commands": ["open", "close", "stop"],
                "requiresApproval": True,
                "enabled": True,
                "description": "Dry-run friendly gate actuator used by gesture workflows.",
            },
            {
                "id": "kitchen-kettle",
                "name": "Smart kettle",
                "kind": "appliance",
                "transport": "wifi/http",
                "endpoint": "http://iot.local/kettle",
                "commands": ["turn_on", "turn_off"],
                "requiresApproval": True,
                "enabled": False,
                "description": "Example appliance action for household automation.",
            },
        ],
    }


def normalize_runtime_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    defaults = default_runtime_settings()
    incoming = deepcopy(settings or {})
    normalized = {**defaults, **incoming, "id": SETTINGS_ID, "name": incoming.get("name") or defaults["name"]}
    normalized["agentExecution"] = {**defaults["agentExecution"], **(incoming.get("agentExecution") or {})}
    normalized["llmProviders"] = _merge_by_id(defaults["llmProviders"], incoming.get("llmProviders") or [])
    normalized["iotSources"] = _merge_by_id(defaults["iotSources"], incoming.get("iotSources") or [])
    normalized["iotActions"] = _merge_by_id(defaults["iotActions"], incoming.get("iotActions") or [])
    return normalized


def public_runtime_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    public = normalize_runtime_settings(settings)
    for provider in public["llmProviders"]:
        if provider.get("apiKey"):
            provider["apiKey"] = SECRET_MASK
    return public


def get_runtime_settings(db: dict[str, Any]) -> dict[str, Any]:
    existing = next((item for item in db.get("settings") or [] if item.get("id") == SETTINGS_ID), None)
    return normalize_runtime_settings(existing)


def upsert_runtime_settings(db: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    existing = get_runtime_settings(db)
    merged = normalize_runtime_settings(_merge_secret_fields(existing, incoming or {}))
    db["settings"] = [item for item in db.get("settings") or [] if item.get("id") != SETTINGS_ID] + [merged]
    return merged


def provider_config(settings: dict[str, Any] | None, provider_id: str) -> dict[str, Any]:
    normalized = normalize_runtime_settings(settings)
    provider_key = "anthropic" if provider_id == "claude" else provider_id
    return next((item for item in normalized["llmProviders"] if item.get("id") == provider_key), {})


def agent_execution_config(settings: dict[str, Any] | None) -> dict[str, Any]:
    return normalize_runtime_settings(settings)["agentExecution"]


def _merge_by_id(defaults: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {item["id"]: deepcopy(item) for item in defaults if item.get("id")}
    order = [item["id"] for item in defaults if item.get("id")]
    for item in incoming:
        item_id = item.get("id")
        if not item_id:
            continue
        if item_id not in order:
            order.append(item_id)
        result[item_id] = {**result.get(item_id, {}), **deepcopy(item)}
    return [result[item_id] for item_id in order if item_id in result]


def _merge_secret_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {**existing, **incoming}
    existing_providers = {item.get("id"): item for item in existing.get("llmProviders") or []}
    providers = []
    for provider in incoming.get("llmProviders") or []:
        item = dict(provider)
        if item.get("apiKey") == SECRET_MASK:
            item["apiKey"] = existing_providers.get(item.get("id"), {}).get("apiKey", "")
        providers.append(item)
    if providers:
        merged["llmProviders"] = providers
    return merged
