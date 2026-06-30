from __future__ import annotations

import subprocess
from pathlib import Path

from . import config


MAX_FILE_BYTES = 250_000
DEFAULT_IGNORES = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "coverage",
    ".cache",
    ".venv",
    "vendor",
    "__pycache__",
}


def resolve_workspace_root(input_root: str | None = None) -> Path:
    root = input_root or config.WORKSPACE_ROOT or "."
    return Path(root).expanduser().resolve()


def safe_resolve(root: str | None, target: str = ".") -> Path:
    abs_root = resolve_workspace_root(root)
    abs_target = (abs_root / (target or ".")).resolve()
    try:
        abs_target.relative_to(abs_root)
    except ValueError as exc:
        raise ValueError("Path is outside WORKSPACE_ROOT") from exc
    return abs_target


def scan_folder(root: str | None, rel: str = ".", depth: int = 3) -> str:
    start = safe_resolve(root, rel)
    workspace_root = resolve_workspace_root(root)
    lines: list[str] = []

    def walk(current: Path, level: int) -> None:
        if level > depth:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            entries = []
        for entry in entries[:120]:
            if entry.name in DEFAULT_IGNORES:
                continue
            rel_path = entry.resolve().relative_to(workspace_root)
            icon = "DIR" if entry.is_dir() else "FILE"
            lines.append(f"{'  ' * level}{icon} {rel_path}")
            if entry.is_dir():
                walk(entry, level + 1)

    walk(start, 0)
    return "\n".join(lines) or "(empty folder or not readable)"


def read_text_file(root: str | None, rel: str) -> str:
    file_path = safe_resolve(root, rel)
    stat = file_path.stat()
    if stat.st_size > MAX_FILE_BYTES:
        raise ValueError(f"File too large: {stat.st_size} bytes")
    return file_path.read_text(encoding="utf-8")


def write_text_file(root: str | None, rel: str, content: str) -> str:
    file_path = safe_resolve(root, rel)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return str(file_path.relative_to(resolve_workspace_root(root)))


def _git(root: str | None, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=resolve_workspace_root(root),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        return (result.stdout or result.stderr or "").strip()
    except Exception as exc:
        return f"git {' '.join(args)} failed: {exc}"


def git_info(root: str | None) -> dict[str, str]:
    return {
        "status": _git(root, ["status", "--short"]),
        "branch": _git(root, ["branch", "--show-current"]),
        "lastCommit": _git(root, ["log", "-1", "--oneline"]),
        "diff": _git(root, ["diff", "--stat"]),
    }

