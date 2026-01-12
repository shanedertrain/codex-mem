from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from codex_mem.paths import ensure_base_dir, spool_path


def append(payload: dict[str, Any]) -> None:
    ensure_base_dir()
    path = spool_path()
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload))
        fp.write("\n")


def read_all(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or spool_path()
    if not target.exists():
        return []
    entries: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def clear(path: Path | None = None) -> None:
    target = path or spool_path()
    if target.exists():
        target.unlink()


def reconcile(
    entries: Iterable[dict[str, Any]],
    ingest_func,
) -> dict[str, int]:
    """Replay spool entries using ingest_func(payload) -> bool."""
    success = 0
    failures = 0
    for entry in entries:
        try:
            if ingest_func(entry):
                success += 1
            else:
                failures += 1
        except Exception:
            failures += 1
    return {"success": success, "failures": failures}
