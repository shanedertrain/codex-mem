from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from fastmcp.exceptions import ToolError  # type: ignore
from fastmcp.server import FastMCP  # type: ignore

from codex_mem.config import Settings
from codex_mem.models import MemoryCandidate, MemoryKind
from codex_mem.paths import detect_project_root
from codex_mem.store import Store

mcp = FastMCP("codex-mem")
_store: Store | None = None
_settings: Settings | None = None


def _get_store() -> tuple[Store, Settings]:
    global _store, _settings
    if _store is None or _settings is None:
        _settings = Settings.from_env()
        _store = Store(_settings)
    return _store, _settings


def _parse_kinds(kinds: Sequence[str] | None) -> list[MemoryKind] | None:
    if not kinds:
        return None
    parsed: list[MemoryKind] = []
    for kind in kinds:
        try:
            parsed.append(MemoryKind(kind))
        except ValueError:
            continue
    return parsed


def _project_root_from_cwd(cwd: str, settings: Settings) -> Path | None:
    return detect_project_root(Path(cwd), settings.root_markers)


def _format_context_pack(rows: Iterable[dict]) -> str:
    by_kind: dict[str, list[dict]] = {}
    for row in rows:
        by_kind.setdefault(row["kind"], []).append(row)
    lines = ["### Relevant memories"]
    for kind, items in by_kind.items():
        lines.append(f"#### {kind}")
        for item in items:
            prefix = "[pinned]" if item["is_pinned"] else ""
            lines.append(f"- {prefix}[id:{item['id']}] {item['text']}")
    return "\n".join(lines)


def mem_recall(
    prompt: str,
    cwd: str,
    limit: int = 12,
    include_global: bool = True,
    kinds: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    """Return a context pack of memories relevant to prompt and cwd."""
    store, settings = _get_store()
    project_root = _project_root_from_cwd(cwd, settings)
    parsed_kinds = _parse_kinds(kinds)
    rows = store.search(
        query=prompt,
        project_root=project_root,
        limit=min(limit, settings.max_recall_items),
        include_global=include_global
        if include_global is not None
        else settings.include_global_by_default,
        kinds=parsed_kinds,
        tags=tags,
    )
    return _format_context_pack(rows)


def mem_search(
    query: str,
    cwd: str | None = None,
    limit: int = 20,
    kinds: list[str] | None = None,
    tags: list[str] | None = None,
) -> list[dict]:
    """Search memories."""
    store, settings = _get_store()
    project_root = _project_root_from_cwd(cwd, settings) if cwd else None
    parsed_kinds = _parse_kinds(kinds)
    return store.search(
        query=query,
        project_root=project_root,
        limit=limit,
        include_global=settings.include_global_by_default if project_root else True,
        kinds=parsed_kinds,
        tags=tags,
    )


def mem_add(
    text: str,
    kind: str = "fact",
    cwd: str | None = None,
    project_scoped: bool = True,
    importance: int = 3,
    tags: list[str] | None = None,
) -> dict:
    """Add a memory."""
    store, settings = _get_store()
    try:
        mem_kind = MemoryKind(kind)
    except ValueError as exc:
        raise ToolError(f"Unknown kind: {kind}") from exc

    project_root = _project_root_from_cwd(cwd, settings) if project_scoped and cwd else None
    candidate = MemoryCandidate(
        kind=mem_kind, text=text, importance=importance, tags=tuple(tags or [])
    )
    mem_id = store.add_memory(candidate, project_root=project_root)
    return {"id": mem_id}


def mem_forget(memory_id: int) -> dict:
    """Soft delete a memory."""
    store, _ = _get_store()
    ok = store.soft_delete(memory_id)
    return {"ok": ok}


def mem_update(
    memory_id: int,
    text: str | None = None,
    importance: int | None = None,
    is_pinned: bool | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Update a memory."""
    store, _ = _get_store()
    ok = store.update_memory(
        memory_id, text=text, importance=importance, is_pinned=is_pinned, tags=tags
    )
    return {"ok": ok}


def mem_stats() -> dict:
    """Return counts and db path."""
    store, _ = _get_store()
    return store.stats()


def run() -> None:
    _get_store()
    _register_tools()
    mcp.run()


def _register_tools() -> None:
    for func in (mem_recall, mem_search, mem_add, mem_forget, mem_update, mem_stats):
        mcp.tool()(func)


if __name__ == "__main__":  # pragma: no cover
    run()
