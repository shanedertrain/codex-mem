from __future__ import annotations

import re
from typing import Iterable, Pattern, Tuple

PatternSpec = Tuple[str, Pattern[str]]


DEFAULT_PATTERNS: tuple[PatternSpec, ...] = (
    ("OPENAI_KEY", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("GITHUB_TOKEN", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("AWS_KEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "BEARER",
        re.compile(r"Bearer [A-Za-z0-9\-_=]{20,}\.[A-Za-z0-9\-_=]{10,}\.[A-Za-z0-9\-_=]{10,}"),
    ),
    (
        "PEM",
        re.compile(
            r"-----BEGIN [^-]+ PRIVATE KEY-----[\s\S]+?-----END [^-]+ PRIVATE KEY-----",
            re.MULTILINE,
        ),
    ),
    ("SLACK", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,48}")),
    ("JWT", re.compile(r"[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}")),
)


def compile_extra_patterns(extra: Iterable[str]) -> list[PatternSpec]:
    compiled: list[PatternSpec] = []
    for idx, pattern in enumerate(extra):
        try:
            compiled.append((f"USER{idx}", re.compile(pattern)))
        except re.error:
            continue
    return compiled


def redact_text(text: str, extra_patterns: Iterable[str] | None = None) -> str:
    """Redact secrets in text."""
    patterns: list[PatternSpec] = list(DEFAULT_PATTERNS)
    if extra_patterns:
        patterns.extend(compile_extra_patterns(extra_patterns))

    redacted = text
    for name, pattern in patterns:
        redacted = pattern.sub(f"[REDACTED:{name}]", redacted)
    return redacted
