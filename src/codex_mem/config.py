from __future__ import annotations

import os
from typing import List

from pydantic import BaseModel, Field, ValidationError

from codex_mem.paths import DEFAULT_ROOT_MARKERS


class Settings(BaseModel):
    root_markers: List[str] = Field(default_factory=lambda: DEFAULT_ROOT_MARKERS.copy())
    remote_enabled: bool = False
    extra_redact_patterns: List[str] = Field(default_factory=list)
    allow_globs: List[str] = Field(default_factory=list)
    deny_globs: List[str] = Field(default_factory=list)
    max_memories_per_turn: int = 5
    merge_threshold: float = 0.82
    spool_enabled: bool = True
    max_recall_items: int = 12
    include_global_by_default: bool = True
    remote_model: str | None = None
    max_remote_chars: int = 5000

    model_config = {"extra": "ignore"}

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        try:
            return cls(
                root_markers=_parse_csv(
                    env.get("CODEX_MEM_ROOT_MARKERS"), fallback=DEFAULT_ROOT_MARKERS
                ),
                remote_enabled=_parse_bool(env.get("CODEX_MEM_REMOTE", "0")),
                extra_redact_patterns=_parse_csv(env.get("CODEX_MEM_REDACT_PATTERNS")),
                allow_globs=_parse_csv(env.get("CODEX_MEM_ALLOW")),
                deny_globs=_parse_csv(env.get("CODEX_MEM_DENY")),
                max_memories_per_turn=_parse_int(env.get("CODEX_MEM_MAX_PER_TURN"), default=5),
                merge_threshold=_parse_float(env.get("CODEX_MEM_MERGE_THRESHOLD"), default=0.82),
                spool_enabled=_parse_bool(env.get("CODEX_MEM_SPOOL_ENABLED", "1")),
                max_recall_items=_parse_int(env.get("CODEX_MEM_MAX_RECALL"), default=12),
                include_global_by_default=_parse_bool(env.get("CODEX_MEM_INCLUDE_GLOBAL", "1")),
                remote_model=env.get("CODEX_MEM_REMOTE_MODEL"),
                max_remote_chars=_parse_int(env.get("CODEX_MEM_REMOTE_MAX_CHARS"), default=5000),
            )
        except ValidationError as exc:
            raise RuntimeError(f"Invalid codex-mem settings: {exc}") from exc


def _parse_csv(value: str | None, fallback: list[str] | None = None) -> list[str]:
    if not value:
        return list(fallback or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default
