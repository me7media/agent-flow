from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .settings_service import normalize_runtime_settings


@dataclass(frozen=True)
class IoTSignal:
    source_id: str
    kind: str
    data_type: str
    transport: str
    payload_summary: str


class IoTContextBuilder:
    def __init__(self, settings: dict[str, Any] | None):
        self.settings = normalize_runtime_settings(settings)

    def context_for_step(self, step: dict[str, Any], agent: dict[str, Any]) -> str:
        source_ids = set(step.get("iotSourceIds") or agent.get("iotSourceIds") or [])
        action_ids = set(step.get("iotActionIds") or agent.get("iotActionIds") or [])
        sources = [item for item in self.settings["iotSources"] if item.get("id") in source_ids]
        actions = [item for item in self.settings["iotActions"] if item.get("id") in action_ids]
        if not sources and not actions:
            return ""
        lines = ["IOT CONTEXT:"]
        if sources:
            lines.append("Input sources:")
            for source in sources:
                lines.append(
                    f"- {source.get('name')} ({source.get('kind')}, {source.get('dataType')}, {source.get('transport')}): "
                    f"{source.get('endpoint')} — {source.get('description') or 'no description'}"
                )
        if actions:
            lines.append("Allowed device actions:")
            for action in actions:
                commands = ", ".join(action.get("commands") or [])
                approval = "requires approval" if action.get("requiresApproval") else "can run automatically"
                lines.append(
                    f"- {action.get('name')} ({action.get('kind')}, {action.get('transport')}): commands [{commands}], "
                    f"{approval}, endpoint {action.get('endpoint')}"
                )
        lines.append("Safety rule: describe intended device actions clearly; do not invent hidden capabilities.")
        return "\n".join(lines)


def normalize_signal(payload: dict[str, Any], settings: dict[str, Any] | None) -> IoTSignal:
    runtime = normalize_runtime_settings(settings)
    source_id = payload.get("sourceId") or payload.get("source_id") or ""
    source = next((item for item in runtime["iotSources"] if item.get("id") == source_id), {})
    return IoTSignal(
        source_id=source_id,
        kind=source.get("kind") or payload.get("kind") or "unknown",
        data_type=source.get("dataType") or payload.get("dataType") or "unknown",
        transport=source.get("transport") or payload.get("transport") or "unknown",
        payload_summary=str(payload.get("summary") or payload.get("payload") or "No payload summary")[:2000],
    )


def simulate_action(action_id: str, command: str, settings: dict[str, Any] | None) -> dict[str, Any]:
    runtime = normalize_runtime_settings(settings)
    action = next((item for item in runtime["iotActions"] if item.get("id") == action_id), None)
    if not action:
        raise ValueError(f"IoT action not found: {action_id}")
    if command not in (action.get("commands") or []):
        raise ValueError(f"Unsupported command '{command}' for {action.get('name')}")
    return {
        "ok": True,
        "dryRun": True,
        "actionId": action_id,
        "command": command,
        "endpoint": action.get("endpoint"),
        "requiresApproval": bool(action.get("requiresApproval")),
        "message": f"Prepared dry-run command '{command}' for {action.get('name')}.",
    }


def default_iot_agents() -> list[dict[str, Any]]:
    return [
        {
            "id": "iot-signal-agent",
            "name": "IoT Signal Agent",
            "role": "Normalizes camera, microphone and sensor signals before AI reasoning.",
            "provider": "ollama",
            "model": "llama3.1",
            "temperature": 0.1,
            "skills": ["iot_source", "sensor_reading", "audio_signal"],
            "mcps": ["iot-gateway-mcp", "mqtt-mcp"],
            "systemPrompt": "You normalize IoT input metadata. Identify source, signal type, confidence and missing data before passing it forward.",
            "iotSourceIds": ["front-yard-camera", "garden-motion-sensor"],
        },
        {
            "id": "vision-gesture-agent",
            "name": "Vision Gesture Agent",
            "role": "Recognizes gestures or visual events from configured camera sources.",
            "provider": "gemini",
            "model": "gemini-1.5-flash",
            "temperature": 0.1,
            "skills": ["iot_source", "computer_vision", "gesture_recognition"],
            "mcps": ["rtsp-camera-mcp"],
            "systemPrompt": "You analyze camera signals. Return detected gesture, confidence, frame context and whether a device action is justified.",
            "iotSourceIds": ["front-yard-camera"],
        },
        {
            "id": "iot-device-manager",
            "name": "IoT Device Manager",
            "role": "Prepares safe commands for gates, relays, appliances and other configured devices.",
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "temperature": 0.15,
            "skills": ["device_control", "iot_safety", "api_connector"],
            "mcps": ["iot-gateway-mcp", "http"],
            "systemPrompt": "You are an IoT control agent. Map approved intent to explicit dry-run commands and call out approval requirements before any real device action.",
            "iotActionIds": ["driveway-gate", "kitchen-kettle"],
        },
        {
            "id": "iot-safety-supervisor",
            "name": "IoT Safety Supervisor",
            "role": "Checks permissions, false-positive risk and safe fallback before physical actions.",
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "temperature": 0.05,
            "skills": ["iot_safety", "security", "reviewer"],
            "mcps": [],
            "systemPrompt": "You approve or reject IoT actions. Be conservative around physical devices, access control, children, pets and ambiguous signals.",
        },
    ]


