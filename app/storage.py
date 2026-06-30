from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Callable

from .config import LEGACY_DB_FILE
from .database import read_state, write_state
from .settings_service import default_runtime_settings
from .registry import default_agents, default_mcps, default_skills


def initial_db() -> dict[str, Any]:
    return {
        "agents": default_agents(),
        "skills": default_skills(),
        "mcps": default_mcps(),
        "flows": [],
        "runs": [],
        "settings": [default_runtime_settings()],
    }


def read_db() -> dict[str, Any]:
    db = read_state()
    if not any(db.get(key) for key in ("agents", "skills", "mcps", "flows", "runs", "savedSequences", "settings")):
        if LEGACY_DB_FILE.exists():
            try:
                db = json.loads(LEGACY_DB_FILE.read_text(encoding="utf-8"))
                write_db(db)
                return db
            except Exception:
                pass
        db = initial_db()
        write_db(db)
        return deepcopy(db)
    db.setdefault("agents", [])
    db.setdefault("skills", [])
    db.setdefault("mcps", [])
    db.setdefault("flows", [])
    db.setdefault("runs", [])
    db.setdefault("savedSequences", [])
    db.setdefault("settings", [default_runtime_settings()])
    return db


def write_db(db: dict[str, Any]) -> None:
    write_state(db)


def patch_db(mutator: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
    db = read_db()
    next_db = mutator(db) or db
    write_db(next_db)
    return next_db
