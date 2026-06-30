from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import DATA_DIR


def _load_json(name: str) -> dict[str, Any]:
    with (DATA_DIR / name).open("r", encoding="utf-8") as file:
        return json.load(file)


_DEFAULT = _load_json("default_registry.json")
_ADVANCED = _load_json("advanced_registry.json")


def default_agents() -> list[dict[str, Any]]:
    return deepcopy(_DEFAULT.get("agents", []))


def default_skills() -> list[dict[str, Any]]:
    return deepcopy(_DEFAULT.get("skills", []))


def default_mcps() -> list[dict[str, Any]]:
    return deepcopy(_DEFAULT.get("mcps", []))


def default_flows() -> list[dict[str, Any]]:
    return deepcopy(_DEFAULT.get("flows", []))


def advanced_agents() -> list[dict[str, Any]]:
    return deepcopy(_ADVANCED.get("agents", []))


def advanced_skills() -> list[dict[str, Any]]:
    return deepcopy(_ADVANCED.get("skills", []))


def advanced_mcps() -> list[dict[str, Any]]:
    return deepcopy(_ADVANCED.get("mcps", []))


def advanced_flows() -> list[dict[str, Any]]:
    return deepcopy(_ADVANCED.get("flows", []))

