from __future__ import annotations

import asyncio
import ipaddress
import json
import platform
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from . import config
from .settings_service import normalize_runtime_settings


@dataclass(frozen=True)
class AdapterCapability:
    id: str
    name: str
    transports: list[str]
    can_discover: bool
    can_read: bool
    can_execute: bool
    real_time: bool
    notes: str


CAPABILITIES = [
    AdapterCapability(
        id="wifi-http",
        name="Wi‑Fi / HTTP device",
        transports=["wifi/http", "http", "https", "wifi"],
        can_discover=True,
        can_read=True,
        can_execute=True,
        real_time=True,
        notes="Works with HTTP/JSON devices, gateways, ESPHome/Tasmota-style APIs, local hubs and webhooks when host is allowlisted.",
    ),
    AdapterCapability(
        id="mqtt-gateway",
        name="MQTT via gateway",
        transports=["mqtt", "mqtt/wifi"],
        can_discover=False,
        can_read=False,
        can_execute=False,
        real_time=False,
        notes="Requires an HTTP/MQTT bridge or future optional MQTT dependency; currently represented as a configured gateway endpoint.",
    ),
    AdapterCapability(
        id="bluetooth-inventory",
        name="Bluetooth inventory",
        transports=["bluetooth", "bt", "ble"],
        can_discover=True,
        can_read=False,
        can_execute=False,
        real_time=True,
        notes="Can list known macOS Bluetooth devices; real BLE read/write should be done through a paired gateway adapter.",
    ),
    AdapterCapability(
        id="rtsp-camera",
        name="RTSP camera metadata",
        transports=["rtsp", "wifi/rtsp"],
        can_discover=False,
        can_read=False,
        can_execute=False,
        real_time=False,
        notes="Camera streams are modeled as sources; frame capture/vision should be provided by a camera gateway or vision service.",
    ),
]


def adapter_catalog() -> list[dict[str, Any]]:
    return [capability.__dict__ for capability in CAPABILITIES]


def _transport(value: str | None) -> str:
    return str(value or "").strip().lower()


def _is_http_transport(value: str | None) -> bool:
    transport = _transport(value)
    return "http" in transport or transport in {"https"}


def _is_bluetooth_transport(value: str | None) -> bool:
    transport = _transport(value)
    return any(token in transport for token in ["bluetooth", "bt", "ble"])


def _host_allowed(url: str | None, allowed_hosts: list[str] | None = None) -> bool:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    allowed = {host.lower() for host in (allowed_hosts if allowed_hosts is not None else config.IOT_ALLOWED_HOSTS)}
    if not allowed:
        return False
    hostname = parsed.hostname.lower()
    if hostname in allowed:
        return True
    try:
        return str(ipaddress.ip_address(hostname)) in allowed
    except ValueError:
        return False


def _safe_ports(values: Any) -> list[int]:
    ports: list[int] = []
    for value in values or [80, 443, 8080, 8123]:
        try:
            port = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535 and port not in ports:
            ports.append(port)
    return ports[:8]


def _hosts_from_body(body: dict[str, Any]) -> list[str]:
    hosts = [str(item).strip() for item in body.get("hosts") or [] if str(item).strip()]
    subnet = str(body.get("subnet") or "").strip()
    if subnet:
        network = ipaddress.ip_network(subnet, strict=False)
        hosts.extend(str(host) for host in network.hosts())
    deduped: list[str] = []
    for host in hosts:
        if host not in deduped:
            deduped.append(host)
    return deduped[: config.IOT_DISCOVERY_MAX_HOSTS]


async def _probe_http_host(client: httpx.AsyncClient, host: str, port: int) -> dict[str, Any] | None:
    scheme = "https" if port == 443 else "http"
    base = f"{scheme}://{host}:{port}"
    for path in ["/status", "/health", "/"]:
        url = f"{base}{path}"
        try:
            response = await client.get(url, timeout=1.5)
        except Exception:
            continue
        if response.status_code < 500:
            text = response.text[:400]
            return {
                "id": f"http-{host}-{port}",
                "name": f"HTTP device {host}:{port}",
                "transport": "wifi/http",
                "endpoint": base,
                "status": response.status_code,
                "sample": text,
                "suggestedSource": {
                    "id": f"source-{host.replace('.', '-')}-{port}",
                    "name": f"HTTP source {host}:{port}",
                    "kind": "gateway",
                    "transport": "wifi/http",
                    "endpoint": base,
                    "dataType": "json/text",
                    "enabled": True,
                    "description": "Discovered HTTP-capable IoT device or gateway.",
                },
            }
    return None


