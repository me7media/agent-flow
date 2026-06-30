from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Callable

from .config import DB_FILE
from .registry import default_agents, default_mcps, default_skills


def initial_db() -> dict[str, Any]:
    return {
        "agents": default_agents(),
        "skills": default_skills(),
        "mcps": default_mcps(),
        "flows": [],
        "runs": [],
    }


def read_db() -> dict[str, Any]:
    try:
        with DB_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        db = initial_db()
        write_db(db)
        return deepcopy(db)


def write_db(db: dict[str, Any]) -> None:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DB_FILE.open("w", encoding="utf-8") as file:
        json.dump(db, file, ensure_ascii=False, indent=2)


def patch_db(mutator: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
    db = read_db()
    next_db = mutator(db) or db
    write_db(next_db)
    return next_db

