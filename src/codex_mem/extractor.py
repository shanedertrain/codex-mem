from __future__ import annotations

import json
import re
from typing import Iterable, List

from codex_mem.config import Settings
from codex_mem.models import MemoryCandidate, MemoryKind, TurnEvent

SENTENCE_SPLIT = re.compile(r"(?<=[.!?\n])\s+")


PREFERENCE_PATTERNS = [
    re.compile(r"\bprefer\b", re.IGNORECASE),
    re.compile(r"\balways\b", re.IGNORECASE),
    re.compile(r"\bfrom now on\b", re.IGNORECASE),
]

DECISION_PATTERNS = [
    re.compile(r"\bwe (will|decided)\b", re.IGNORECASE),
    re.compile(r"\bdecision\b", re.IGNORECASE),
    re.compile(r"\bchoose\b", re.IGNORECASE),
]

TODO_PATTERNS = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bnext\b", re.IGNORECASE),
    re.compile(r"\bfollow up\b", re.IGNORECASE),
    re.compile(r"\bneed to\b", re.IGNORECASE),
]

FACT_PATTERNS = [
    re.compile(r"\bus(e|ing)\b", re.IGNORECASE),
    re.compile(r"\brunning\b", re.IGNORECASE),
    re.compile(r"\bversion\b", re.IGNORECASE),
]

PITFALL_PATTERNS = [
    re.compile(r"\bavoid\b", re.IGNORECASE),
    re.compile(r"\bdon't\b", re.IGNORECASE),
    re.compile(r"\bissue\b", re.IGNORECASE),
    re.compile(r"\bfails?\b", re.IGNORECASE),
]

WORKFLOW_PATTERNS = [
    re.compile(r"\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bprocess\b", re.IGNORECASE),
    re.compile(r"\bsteps\b", re.IGNORECASE),
]

REFERENCE_PATTERNS = [
    re.compile(r"\bsee\b", re.IGNORECASE),
    re.compile(r"\bref(erence)?\b", re.IGNORECASE),
    re.compile(r"\bdoc\b", re.IGNORECASE),
    re.compile(r"\burl\b", re.IGNORECASE),
]


def extract_memories(turn: TurnEvent, settings: Settings) -> List[MemoryCandidate]:
    if settings.remote_enabled:
        remote_result = _try_remote_extract(turn, settings)
        if remote_result is not None:
            return remote_result[: settings.max_memories_per_turn]
    return _rule_based_extract(turn, settings.max_memories_per_turn)


def _rule_based_extract(turn: TurnEvent, limit: int) -> List[MemoryCandidate]:
    source_text = "\n".join(
        [msg.content for msg in turn.input_messages] + [turn.assistant_message.content]
    )
    sentences = _split_sentences(source_text)
    candidates: list[MemoryCandidate] = []

    for sentence in sentences:
        kind = _classify_sentence(sentence)
        if kind is None:
            continue
        importance = _importance_for_sentence(sentence)
        candidate = MemoryCandidate(kind=kind, text=sentence.strip(), importance=importance)
        candidates.append(candidate)
        if len(candidates) >= limit:
            break
    return candidates


def _split_sentences(text: str) -> list[str]:
    raw_sentences = SENTENCE_SPLIT.split(text)
    return [s.strip() for s in raw_sentences if s.strip()]


def _classify_sentence(sentence: str) -> MemoryKind | None:
    checks: list[tuple[Iterable[re.Pattern[str]], MemoryKind]] = [
        (PREFERENCE_PATTERNS, MemoryKind.PREFERENCE),
        (DECISION_PATTERNS, MemoryKind.DECISION),
        (TODO_PATTERNS, MemoryKind.TODO),
        (PITFALL_PATTERNS, MemoryKind.PITFALL),
        (WORKFLOW_PATTERNS, MemoryKind.WORKFLOW),
        (REFERENCE_PATTERNS, MemoryKind.REFERENCE),
        (FACT_PATTERNS, MemoryKind.FACT),
    ]
    for patterns, kind in checks:
        if any(pattern.search(sentence) for pattern in patterns):
            return kind
    return None


def _importance_for_sentence(sentence: str) -> int:
    lowered = sentence.lower()
    if "always" in lowered or "never" in lowered or "must" in lowered:
        return 5
    if "should" in lowered:
        return 4
    if "maybe" in lowered or "optional" in lowered:
        return 2
    return 3


def _try_remote_extract(turn: TurnEvent, settings: Settings) -> list[MemoryCandidate] | None:
    try:
        import openai  # type: ignore
    except Exception:
        return None
    client = openai.OpenAI()
    truncated_assistant = turn.assistant_message.content[: settings.max_remote_chars]
    prompt = (
        "Extract durable memories from the assistant's message. "
        "Return JSON with entries of {kind, text, importance}."
    )
    try:
        resp = client.responses.create(
            model=settings.remote_model or "gpt-4o-mini",
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": truncated_assistant},
            ],
            response_format={"type": "json_object"},
        )
    except Exception:
        return None
    try:
        message = resp.output[0].content[0].text  # type: ignore
        data = json.loads(message)
        results = []
        for item in data.get("memories", []):
            kind = MemoryKind(item.get("kind", MemoryKind.FACT))
            results.append(
                MemoryCandidate(
                    kind=kind,
                    text=item.get("text", ""),
                    importance=int(item.get("importance", 3)),
                )
            )
        return results
    except Exception:
        return None
