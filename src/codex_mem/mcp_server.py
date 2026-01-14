from __future__ import annotations

import logging
import sys
import time
from importlib import metadata
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable, Sequence

from fastmcp.exceptions import ToolError  # type: ignore
from fastmcp.server import FastMCP  # type: ignore

from codex_mem.config import Settings, log_level_from_env
from codex_mem.models import MemoryCandidate, MemoryKind
from codex_mem.paths import detect_project_root, ensure_mcp_dir, mcp_log_path
from codex_mem.store import Store

mcp = FastMCP("codex-mem")
_store: Store | None = None
_settings: Settings | None = None
logger = logging.getLogger("codex_mem.mcp_server")
_logging_configured = False
_log_file: Path | None = None
_configured_handlers: list[logging.Handler] = []


def _get_store() -> tuple[Store, Settings]:
    global _store, _settings
    if _store is None or _settings is None:
        _settings = Settings.from_env()
        _store = Store(_settings)
    return _store, _settings


def _clear_configured_handlers() -> None:
    """Remove handlers we attached to the root logger."""
    global _configured_handlers
    root_logger = logging.getLogger()
    for handler in _configured_handlers:
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    _configured_handlers = []


def setup_logging(force: bool = False) -> Path | None:
    """Configure console + rotating file logging with UTC timestamps."""
    global _logging_configured, _log_file
    if _logging_configured and not force:
        return _log_file

    if force:
        _clear_configured_handlers()
        _logging_configured = False
        _log_file = None

    log_level = log_level_from_env()
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    logger.setLevel(log_level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    formatter.converter = time.gmtime

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    _configured_handlers.append(stream_handler)

    log_path = mcp_log_path()
    try:
        ensure_mcp_dir()
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        _configured_handlers.append(file_handler)
        _log_file = log_path
    except Exception as exc:
        _log_file = None
        logger.warning(
            "Failed to set up file logging at %s: %s; continuing with console only",
            log_path,
            exc,
        )

    _logging_configured = True
    return _log_file


def _reset_logging_for_tests() -> None:
    """Reset logging state so tests can reconfigure cleanly."""
    global _logging_configured, _log_file
    _clear_configured_handlers()
    _logging_configured = False
    _log_file = None


def _handler_is_closed(handler: logging.Handler) -> bool:
    stream = getattr(handler, "stream", None)
    if stream is not None:
        return bool(getattr(stream, "closed", False))
    console = getattr(handler, "console", None)
    if console is not None:
        file = getattr(console, "file", None)
        return bool(getattr(file, "closed", False))
    return False


def _prune_closed_handlers() -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if _handler_is_closed(handler):
            root_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass


def _wants_help(argv: Sequence[str]) -> bool:
    return any(arg in {"-h", "--help"} for arg in argv)


def _print_help() -> None:
    sys.stdout.write(
        "codex-mem-serve runs the codex-mem MCP server over stdio.\n"
        "Usage: codex-mem-serve\n"
        "Other commands: codex-mem --help\n"
    )


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


def _stdio_closed() -> bool:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and getattr(stream, "closed", False):
            return True
    return False


def _package_version() -> str:
    try:
        return metadata.version("codex-mem")
    except metadata.PackageNotFoundError:
        return "unknown"


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


def run(transport: str = "stdio") -> None:
    if _wants_help(sys.argv[1:]):
        _print_help()
        return
    log_file = setup_logging(force=True)
    store = None
    try:
        store, settings = _get_store()
        _register_tools()
        logger.info(
            "codex-mem starting transport=%s level=%s log_file=%s cwd=%s version=%s "
            "host=%s port=%s remote_enabled=%s spool_enabled=%s",
            transport,
            logging.getLevelName(logging.getLogger().level),
            log_file or "stdout-only",
            Path.cwd(),
            _package_version(),
            mcp.settings.host,
            mcp.settings.port,
            settings.remote_enabled,
            settings.spool_enabled,
        )
        mcp.run(transport=transport)
    except Exception:
        logger.exception("codex-mem encountered a fatal error")
        raise
    finally:
        global _store, _settings
        if store:
            store.close()
        _store = None
        _settings = None
        # stdio transport can close streams before shutdown logging runs.
        _prune_closed_handlers()
        if transport != "stdio" or not _stdio_closed():
            prev_raise = logging.raiseExceptions
            logging.raiseExceptions = False
            try:
                logger.info("codex-mem stopping")
            finally:
                logging.raiseExceptions = prev_raise


def _register_tools() -> None:
    for func in (mem_recall, mem_search, mem_add, mem_forget, mem_update, mem_stats):
        mcp.tool()(func)


if __name__ == "__main__":  # pragma: no cover
    run()
