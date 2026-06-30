from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import DB_FILE, MIGRATIONS_DIR


COLLECTIONS = {
    "agents": "agents",
    "skills": "skills",
    "mcps": "mcps",
    "flows": "flows",
    "savedSequences": "saved_sequences",
    "settings": "settings",
}


def connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _load(value: str) -> dict[str, Any]:
    return json.loads(value)


def _sync_collection(connection: sqlite3.Connection, table: str, items: list[dict[str, Any]]) -> None:
    ids = [item.get("id") for item in items if item.get("id")]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        connection.execute(f"DELETE FROM {table} WHERE id NOT IN ({placeholders})", ids)
    else:
        connection.execute(f"DELETE FROM {table}")

    for position, item in enumerate(items):
        item_id = item.get("id")
        if not item_id:
            continue
        connection.execute(
            f"""
            INSERT INTO {table} (id, name, payload, position, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
              name = excluded.name,
              payload = excluded.payload,
              position = excluded.position,
              updated_at = CURRENT_TIMESTAMP
            """,
            (item_id, item.get("name") or item_id, _dump(item), position),
        )


def _read_collection(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = connection.execute(f"SELECT payload FROM {table} ORDER BY position ASC, rowid ASC").fetchall()
    return [_load(row["payload"]) for row in rows]


def read_state() -> dict[str, Any]:
    migrate()
    with connect() as connection:
        state = {key: _read_collection(connection, table) for key, table in COLLECTIONS.items()}
        run_rows = connection.execute("SELECT payload FROM runs ORDER BY created_at ASC, rowid ASC").fetchall()
        state["runs"] = [_load(row["payload"]) for row in run_rows]
        return state


def write_state(db: dict[str, Any]) -> None:
    migrate()
    with connect() as connection:
        for key, table in COLLECTIONS.items():
            _sync_collection(connection, table, db.get(key) or [])
        run_ids = [run.get("id") for run in db.get("runs") or [] if run.get("id")]
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            connection.execute(f"DELETE FROM runs WHERE id NOT IN ({placeholders})", run_ids)
        else:
            connection.execute("DELETE FROM runs")
        for run in db.get("runs") or []:
            run_id = run.get("id")
            if not run_id:
                continue
            connection.execute(
                """
                INSERT INTO runs (id, flow_id, created_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  flow_id = excluded.flow_id,
                  created_at = excluded.created_at,
                  payload = excluded.payload
                """,
                (run_id, run.get("flowId"), run.get("createdAt"), _dump(run)),
            )
