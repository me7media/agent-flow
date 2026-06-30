from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "agent_flow.sqlite3"
LEGACY_DB_FILE = DATA_DIR / "db.json"
MIGRATIONS_DIR = BASE_DIR / "migrations"

load_dotenv(PROJECT_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


PORT = int(os.getenv("PORT", "8787"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "openai" if OPENAI_API_KEY else "mock")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "./workspace")
AGENT_ALLOW_DIRECT_FILE_WRITES = env_bool("AGENT_ALLOW_DIRECT_FILE_WRITES")
IOT_ENABLED = env_bool("IOT_ENABLED", True)
IOT_DEVICE_ACTIONS_ENABLED = env_bool("IOT_DEVICE_ACTIONS_ENABLED", False)
IOT_ALLOWED_HOSTS = env_list("IOT_ALLOWED_HOSTS")
IOT_DISCOVERY_MAX_HOSTS = int(os.getenv("IOT_DISCOVERY_MAX_HOSTS", "32"))
CORS_ORIGINS = env_list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
HTTP_ACTION_ALLOWED_HOSTS = env_list("HTTP_ACTION_ALLOWED_HOSTS")
EMAIL_ACTION_ENABLED = env_bool("EMAIL_ACTION_ENABLED", False)
