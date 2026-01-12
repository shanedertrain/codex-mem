# codex-mem

Persistent, local-first memory layer for Codex. Captures Codex turns via the `notify` hook, extracts durable memories, and exposes them back to Codex through an MCP server and CLI.

## Features
- Turn ingest from `notify` (CLI/IDE)
- SQLite store with FTS5 search
- Rule-based memory extraction (preferences, facts, decisions, TODOs, pitfalls, workflow notes, references)
- MCP tools: `mem.recall`, `mem.search`, `mem.add`, `mem.update`, `mem.forget`, `mem.stats`
- CLI: `init`, `serve`, `search`, `add`, `forget`, `export`, `reconcile`, `doctor`
- Secret redaction and allow/deny globs for capture
- Optional spool + reconcile when the DB is locked

## Quick start
```bash
python -m pip install -e ./codex-mem
cd codex-mem
codex-mem init
# paste the printed snippet into ~/.codex/config.toml
codex-mem serve  # MCP server (stdio)
```

## Configuration (env)
- `CODEX_HOME`: override Codex home (default `~/.codex`)
- `CODEX_MEM_HOME`: override base dir (default `${CODEX_HOME}/mem`)
- `CODEX_MEM_ROOT_MARKERS`: comma-separated markers for project roots (default `.git`)
- `CODEX_MEM_MAX_PER_TURN`: max memories emitted per turn (default 5)
- `CODEX_MEM_MERGE_THRESHOLD`: similarity threshold for merging (default 0.82)
- `CODEX_MEM_REMOTE=1`: enable remote extraction (OpenAI Responses); `CODEX_MEM_REMOTE_MODEL` selects the model
- `CODEX_MEM_REDACT_PATTERNS`: comma-separated extra regexes to redact
- `CODEX_MEM_ALLOW` / `CODEX_MEM_DENY`: glob allow/deny lists for captured cwds
- `CODEX_MEM_SPOOL_ENABLED`: enable spool on DB lock (default 1)

## Notify payloads (expanded)
codex-mem accepts `notify` payloads with either plain strings or structured message objects:
- `input-messages`: list of strings **or** `{role, content, type, surface}` objects
- `last-assistant-message`: string **or** structured object (content list supported)
- Extra fields (e.g., `surface`, `timestamp`) are preserved when present

**Pros of structured payloads**
- Better fidelity for extraction (roles and surfaces retained)
- Future-safe if Codex adds richer notify data (tool outputs, multi-part content)

**Cons**
- Larger payloads (slightly slower)
- Some fields may be ignored if they cannot be normalized to text

## CLI
- `codex-mem init` — create base dir and print config snippet
- `codex-mem serve` — run MCP server over stdio
- `codex-mem search "<query>" --cwd ...`
- `codex-mem add "<text>" --kind fact --cwd ... --importance 3`
- `codex-mem forget <id>`
- `codex-mem export --format markdown|json --cwd ...`
- `codex-mem reconcile` — import spooled turns
- `codex-mem doctor` — basic health checks
