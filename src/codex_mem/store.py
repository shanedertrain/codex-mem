from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Sequence

from codex_mem.config import Settings
from codex_mem.models import MemoryCandidate, MemoryKind, TurnEvent
from codex_mem.paths import db_path, ensure_base_dir


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        ensure_base_dir()
        self.conn = sqlite3.connect(db_path(), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        self.conn.close()

    def _init_db(self) -> None:
        cur = self.conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY,
                thread_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                ts_utc TEXT NOT NULL,
                cwd TEXT NOT NULL,
                project_root TEXT NULL,
                input_messages_json TEXT NOT NULL,
                assistant_message TEXT NOT NULL,
                assistant_message_json TEXT NULL,
                surface TEXT NULL,
                hash TEXT UNIQUE
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY,
                ts_utc TEXT NOT NULL,
                project_root TEXT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                source_turn_id INTEGER NULL,
                importance INTEGER NOT NULL DEFAULT 1,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                tags_json TEXT NULL,
                FOREIGN KEY(source_turn_id) REFERENCES turns(id)
            );
            """
        )
        cur.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(text, project_root, kind, content='memories', content_rowid='id');
            """
        )
        # triggers to keep FTS in sync
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memory_fts(rowid, text, project_root, kind)
                VALUES (new.id, new.text, new.project_root, new.kind);
            END;
            """
        )
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                DELETE FROM memory_fts WHERE rowid = old.id;
            END;
            """
        )
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                DELETE FROM memory_fts WHERE rowid = old.id;
                INSERT INTO memory_fts(rowid, text, project_root, kind)
                VALUES (new.id, new.text, new.project_root, new.kind);
            END;
            """
        )
        self.conn.commit()

    def insert_turn(
        self, turn: TurnEvent, project_root: Path | None, content_hash: str
    ) -> int | None:
        """Insert a turn; return row id or None if deduped."""
        payload = {
            "thread_id": turn.thread_id,
            "turn_id": turn.turn_id,
            "ts_utc": turn.ts_utc.isoformat(),
            "cwd": str(turn.cwd),
            "project_root": str(project_root) if project_root else None,
            "input_messages_json": json.dumps([msg.model_dump() for msg in turn.input_messages]),
            "assistant_message": turn.assistant_message.content,
            "assistant_message_json": json.dumps(turn.assistant_message.model_dump()),
            "surface": turn.surface,
            "hash": content_hash,
        }
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO turns (
                    thread_id, turn_id, ts_utc, cwd, project_root, input_messages_json,
                    assistant_message, assistant_message_json, surface, hash
                )
                VALUES (:thread_id, :turn_id, :ts_utc, :cwd, :project_root, :input_messages_json,
                        :assistant_message, :assistant_message_json, :surface, :hash)
                """,
                payload,
            )
            self.conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def add_memory(
        self,
        candidate: MemoryCandidate,
        project_root: Path | None,
        source_turn_id: int | None = None,
    ) -> int | None:
        merged_id = self._merge_if_similar(candidate, project_root)
        if merged_id is not None:
            return merged_id
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO memories (
                ts_utc, project_root, kind, text, source_turn_id, importance, tags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                str(project_root) if project_root else None,
                candidate.kind.value,
                candidate.text.strip(),
                source_turn_id,
                candidate.importance,
                json.dumps(list(candidate.tags)) if candidate.tags else None,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _merge_if_similar(
        self, candidate: MemoryCandidate, project_root: Path | None
    ) -> int | None:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, text FROM memories
            WHERE is_deleted = 0
              AND kind = ?
              AND (project_root = ? OR (project_root IS NULL AND ? IS NULL))
            ORDER BY ts_utc DESC
            LIMIT 8
            """,
            (
                candidate.kind.value,
                str(project_root) if project_root else None,
                str(project_root) if project_root else None,
            ),
        )
        rows = cur.fetchall()
        for row in rows:
            ratio = SequenceMatcher(None, candidate.text.lower(), row["text"].lower()).ratio()
            if ratio >= self.settings.merge_threshold:
                merged_text = _merge_text(row["text"], candidate.text)
                cur.execute(
                    "UPDATE memories SET text = ?, ts_utc = ? WHERE id = ?",
                    (merged_text, datetime.now(timezone.utc).isoformat(), row["id"]),
                )
                self.conn.commit()
                return int(row["id"])
        return None

    def search(
        self,
        query: str,
        project_root: Path | None,
        limit: int,
        include_global: bool = True,
        kinds: Sequence[MemoryKind] | None = None,
        tags: Sequence[str] | None = None,
    ) -> list[dict]:
        where_parts: list[str] = ["m.is_deleted = 0"]
        params: list[str | int | None] = []

        if project_root is not None:
            scope_clauses = ["m.project_root = ?"]
            params.append(str(project_root))
            if include_global:
                scope_clauses.append("m.project_root IS NULL")
            where_parts.append("(" + " OR ".join(scope_clauses) + ")")
        else:
            if not include_global:
                where_parts.append("m.project_root IS NOT NULL")

        if kinds:
            kind_placeholders = ",".join("?" for _ in kinds)
            where_parts.append(f"m.kind IN ({kind_placeholders})")
            params.extend([kind.value for kind in kinds])

        cleaned_query = query.strip()
        use_fts = bool(cleaned_query) and cleaned_query != "*"
        where_clause = " AND ".join(where_parts) if where_parts else "1=1"
        if use_fts:
            base_sql = """
                SELECT m.id, m.ts_utc, m.project_root, m.kind, m.text,
                       m.importance, m.is_pinned, m.is_deleted, m.tags_json,
                       bm25(memory_fts) AS score
                FROM memories m
                JOIN memory_fts ON memory_fts.rowid = m.id
                WHERE memory_fts MATCH ? AND {where_clause}
                ORDER BY m.is_pinned DESC, m.importance DESC, score ASC, m.ts_utc DESC
                LIMIT ?
            """
            sql = base_sql.format(where_clause=where_clause)
            params = [_fts_query(cleaned_query)] + params + [limit]
        else:
            base_sql = """
                SELECT m.id, m.ts_utc, m.project_root, m.kind, m.text,
                       m.importance, m.is_pinned, m.is_deleted, m.tags_json,
                       0 AS score
                FROM memories m
                WHERE {where_clause}
                ORDER BY m.is_pinned DESC, m.importance DESC, m.ts_utc DESC
                LIMIT ?
            """
            sql = base_sql.format(where_clause=where_clause)
            params = params + [limit]

        cur = self.conn.cursor()
        cur.execute(sql, params)
        rows = [dict(row) for row in cur.fetchall()]
        return _filter_by_tags(rows, tags)

    def soft_delete(self, memory_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("UPDATE memories SET is_deleted = 1 WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def update_memory(
        self,
        memory_id: int,
        text: str | None = None,
        importance: int | None = None,
        is_pinned: bool | None = None,
        tags: Sequence[str] | None = None,
    ) -> bool:
        parts: list[str] = []
        params: list[object] = []
        if text is not None:
            parts.append("text = ?")
            params.append(text)
        if importance is not None:
            parts.append("importance = ?")
            params.append(importance)
        if is_pinned is not None:
            parts.append("is_pinned = ?")
            params.append(1 if is_pinned else 0)
        if tags is not None:
            parts.append("tags_json = ?")
            params.append(json.dumps(list(tags)))
        if not parts:
            return False
        params.append(memory_id)
        sql = f"UPDATE memories SET {', '.join(parts)} WHERE id = ?"
        cur = self.conn.cursor()
        cur.execute(sql, params)
        self.conn.commit()
        return cur.rowcount > 0

    def stats(self) -> dict[str, object]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT kind, project_root, COUNT(*) as count
            FROM memories
            WHERE is_deleted = 0
            GROUP BY kind, project_root
            """
        )
        counts = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT MAX(ts_utc) as last_ts FROM turns")
        last_row = cur.fetchone()
        last_ingest = last_row["last_ts"] if last_row else None
        return {
            "db_path": str(db_path()),
            "counts": counts,
            "last_ingest": last_ingest,
        }


def _merge_text(existing: str, new_text: str) -> str:
    if new_text.strip() in existing:
        return existing
    return existing.strip() + "\n- " + new_text.strip()


def _filter_by_tags(rows: list[dict], tags: Sequence[str] | None) -> list[dict]:
    if not tags:
        return rows
    filtered: list[dict] = []
    tag_set = set(tags)
    for row in rows:
        existing = set(json.loads(row["tags_json"])) if row.get("tags_json") else set()
        if tag_set.issubset(existing):
            filtered.append(row)
    return filtered


def _fts_query(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return "*"
    return cleaned.replace('"', " ")
