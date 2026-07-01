from __future__ import annotations

import base64
from copy import deepcopy
import os
from typing import Any

from . import config


SETTINGS_ID = "runtime-settings"
SECRET_MASK = "••••••••"


def encrypt_secret(val: str) -> str:
    if not val:
        return ""
    if val.startswith("enc:"):
        return val
    # Derive key from environment or fallback salt
    raw_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or "agent-flow-default-secret-salt-2026"
    key = raw_key.encode("utf-8")
    encrypted_bytes = bytes(ord(c) ^ key[i % len(key)] for i, c in enumerate(val))
    return "enc:" + base64.b64encode(encrypted_bytes).decode("utf-8")


def decrypt_secret(val: str) -> str:
    if not val or not val.startswith("enc:"):
        return val
    try:
        raw_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or "agent-flow-default-secret-salt-2026"
        key = raw_key.encode("utf-8")
        encrypted_bytes = base64.b64decode(val[4:])
        decrypted_chars = [chr(b ^ key[i % len(key)]) for i, b in enumerate(encrypted_bytes)]
        return "".join(decrypted_chars)
    except Exception:
        return val


def default_runtime_settings() -> dict[str, Any]:
    return {
        "id": SETTINGS_ID,
        "name": "Runtime settings",
        "agentExecution": {
            "fileWriteMode": "review",
            "maxFileBlocks": 20,
            "allowMockProvider": False,
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
                "id": "PTZB648647BMZSB",
                "name": "Camera0 (webcam / RTSP)",
                "kind": "camera",
                "transport": "wifi/http",
                "endpoint": "http://127.0.0.1:8787/api/iot/camera/PTZB648647BMZSB",
                "dataType": "video",
                "enabled": True,
                "description": "Surveillance camera Camera0 (Tuya ID: PTZB648647BMZSB) via local HTTP gateway/FaceTime HD camera.",
            },
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
                "id": "doorbell-ring",
                "name": "Smart Doorbell Camera",
                "kind": "camera",
                "transport": "wifi/http",
                "endpoint": "http://127.0.0.1:8787/api/iot/camera/PTZB648647BMZSB",
                "dataType": "video",
                "enabled": True,
                "description": "Smart video doorbell camera stream at the front door.",
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
            {
                "id": "living-room-thermo",
                "name": "Living Room Thermostat",
                "kind": "sensor",
                "transport": "wifi/http",
                "endpoint": "http://127.0.0.1:8787/api/iot/thermo/telemetry",
                "dataType": "json",
                "enabled": True,
                "description": "Wi-Fi sensor reporting temperature, humidity and air quality index.",
            },
            {
                "id": "custom-mcu-sensor",
                "name": "Custom ESP32 Sensor",
                "kind": "sensor",
                "transport": "custom/esp32",
                "endpoint": "http://192.168.0.150/telemetry",
                "dataType": "json",
                "enabled": True,
                "description": "Custom embedded microcontroller telemetry feed (temperature/vibration/distance).",
            },
        ],
        "iotActions": [
            {
                "id": "driveway-gate",
                "name": "Driveway gate controller",
                "kind": "gate",
                "transport": "wifi/http",
                "endpoint": "http://127.0.0.1:8787/api/iot/gate/control",
                "commands": ["open", "close", "stop"],
                "requiresApproval": True,
                "enabled": True,
                "description": "Driveway gate actuator used by gesture workflows.",
            },
            {
                "id": "garage-door",
                "name": "Garage door opener",
                "kind": "gate",
                "transport": "wifi/http",
                "endpoint": "http://127.0.0.1:8787/api/iot/gate/control?device=garage",
                "commands": ["open", "close"],
                "requiresApproval": True,
                "enabled": True,
                "description": "Smart garage relay board.",
            },
            {
                "id": "kitchen-kettle",
                "name": "Smart kettle",
                "kind": "appliance",
                "transport": "wifi/http",
                "endpoint": "http://127.0.0.1:8787/api/iot/gate/control?device=kettle",
                "commands": ["turn_on", "turn_off"],
                "requiresApproval": True,
                "enabled": True,
                "description": "Smart electric water kettle.",
            },
            {
                "id": "living-room-ac",
                "name": "Living Room AC",
                "kind": "appliance",
                "transport": "wifi/http",
                "endpoint": "http://127.0.0.1:8787/api/iot/gate/control?device=ac",
                "commands": ["turn_on", "turn_off", "set_temp_22", "set_temp_24"],
                "requiresApproval": False,
                "enabled": True,
                "description": "Smart AC or IR blaster.",
            },
            {
                "id": "window-blinds",
                "name": "Window blinds motor",
                "kind": "motor",
                "transport": "zigbee/mqtt",
                "endpoint": "mqtt://iot.local/blinds/control",
                "commands": ["open", "close", "stop"],
                "requiresApproval": False,
                "enabled": True,
                "description": "Zigbee motorized roller shade controller.",
            },
            {
                "id": "smart-lock",
                "name": "Front door lock",
                "kind": "lock",
                "transport": "ble/lock",
                "endpoint": "local://lock/front-door",
                "commands": ["lock", "unlock"],
                "requiresApproval": True,
                "enabled": True,
                "description": "Smart Bluetooth deadbolt actuator.",
            },
            {
                "id": "custom-esp32-relay",
                "name": "Custom ESP32 Relay Board",
                "kind": "switch",
                "transport": "custom/esp32",
                "endpoint": "http://192.168.0.150/relay",
                "commands": ["high", "low"],
                "requiresApproval": False,
                "enabled": True,
                "description": "Custom Arduino/ESP32 relay switch controlling secondary GPIO pins.",
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
    for action in public["iotActions"]:
        if action.get("localKey"):
            action["localKey"] = SECRET_MASK
    return public


def get_runtime_settings(db: dict[str, Any]) -> dict[str, Any]:
    existing = next((item for item in db.get("settings") or [] if item.get("id") == SETTINGS_ID), None)
    settings = normalize_runtime_settings(existing)
    
    # Decrypt all keys for runtime usage
    for provider in settings.get("llmProviders", []):
        if provider.get("apiKey"):
            provider["apiKey"] = decrypt_secret(provider["apiKey"])
    for action in settings.get("iotActions", []):
        if action.get("localKey"):
            action["localKey"] = decrypt_secret(action["localKey"])
            
    return settings


def upsert_runtime_settings(db: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    existing = get_runtime_settings(db) # already decrypted
    merged = normalize_runtime_settings(_merge_secret_fields(existing, incoming or {}))
    
    # Create copy to encrypt before DB write
    to_save = deepcopy(merged)
    for provider in to_save.get("llmProviders", []):
        if provider.get("apiKey"):
            provider["apiKey"] = encrypt_secret(provider["apiKey"])
    for action in to_save.get("iotActions", []):
        if action.get("localKey"):
            action["localKey"] = encrypt_secret(action["localKey"])
            
    db["settings"] = [item for item in db.get("settings") or [] if item.get("id") != SETTINGS_ID] + [to_save]
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
        if item.get("apiKey") in {SECRET_MASK, "********"}:
            item["apiKey"] = existing_providers.get(item.get("id"), {}).get("apiKey", "")
        providers.append(item)
    if providers:
        merged["llmProviders"] = providers
        
    existing_actions = {item.get("id"): item for item in existing.get("iotActions") or []}
    actions = []
    for action in incoming.get("iotActions") or []:
        item = dict(action)
        if item.get("localKey") in {SECRET_MASK, "********"}:
            item["localKey"] = existing_actions.get(item.get("id"), {}).get("localKey", "")
        actions.append(item)
    if actions:
        merged["iotActions"] = actions
        
    return merged
