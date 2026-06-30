from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import config
from .emailer import send_email
from .registry import advanced_agents, advanced_flows, advanced_mcps, advanced_skills, default_agents, default_flows, default_mcps, default_skills
from .runner import run_flow
from .storage import read_db, write_db
from .workspace import git_info, read_text_file, resolve_workspace_root, scan_folder, write_text_file


app = FastAPI(title="Agent Flow Python API")
scheduled: dict[str, asyncio.Task[None]] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def seed_db(db: dict[str, Any]) -> dict[str, Any]:
    db["agents"] = merge_by_id(db.get("agents"), [*default_agents(), *advanced_agents()])
    db["skills"] = merge_by_id(db.get("skills"), [*default_skills(), *advanced_skills()])
    db["mcps"] = merge_by_id(db.get("mcps"), [*default_mcps(), *advanced_mcps()])
    db["flows"] = merge_by_id(db.get("flows"), [*default_flows(), *advanced_flows()])
    db.setdefault("runs", [])
    db.setdefault("savedSequences", [])
    return db


def cron_field_matches(field: str | None, value: int, minimum: int, maximum: int) -> bool:
    if not field or field == "*":
        return True
    for part in str(field).split(","):
        if "/" in part:
            base, step_text = part.split("/", 1)
            try:
                step = int(step_text)
                start = minimum if base == "*" else int(base)
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
    return len(str(expr or "").strip().split()) == 5


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
                agents=db["agents"],
                skills=db["skills"],
                mcps=db["mcps"],
                task=flow.get("task") or "",
                loops=flow.get("loops"),
                workspace_root=flow.get("workspaceRoot") or config.WORKSPACE_ROOT or "",
                loop_groups=flow.get("loopGroups") or [],
            )
            db["runs"].append({"id": str(uuid.uuid4()), "flowId": flow_id, "createdAt": iso_now(), "logs": logs})
            write_db(db)

    scheduled[flow_id] = asyncio.create_task(job())
    return True


def ok(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status_code)


def error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "provider": "openai" if config.OPENAI_API_KEY else "mock",
        "workspaceRoot": str(resolve_workspace_root(config.WORKSPACE_ROOT)),
    }


@app.get("/api/registry")
async def registry() -> dict[str, Any]:
    db = seed_db(read_db())
    write_db(db)
    return {"agents": db["agents"], "skills": db["skills"], "mcps": db["mcps"]}


@app.get("/api/agents")
async def agents() -> list[dict[str, Any]]:
    return seed_db(read_db())["agents"]


@app.post("/api/agents")
async def save_agent(request: Request) -> dict[str, Any]:
    body = await request.json()
    db = seed_db(read_db())
    agent = {**body, "id": body.get("id") or str(uuid.uuid4()), "updatedAt": iso_now()}
    db["agents"] = [item for item in db["agents"] if item.get("id") != agent["id"]] + [agent]
    write_db(db)
    return {"ok": True, "agent": agent}


@app.get("/api/flows")
async def flows() -> list[dict[str, Any]]:
    return seed_db(read_db())["flows"]


@app.post("/api/flows")
async def save_flow(request: Request) -> dict[str, Any]:
    body = await request.json()
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


@app.post("/api/flows/run")
async def run_flow_route(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        db = seed_db(read_db())
        logs = await run_flow(
            flow=body.get("flow") or [],
            agents=body.get("agents") or db["agents"],
            skills=body.get("skills") or db["skills"],
            mcps=body.get("mcps") or db["mcps"],
            task=body.get("task") or "",
            loops=body.get("loops") or 1,
            workspace_root=body.get("workspaceRoot") or config.WORKSPACE_ROOT or "",
            loop_groups=body.get("loopGroups") or [],
        )
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
                logs = await run_flow(
                    flow=body.get("flow") or [],
                    agents=body.get("agents") or db["agents"],
                    skills=body.get("skills") or db["skills"],
                    mcps=body.get("mcps") or db["mcps"],
                    task=body.get("task") or "",
                    loops=body.get("loops") or 1,
                    workspace_root=body.get("workspaceRoot") or config.WORKSPACE_ROOT or "",
                    loop_groups=body.get("loopGroups") or [],
                    on_event=send,
                )
                run = {"id": str(uuid.uuid4()), "createdAt": iso_now(), "logs": logs}
                db["runs"].append(run)
                write_db(db)
                await send({"type": "saved", "runId": run["id"], "message": "Run saved to history."})
            except Exception as exc:
                await send({"type": "error", "error": str(exc)})
            finally:
                await queue.put(None)

        asyncio.create_task(worker())
        while True:
            event = await queue.get()
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson; charset=utf-8")


@app.get("/api/runs")
async def runs() -> list[dict[str, Any]]:
    db = seed_db(read_db())
    return list(reversed(db["runs"][-30:]))


@app.post("/api/workspace/scan")
async def workspace_scan(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        workspace_root = body.get("workspaceRoot") or config.WORKSPACE_ROOT
        return ok(
            {
                "ok": True,
                "root": str(resolve_workspace_root(workspace_root)),
                "tree": scan_folder(workspace_root, body.get("path") or ".", body.get("depth") or 3),
            }
        )
    except Exception as exc:
        return error(str(exc), 400)


@app.post("/api/workspace/read")
async def workspace_read(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        return ok({"ok": True, "path": body.get("path"), "content": read_text_file(body.get("workspaceRoot") or config.WORKSPACE_ROOT, body.get("path"))})
    except Exception as exc:
        return error(str(exc), 400)


@app.post("/api/workspace/write")
async def workspace_write(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        written = write_text_file(body.get("workspaceRoot") or config.WORKSPACE_ROOT, body.get("path"), body.get("content") or "")
        return ok({"ok": True, "path": written})
    except Exception as exc:
        return error(str(exc), 400)


@app.post("/api/git/info")
async def git_info_route(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        return ok({"ok": True, "git": git_info(body.get("workspaceRoot") or config.WORKSPACE_ROOT or "")})
    except Exception as exc:
        return error(str(exc), 400)


@app.post("/api/actions/http")
async def http_action(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(
                body.get("method") or "GET",
                body.get("url"),
                headers=body.get("headers") or {},
                json=body.get("body") if body.get("body") is not None else None,
            )
        return ok({"ok": response.is_success, "status": response.status_code, "text": response.text[:10000]})
    except Exception as exc:
        return error(str(exc), 500)


@app.post("/api/actions/email/send")
async def email_send(request: Request) -> JSONResponse:
    try:
        return ok({"ok": True, "result": send_email(await request.json())})
    except Exception as exc:
        return error(str(exc), 500)
