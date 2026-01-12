from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, List

from pydantic import BaseModel, Field


class MemoryKind(str, Enum):
    PREFERENCE = "preference"
    FACT = "fact"
    DECISION = "decision"
    TODO = "todo"
    PITFALL = "pitfall"
    WORKFLOW = "workflow"
    REFERENCE = "reference"


class Message(BaseModel):
    content: str
    role: str | None = None
    surface: str | None = None
    type: str | None = None


class TurnEvent(BaseModel):
    thread_id: str
    turn_id: str
    cwd: str
    input_messages: List[Message] = Field(default_factory=list)
    assistant_message: Message
    surface: str | None = None
    ts_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_event_payload(cls, payload: dict[str, Any]) -> "TurnEvent":
        """Normalize Codex notify JSON into a TurnEvent."""
        cwd = payload.get("cwd") or ""
        thread_id = payload.get("thread-id") or payload.get("thread_id") or ""
        turn_id = payload.get("turn-id") or payload.get("turn_id") or ""
        surface = payload.get("surface")
        ts_value = payload.get("ts_utc") or payload.get("timestamp")
        ts_utc = _parse_datetime(ts_value) if ts_value else datetime.now(timezone.utc)

        raw_inputs = payload.get("input-messages") or payload.get("input_messages") or []
        if not isinstance(raw_inputs, (list, tuple)):
            raw_inputs = [raw_inputs]
        input_messages = [
            Message(**_coerce_message(item, default_role="user")) for item in raw_inputs
        ]

        last_assistant = payload.get("last-assistant-message") or payload.get(
            "last_assistant_message"
        )
        if last_assistant is None:
            raise ValueError("missing last assistant message in notify payload")
        assistant_message = Message(**_coerce_message(last_assistant, default_role="assistant"))

        return cls(
            thread_id=str(thread_id),
            turn_id=str(turn_id),
            cwd=str(cwd),
            surface=surface,
            input_messages=input_messages,
            assistant_message=assistant_message,
            ts_utc=ts_utc,
        )

    def content_hash(self) -> str:
        normalized_inputs = [m.content.strip() for m in self.input_messages]
        parts = [
            self.thread_id.strip(),
            self.turn_id.strip(),
            self.cwd.strip(),
            self.assistant_message.content.strip(),
            json.dumps(normalized_inputs, ensure_ascii=False),
        ]
        joined = "|".join(parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass
class MemoryCandidate:
    kind: MemoryKind
    text: str
    importance: int = 3
    tags: tuple[str, ...] = ()


def _coerce_message(value: Any, default_role: str | None) -> dict[str, Any]:
    if isinstance(value, str):
        return {"content": value, "role": default_role}
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, list):
            content_str = "\n".join(_flatten_content_fragments(content))
        else:
            content_str = str(content or "")
        role = value.get("role") or default_role
        return {
            "content": content_str,
            "role": role,
            "surface": value.get("surface"),
            "type": value.get("type"),
        }
    return {"content": str(value), "role": default_role}


def _flatten_content_fragments(chunks: Iterable[Any]) -> Iterable[str]:
    for chunk in chunks:
        if isinstance(chunk, str):
            yield chunk
        elif isinstance(chunk, dict) and "text" in chunk:
            yield str(chunk["text"])
        else:
            yield str(chunk)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        return datetime.fromisoformat(str(value)).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)
