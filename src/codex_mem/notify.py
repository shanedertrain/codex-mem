from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from codex_mem.config import Settings
from codex_mem.extractor import extract_memories
from codex_mem.models import TurnEvent
from codex_mem.paths import detect_project_root, log_path
from codex_mem.redact import redact_text
from codex_mem.spool import append as spool_append
from codex_mem.store import Store

logger = logging.getLogger("codex_mem.notify")


def configure_logging() -> None:
    log_file = log_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def ingest_event(payload: dict[str, Any], settings: Settings, store: Store) -> bool:
    turn = TurnEvent.from_event_payload(payload)
    turn = _redact_turn(turn, settings)

    project_root = detect_project_root(Path(turn.cwd), settings.root_markers)
    if not _is_allowed(Path(turn.cwd), settings):
        logger.info("cwd %s denied by allow/deny globs", turn.cwd)
        return False

    content_hash = turn.content_hash()
    try:
        turn_id = store.insert_turn(turn, project_root, content_hash)
    except sqlite3.OperationalError as exc:
        logger.warning("DB write failed, spooling: %s", exc)
        if settings.spool_enabled:
            spool_append({"payload": turn.model_dump(mode="json")})
        return False

    if turn_id is None:
        logger.info("deduped turn %s/%s", turn.thread_id, turn.turn_id)
        return True

    candidates = extract_memories(turn, settings)
    for candidate in candidates:
        try:
            store.add_memory(candidate, project_root, turn_id)
        except sqlite3.OperationalError as exc:
            logger.warning("memory insert failed, spooling: %s", exc)
            if settings.spool_enabled:
                spool_append({"payload": turn.model_dump(mode="json")})
            return False
    return True


def _redact_turn(turn: TurnEvent, settings: Settings) -> TurnEvent:
    redacted_inputs = [
        msg.model_copy(update={"content": redact_text(msg.content, settings.extra_redact_patterns)})
        for msg in turn.input_messages
    ]
    redacted_assistant = turn.assistant_message.model_copy(
        update={
            "content": redact_text(turn.assistant_message.content, settings.extra_redact_patterns)
        }
    )
    return turn.model_copy(
        update={"input_messages": redacted_inputs, "assistant_message": redacted_assistant}
    )


def _is_allowed(cwd: Path, settings: Settings) -> bool:
    from fnmatch import fnmatch

    if settings.allow_globs:
        if not any(fnmatch(str(cwd), pattern) for pattern in settings.allow_globs):
            return False
    if settings.deny_globs:
        if any(fnmatch(str(cwd), pattern) for pattern in settings.deny_globs):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Usage: codex-mem-notify <json-payload>", file=sys.stderr)
        return 1
    configure_logging()
    try:
        payload = json.loads(argv[0])
    except json.JSONDecodeError:
        logger.error("invalid JSON payload")
        return 1

    settings = Settings.from_env()
    store = Store(settings)
    try:
        ok = ingest_event(payload, settings, store)
        return 0 if ok else 1
    finally:
        store.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