async def discover_iot_devices(body: dict[str, Any]) -> dict[str, Any]:
    transport = _transport(body.get("transport") or "wifi/http")
    if _is_bluetooth_transport(transport):
        return {"ok": True, "transport": transport, "devices": _discover_bluetooth_devices(), "notes": "Bluetooth device control requires a paired gateway adapter."}
    if not _is_http_transport(transport):
        return {"ok": True, "transport": transport, "devices": [], "notes": "This transport uses configured endpoints or an external gateway; no built-in scanner is available."}
    hosts = _hosts_from_body(body)
    ports = _safe_ports(body.get("ports"))
    if not hosts:
        return {"ok": True, "transport": transport, "devices": [], "notes": "Provide hosts or a CIDR subnet, e.g. 192.168.1.0/28."}
    async with httpx.AsyncClient(follow_redirects=False) as client:
        tasks = [_probe_http_host(client, host, port) for host in hosts for port in ports]
        results = await asyncio.gather(*tasks)
    devices = [item for item in results if item]
    return {"ok": True, "transport": transport, "scannedHosts": len(hosts), "ports": ports, "devices": devices}


def _discover_bluetooth_devices() -> list[dict[str, Any]]:
    if platform.system().lower() != "darwin":
        return []
    try:
        result = subprocess.run(
            ["system_profiler", "SPBluetoothDataType", "-json"],
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout:
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    devices: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            name = value.get("device_name") or value.get("_name") or value.get("name")
            address = value.get("device_address") or value.get("address")
            if name or address:
                devices.append({"name": name or address, "address": address or "", "transport": "bluetooth", "status": value.get("device_connected") or value.get("device_paired") or "known"})
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    unique: dict[str, dict[str, Any]] = {}
    for device in devices:
        key = device.get("address") or device.get("name")
        if key:
            unique[key] = device
    return list(unique.values())[:50]


def _find_source(source_id: str, settings: dict[str, Any] | None) -> dict[str, Any]:
    runtime = normalize_runtime_settings(settings)
    source = next((item for item in runtime["iotSources"] if item.get("id") == source_id), None)
    if not source:
        raise ValueError(f"IoT source not found: {source_id}")
    if source.get("enabled") is False:
        raise ValueError(f"IoT source is disabled: {source_id}")
    return source


def _find_action(action_id: str, settings: dict[str, Any] | None) -> dict[str, Any]:
    runtime = normalize_runtime_settings(settings)
    action = next((item for item in runtime["iotActions"] if item.get("id") == action_id), None)
    if not action:
        raise ValueError(f"IoT action not found: {action_id}")
    if action.get("enabled") is False:
        raise ValueError(f"IoT action is disabled: {action_id}")
    return action


async def read_iot_source(source_id: str, settings: dict[str, Any] | None) -> dict[str, Any]:
    source = _find_source(source_id, settings)
    endpoint = source.get("endpoint")
    if not _is_http_transport(source.get("transport")):
        return {
            "ok": True,
            "sourceId": source_id,
            "mode": "configured",
            "message": "Source is configured but this transport requires an external gateway for live reads.",
            "source": source,
        }
    if not _host_allowed(endpoint):
        return {"ok": False, "sourceId": source_id, "blocked": True, "message": "Source host is not in IOT_ALLOWED_HOSTS.", "endpoint": endpoint}
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        response = await client.get(endpoint)
    text = response.text[:5000]
    parsed: Any = None
    try:
        parsed = response.json()
    except Exception:
        parsed = None
    return {
        "ok": response.is_success,
        "sourceId": source_id,
        "status": response.status_code,
        "endpoint": endpoint,
        "dataType": source.get("dataType"),
        "payload": parsed if parsed is not None else text,
        "summary": text[:1000],
    }


async def execute_iot_action(action_id: str, command: str, settings: dict[str, Any] | None, approved: bool = False, dry_run: bool | None = None) -> dict[str, Any]:
    action = _find_action(action_id, settings)
    commands = action.get("commands") or []
    if command not in commands:
        raise ValueError(f"Unsupported command '{command}' for {action.get('name')}")
    endpoint = action.get("endpoint")
    should_dry_run = dry_run if dry_run is not None else not config.IOT_DEVICE_ACTIONS_ENABLED
    if should_dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "actionId": action_id,
            "command": command,
            "endpoint": endpoint,
            "requiresApproval": bool(action.get("requiresApproval")),
            "message": f"Prepared dry-run command '{command}' for {action.get('name')}.",
        }
    if action.get("requiresApproval") and not approved:
        return {"ok": False, "approvalRequired": True, "actionId": action_id, "command": command, "message": "Approval is required before real device action."}
    if not _is_http_transport(action.get("transport")):
        return {"ok": False, "actionId": action_id, "command": command, "message": "Real execution for this transport requires an external gateway adapter."}
    if not _host_allowed(endpoint):
        return {"ok": False, "blocked": True, "actionId": action_id, "command": command, "message": "Action host is not in IOT_ALLOWED_HOSTS.", "endpoint": endpoint}
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        response = await client.post(endpoint, json={"command": command, "actionId": action_id})
    return {"ok": response.is_success, "dryRun": False, "actionId": action_id, "command": command, "status": response.status_code, "response": response.text[:5000]}
