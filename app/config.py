from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "db.json"

load_dotenv(PROJECT_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


PORT = int(os.getenv("PORT", "8787"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "./workspace")
AGENT_ALLOW_DIRECT_FILE_WRITES = env_bool("AGENT_ALLOW_DIRECT_FILE_WRITES")