def default_iot_skills() -> list[dict[str, Any]]:
    return [
        {"id": "iot_source", "name": "IoT Source", "category": "iot", "description": "Handles incoming camera, microphone, sensor, webhook or device telemetry."},
        {"id": "computer_vision", "name": "Computer Vision", "category": "iot", "description": "Plans visual recognition from camera/image streams."},
        {"id": "gesture_recognition", "name": "Gesture Recognition", "category": "iot", "description": "Detects simple user gestures and maps them to intents."},
        {"id": "audio_signal", "name": "Audio Signal", "category": "iot", "description": "Processes microphone or sound-event metadata."},
        {"id": "sensor_reading", "name": "Sensor Reading", "category": "iot", "description": "Normalizes raw sensor readings and thresholds."},
        {"id": "device_control", "name": "Device Control", "category": "iot", "description": "Prepares safe commands for gates, relays and smart appliances."},
        {"id": "iot_safety", "name": "IoT Safety", "category": "iot", "description": "Checks approvals, false positives and physical-world safety constraints."},
    ]


def default_iot_mcps() -> list[dict[str, Any]]:
    return [
        {"id": "iot-gateway-mcp", "name": "IoT Gateway MCP", "endpoint": "local://iot-gateway", "description": "Abstract gateway for Wi‑Fi, Bluetooth, cable, HTTP and MQTT devices."},
        {"id": "mqtt-mcp", "name": "MQTT MCP", "endpoint": "mqtt://iot.local", "description": "MQTT telemetry and command topics."},
        {"id": "rtsp-camera-mcp", "name": "RTSP Camera MCP", "endpoint": "rtsp://camera.local", "description": "Camera stream connector for visual IoT pipelines."},
    ]


def default_iot_flows() -> list[dict[str, Any]]:
    return [
        {
            "id": "iot-camera-gesture-gate",
            "name": "IoT: Camera gesture → gate action",
            "category": "iot",
            "task": "Recognize an approved hand gesture from the front-yard camera and prepare a safe driveway gate open/close command.",
            "workspaceRoot": "./workspace",
            "loops": 1,
            "cron": "",
            "steps": [
                {"id": "iot-gate-1", "agentId": "iot-signal-agent", "note": "Read metadata from the configured front-yard camera source.", "loops": 1, "cron": "", "dependsOnPrevious": True, "iotSourceIds": ["front-yard-camera"]},
                {"id": "iot-gate-2", "agentId": "vision-gesture-agent", "note": "Detect gesture intent: open, close, stop or ignore. Include confidence.", "loops": 1, "cron": "", "dependsOnPrevious": True, "iotSourceIds": ["front-yard-camera"]},
                {"id": "iot-gate-3", "agentId": "iot-safety-supervisor", "note": "Reject ambiguous or unsafe actions before touching gate control.", "loops": 1, "cron": "", "dependsOnPrevious": True, "iotActionIds": ["driveway-gate"]},
                {"id": "iot-gate-4", "agentId": "iot-device-manager", "note": "Prepare dry-run gate command and show approval requirements.", "loops": 1, "cron": "", "dependsOnPrevious": True, "iotActionIds": ["driveway-gate"]},
            ],
        },
        {
            "id": "iot-motion-sensor-alert",
            "name": "IoT: Motion sensor → safety review",
            "category": "iot",
            "task": "Process a garden motion sensor signal, classify it and decide whether to notify or trigger a safe device action.",
            "workspaceRoot": "./workspace",
            "loops": 1,
            "cron": "*/5 * * * *",
            "steps": [
                {"id": "iot-motion-1", "agentId": "iot-signal-agent", "note": "Normalize motion sensor event and threshold context.", "loops": 1, "cron": "", "dependsOnPrevious": True, "iotSourceIds": ["garden-motion-sensor"]},
                {"id": "iot-motion-2", "agentId": "iot-safety-supervisor", "note": "Classify false-positive risk and allowed next action.", "loops": 1, "cron": "", "dependsOnPrevious": True},
                {"id": "iot-motion-3", "agentId": "final-assembler", "note": "Summarize event, confidence and next steps for operator.", "loops": 1, "cron": "", "dependsOnPrevious": True},
            ],
        },
    ]
