from __future__ import annotations

from pathlib import Path
from typing import Iterable

DEFAULT_ROOT_MARKERS = [".git"]


def codex_home() -> Path:
    """Return the codex home directory."""
    env_home = Path.home()
    override = getenv_path("CODEX_HOME")
    if override is not None:
        return override
    return env_home / ".codex"


def mem_base_dir() -> Path:
    """Base directory for codex-mem artifacts."""
    override = getenv_path("CODEX_MEM_HOME")
    if override is not None:
        return override
    return codex_home() / "mem"


def db_path() -> Path:
    return mem_base_dir() / "mem.sqlite3"


def log_path() -> Path:
    return mem_base_dir() / "notify.log"


def spool_path() -> Path:
    return mem_base_dir() / "notify_spool.jsonl"


def ensure_base_dir() -> Path:
    base = mem_base_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base


def detect_project_root(cwd: Path, markers: Iterable[str]) -> Path | None:
    """Walk upward from cwd to find a directory containing any marker file/dir."""
    current = cwd.resolve()
    for parent in [current, *current.parents]:
        for marker in markers:
            if (parent / marker).exists():
                return parent
    return None


def getenv_path(key: str) -> Path | None:
    import os

    value = os.environ.get(key)
    if value:
        return Path(value).expanduser()
    return None
