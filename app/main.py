from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import config
from .emailer import send_email
from .iot import default_iot_agents, default_iot_flows, default_iot_mcps, default_iot_skills, normalize_signal
from .iot_runtime import adapter_catalog, discover_iot_devices, execute_iot_action, read_iot_source
from .llm import available_providers
from .registry import advanced_agents, advanced_flows, advanced_mcps, advanced_skills, default_agents, default_flows, default_mcps, default_skills
from .runner import run_flow
from .settings_service import get_runtime_settings, public_runtime_settings, upsert_runtime_settings
from .storage import read_db, write_db
from .workspace import resolve_workspace_root


app = FastAPI(title="Agent Flow Python API")
scheduled: dict[str, asyncio.Task[None]] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def feature_flags() -> dict[str, bool]:
    return {"iot": config.IOT_ENABLED}


def merge_by_id(current: list[dict[str, Any]] | None, defaults: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in [*(defaults or []), *(current or [])]:
        item_id = item.get("id") if isinstance(item, dict) else None
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        result.append(item)
    return result


def _is_iot_entry(item: dict[str, Any]) -> bool:
    text = " ".join(
        str(value)
        for value in [
            item.get("id"),
            item.get("name"),
            item.get("category"),
            item.get("role"),
            *(item.get("skills") or []),
            *(item.get("mcps") or []),
        ]
        if value
    ).lower()
    return item.get("category") == "iot" or any(token in text for token in ["iot", "sensor", "camera", "gesture", "device_control"])


def _filter_iot(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return items if config.IOT_ENABLED else [item for item in items if not _is_iot_entry(item)]


def _public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    public = public_runtime_settings(settings)
    public["features"] = feature_flags()
    if not config.IOT_ENABLED:
        public["iotSources"] = []
        public["iotActions"] = []
    return public


def seed_db(db: dict[str, Any]) -> dict[str, Any]:
    iot_agents = default_iot_agents() if config.IOT_ENABLED else []
    iot_skills = default_iot_skills() if config.IOT_ENABLED else []
    iot_mcps = default_iot_mcps() if config.IOT_ENABLED else []
    iot_flows = default_iot_flows() if config.IOT_ENABLED else []
    db["agents"] = merge_by_id(db.get("agents"), [*default_agents(), *advanced_agents(), *iot_agents])
    db["skills"] = merge_by_id(db.get("skills"), [*default_skills(), *advanced_skills(), *iot_skills])
    db["mcps"] = merge_by_id(db.get("mcps"), [*default_mcps(), *advanced_mcps(), *iot_mcps])
    db["flows"] = merge_by_id(db.get("flows"), [*default_flows(), *advanced_flows(), *iot_flows])
    db.setdefault("runs", [])
    db.setdefault("savedSequences", [])
    upsert_runtime_settings(db, get_runtime_settings(db))
    return db


def _cron_field_valid(field: str | None, minimum: int, maximum: int) -> bool:
    if not field:
        return False
    for part in str(field).split(","):
        if not part:
            return False
        base, _, step_text = part.partition("/")
        if step_text:
            try:
                step = int(step_text)
            except ValueError:
                return False
            if step <= 0:
                return False
        if base == "*":
            continue
        if "-" in base:
            try:
                start, end = [int(piece) for piece in base.split("-", 1)]
            except ValueError:
                return False
            if start > end or start < minimum or end > maximum:
                return False
            continue
        try:
            value = int(base)
        except ValueError:
            return False
        if value < minimum or value > maximum:
            return False
    return True


def cron_field_matches(field: str | None, value: int, minimum: int, maximum: int) -> bool:
    if not field or field == "*":
        return True
    for part in str(field).split(","):
        if "/" in part:
            base, step_text = part.split("/", 1)
            try:
                step = int(step_text)
                start = minimum if base == "*" else int(base.split("-", 1)[0])
            except ValueError:
                continue
            if step > 0 and value >= start and (value - start) % step == 0:
                return True
            continue
        if "-" in part:
            try:
                start, end = [int(piece) for piece in part.split("-", 1)]
            except ValueError:
                continue
            if start <= value <= end:
                return True
            continue
        try:
            if int(part) == value:
                return True
        except ValueError:
            continue
    return False


def is_cron_valid(expr: str | None = "") -> bool:
    fields = str(expr or "").strip().split()
    if len(fields) != 5:
        return False
    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    return all(_cron_field_valid(field, minimum, maximum) for field, (minimum, maximum) in zip(fields, ranges))


def cron_due(expr: str, date: datetime | None = None) -> bool:
    current = date or datetime.now()
    minute, hour, dom, month, dow = str(expr).strip().split()
    js_day_of_week = (current.weekday() + 1) % 7
    return (
        cron_field_matches(minute, current.minute, 0, 59)
        and cron_field_matches(hour, current.hour, 0, 23)
        and cron_field_matches(dom, current.day, 1, 31)
        and cron_field_matches(month, current.month, 1, 12)
        and cron_field_matches(dow, js_day_of_week, 0, 6)
    )


def schedule_flow(flow: dict[str, Any]) -> bool:
    if not flow.get("cron") or not is_cron_valid(flow.get("cron")):
        return False
    flow_id = flow.get("id")
    if not flow_id:
        return False
    if flow_id in scheduled:
        scheduled[flow_id].cancel()

    async def job() -> None:
        last_run_key = ""
        while True:
            await asyncio.sleep(60)
            now = datetime.now()
            key = f"{now.year}-{now.month}-{now.day}-{now.hour}-{now.minute}"
            if key == last_run_key or not cron_due(flow["cron"], now):
                continue
            last_run_key = key
            db = seed_db(read_db())
            logs = await run_flow(
                flow=flow.get("steps") or [],
                agents=_filter_iot(db["agents"]),
                skills=_filter_iot(db["skills"]),
                mcps=_filter_iot(db["mcps"]),
                task=flow.get("task") or "",
                loops=flow.get("loops"),
                workspace_root=flow.get("workspaceRoot") or config.WORKSPACE_ROOT or "",
                loop_groups=flow.get("loopGroups") or [],
                runtime_settings=get_runtime_settings(db),
            )
            db["runs"].append({"id": str(uuid.uuid4()), "flowId": flow_id, "createdAt": iso_now(), "logs": logs})
            write_db(db)

    scheduled[flow_id] = asyncio.create_task(job())
    return True


def restore_schedules() -> None:
    db = seed_db(read_db())
    for flow in _filter_iot(db.get("flows") or []):
        schedule_flow(flow)


@app.on_event("startup")
async def startup() -> None:
    restore_schedules()


@app.on_event("shutdown")
async def shutdown() -> None:
    for task in scheduled.values():
        task.cancel()
    scheduled.clear()


def ok(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status_code)


def error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


def _iot_disabled() -> JSONResponse:
    return error("IoT is disabled by IOT_ENABLED=false", 404)


def _allowed_host(url: str | None, allowed_hosts: list[str]) -> bool:
    if not url or not allowed_hosts:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname in {host.lower() for host in allowed_hosts}:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return str(ip) in allowed_hosts


@app.get("/api/health")
async def health() -> dict[str, Any]:
    db = seed_db(read_db())
    runtime_settings = get_runtime_settings(db)
    providers = available_providers(runtime_settings)
    active_provider = config.DEFAULT_LLM_PROVIDER or ("openai" if config.OPENAI_API_KEY else "mock")
    return {
        "ok": True,
        "provider": active_provider,
        "providers": providers,
        "settings": _public_settings(runtime_settings),
        "features": feature_flags(),
        "workspaceRoot": str(resolve_workspace_root(config.WORKSPACE_ROOT)),
    }


@app.get("/api/registry")
async def registry() -> dict[str, Any]:
    db = seed_db(read_db())
    write_db(db)
    runtime_settings = get_runtime_settings(db)
    return {
        "agents": _filter_iot(db["agents"]),
        "skills": _filter_iot(db["skills"]),
        "mcps": _filter_iot(db["mcps"]),
        "flows": _filter_iot(db["flows"]),
        "providers": available_providers(runtime_settings),
        "settings": _public_settings(runtime_settings),
        "features": feature_flags(),
    }


@app.get("/api/providers")
async def providers() -> list[dict[str, Any]]:
    db = seed_db(read_db())
    return available_providers(get_runtime_settings(db))


@app.get("/api/settings")
async def settings() -> dict[str, Any]:
    db = seed_db(read_db())
    return _public_settings(get_runtime_settings(db))


@app.put("/api/settings")
async def save_settings(request: Request) -> dict[str, Any]:
    body = await request.json()
    if not config.IOT_ENABLED:
        body = {**body, "iotSources": [], "iotActions": []}
    db = seed_db(read_db())
    runtime_settings = upsert_runtime_settings(db, body)
    write_db(db)
    return {"ok": True, "settings": _public_settings(runtime_settings), "providers": available_providers(runtime_settings), "features": feature_flags()}


@app.get("/api/iot/pipelines")
async def iot_pipelines() -> Any:
    if not config.IOT_ENABLED:
        return _iot_disabled()
    db = seed_db(read_db())
    return [flow for flow in db["flows"] if flow.get("category") == "iot"]


@app.get("/api/iot/catalog")
async def iot_catalog() -> Any:
    if not config.IOT_ENABLED:
        return _iot_disabled()
    db = seed_db(read_db())
    runtime_settings = get_runtime_settings(db)
    public = _public_settings(runtime_settings)
    return {"sources": public["iotSources"], "actions": public["iotActions"]}


@app.post("/api/iot/signals")
async def iot_signal(request: Request) -> Any:
    if not config.IOT_ENABLED:
        return _iot_disabled()
    db = seed_db(read_db())
    signal = normalize_signal(await request.json(), get_runtime_settings(db))
    return {"ok": True, "signal": signal.__dict__}


@app.get("/api/iot/adapters")
async def iot_adapters() -> JSONResponse:
    if not config.IOT_ENABLED:
        return _iot_disabled()
    return ok({"ok": True, "adapters": adapter_catalog(), "deviceActionsEnabled": config.IOT_DEVICE_ACTIONS_ENABLED})


@app.post("/api/iot/discover")
async def iot_discover(request: Request) -> JSONResponse:
    if not config.IOT_ENABLED:
        return _iot_disabled()
    try:
        return ok(await discover_iot_devices(await request.json()))
    except Exception as exc:
        return error(str(exc), 400)


@app.post("/api/iot/sources/read")
async def iot_source_read(request: Request) -> JSONResponse:
    if not config.IOT_ENABLED:
        return _iot_disabled()
    try:
        body = await request.json()
        db = seed_db(read_db())
        result = await read_iot_source(body.get("sourceId") or "", get_runtime_settings(db))
        return ok(result, 200 if result.get("ok", True) else 400)
    except Exception as exc:
        return error(str(exc), 400)


@app.post("/api/iot/actions/test")
async def iot_action_test(request: Request) -> JSONResponse:
    if not config.IOT_ENABLED:
        return _iot_disabled()
    try:
        body = await request.json()
        db = seed_db(read_db())
        result = await execute_iot_action(body.get("actionId") or "", body.get("command") or "", get_runtime_settings(db), dry_run=True)
        return ok(result)
    except Exception as exc:
        return error(str(exc), 400)


@app.post("/api/iot/actions/execute")
async def iot_action_execute(request: Request) -> JSONResponse:
    if not config.IOT_ENABLED:
        return _iot_disabled()
    try:
        body = await request.json()
        db = seed_db(read_db())
        result = await execute_iot_action(
            body.get("actionId") or "",
            body.get("command") or "",
            get_runtime_settings(db),
            approved=bool(body.get("approved")),
            dry_run=body.get("dryRun") if isinstance(body.get("dryRun"), bool) else None,
        )
        return ok(result, 200 if result.get("ok", True) else 400)
    except Exception as exc:
        return error(str(exc), 400)


@app.get("/api/agents")
async def agents() -> list[dict[str, Any]]:
    return _filter_iot(seed_db(read_db())["agents"])


@app.post("/api/agents")
async def save_agent(request: Request) -> Any:
    body = await request.json()
    if not config.IOT_ENABLED and _is_iot_entry(body):
        return _iot_disabled()
    db = seed_db(read_db())
    agent = {**body, "id": body.get("id") or str(uuid.uuid4()), "updatedAt": iso_now()}
    db["agents"] = [item for item in db["agents"] if item.get("id") != agent["id"]] + [agent]
    write_db(db)
    return {"ok": True, "agent": agent}


@app.get("/api/flows")
async def flows() -> list[dict[str, Any]]:
    return _filter_iot(seed_db(read_db())["flows"])


@app.post("/api/flows")
async def save_flow(request: Request) -> Any:
    body = await request.json()
    if not config.IOT_ENABLED and body.get("category") == "iot":
        return _iot_disabled()
    db = seed_db(read_db())
    flow = {**body, "id": body.get("id") or str(uuid.uuid4()), "updatedAt": iso_now()}
    db["flows"] = [item for item in db["flows"] if item.get("id") != flow["id"]] + [flow]
    schedule_flow(flow)
    write_db(db)
    return {"ok": True, "flow": flow}


@app.delete("/api/flows/{flow_id}")
async def delete_flow(flow_id: str) -> dict[str, bool]:
    db = seed_db(read_db())
    db["flows"] = [flow for flow in db["flows"] if flow.get("id") != flow_id]
    if flow_id in scheduled:
        scheduled[flow_id].cancel()
        scheduled.pop(flow_id, None)
    write_db(db)
    return {"ok": True}


async def _execute_flow(body: dict[str, Any], on_event: Any | None = None) -> list[dict[str, Any]]:
    db = seed_db(read_db())
    return await run_flow(
        flow=body.get("flow") or [],
        agents=_filter_iot(body.get("agents") or db["agents"]),
        skills=_filter_iot(body.get("skills") or db["skills"]),
        mcps=_filter_iot(body.get("mcps") or db["mcps"]),
        task=body.get("task") or "",
        loops=body.get("loops") or 1,
        workspace_root=body.get("workspaceRoot") or config.WORKSPACE_ROOT or "",
        loop_groups=body.get("loopGroups") or [],
        runtime_settings=get_runtime_settings(db),
        on_event=on_event,
    )


@app.post("/api/flows/run")
async def run_flow_route(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        db = seed_db(read_db())
        logs = await _execute_flow(body)
        run = {"id": str(uuid.uuid4()), "createdAt": iso_now(), "logs": logs}
        db["runs"].append(run)
        write_db(db)
        return ok({"ok": True, "runId": run["id"], "logs": logs})
    except Exception as exc:
        return error(str(exc), 500)


@app.post("/api/flows/run/stream")
async def run_flow_stream(request: Request) -> StreamingResponse:
    body = await request.json()

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def send(event: dict[str, Any]) -> None:
            await queue.put({"at": iso_now(), **event})

        async def worker() -> None:
            try:
                db = seed_db(read_db())
                await send({"type": "server", "message": "Backend accepted run request."})
                logs = await _execute_flow(body, on_event=send)
                run = {"id": str(uuid.uuid4()), "createdAt": iso_now(), "logs": logs}
                db["runs"].append(run)
                write_db(db)
                await send({"type": "saved", "runId": run["id"], "message": "Run saved to history."})
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await send({"type": "stopped", "message": "Backend run cancelled."})
                raise
            except Exception as exc:
                await send({"type": "error", "error": str(exc)})
            finally:
                await queue.put(None)

        worker_task = asyncio.create_task(worker())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            if not worker_task.done():
                worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker_task

    return StreamingResponse(events(), media_type="application/x-ndjson; charset=utf-8")


@app.get("/api/runs")
async def runs() -> list[dict[str, Any]]:
    db = seed_db(read_db())
    return list(reversed(db["runs"][-30:]))


@app.post("/api/actions/http")
async def http_action(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        method = str(body.get("method") or "GET").upper()
        url = body.get("url")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return error(f"HTTP method is not allowed: {method}", 400)
        if not _allowed_host(url, config.HTTP_ACTION_ALLOWED_HOSTS):
            return error("HTTP actions are disabled or host is not in HTTP_ACTION_ALLOWED_HOSTS", 403)
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request(
                method,
                url,
                headers=body.get("headers") or {},
                json=body.get("body") if body.get("body") is not None else None,
            )
        return ok({"ok": response.is_success, "status": response.status_code, "text": response.text[:10000]})
    except Exception as exc:
        return error(str(exc), 500)


@app.post("/api/actions/email/send")
async def email_send(request: Request) -> JSONResponse:
    if not config.EMAIL_ACTION_ENABLED:
        return error("Email actions are disabled by EMAIL_ACTION_ENABLED=false", 403)
    try:
        return ok({"ok": True, "result": send_email(await request.json())})
    except Exception as exc:
        return error(str(exc), 500)
