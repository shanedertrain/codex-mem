from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from codex_mem.config import Settings
from codex_mem.models import MemoryCandidate, MemoryKind
from codex_mem.notify import ingest_event
from codex_mem.paths import detect_project_root, ensure_base_dir
from codex_mem.spool import clear as clear_spool
from codex_mem.spool import read_all as read_spool
from codex_mem.store import Store

app = typer.Typer(help="codex-mem CLI")


def _get_store(settings: Settings) -> Store:
    return Store(settings)


@app.command()
def init() -> None:
    """Initialize codex-mem and print config snippet."""
    settings = Settings.from_env()
    store = _get_store(settings)
    store.close()
    base = ensure_base_dir()
    python_cmd = sys.executable
    snippet = f'''
# Turn capture
notify = ["{python_cmd}", "-m", "codex_mem.notify"]

# MCP server
[mcp_servers.codex_mem]
command = "{python_cmd}"
args = ["-m", "codex_mem.mcp_server"]
startup_timeout_sec = 10.0
tool_timeout_sec = 60.0
'''
    typer.echo(f"Initialized codex-mem at {base}")
    typer.echo("Paste this into ~/.codex/config.toml:")
    typer.echo(snippet.strip())


@app.command()
def serve() -> None:
    """Run MCP server (stdio)."""
    from codex_mem.mcp_server import run

    run()


@app.command()
def search(
    query: str = typer.Argument(..., help="FTS query"),
    cwd: str | None = typer.Option(None, help="Project cwd for scoping"),
    limit: int = typer.Option(20, help="Max results"),
) -> None:
    settings = Settings.from_env()
    store = _get_store(settings)
    project_root = detect_project_root(Path(cwd), settings.root_markers) if cwd else None
    rows = store.search(query, project_root, limit, include_global=True)
    for row in rows:
        typer.echo(f"[{row['id']}] ({row['kind']}) {row['text']}")
    store.close()


@app.command()
def add(
    text: str = typer.Argument(..., help="Memory text"),
    kind: str = typer.Option("fact", help="Kind of memory"),
    cwd: str | None = typer.Option(None, help="Project cwd"),
    project_scoped: bool = typer.Option(True, help="Scope to project"),
    importance: int = typer.Option(3, help="Importance 1-5"),
    tags: list[str] = typer.Option(None, help="Tags"),
) -> None:
    settings = Settings.from_env()
    store = _get_store(settings)
    try:
        mem_kind = MemoryKind(kind)
    except ValueError:
        typer.echo(f"Unknown kind: {kind}", err=True)
        raise typer.Exit(code=1)
    project_root = (
        detect_project_root(Path(cwd), settings.root_markers) if project_scoped and cwd else None
    )
    candidate = MemoryCandidate(
        kind=mem_kind, text=text, importance=importance, tags=tuple(tags or [])
    )
    mem_id = store.add_memory(candidate, project_root=project_root)
    typer.echo(f"Added memory id={mem_id}")
    store.close()


@app.command()
def forget(memory_id: int = typer.Argument(..., help="ID to delete")) -> None:
    settings = Settings.from_env()
    store = _get_store(settings)
    ok = store.soft_delete(memory_id)
    store.close()
    if not ok:
        typer.echo("Memory not found", err=True)
        raise typer.Exit(code=1)
    typer.echo("Deleted")


@app.command()
def export(
    fmt: str = typer.Option("markdown", help="markdown|json"),
    cwd: str | None = typer.Option(None, help="Project cwd"),
    include_global: bool = typer.Option(True, help="Include global memories"),
) -> None:
    settings = Settings.from_env()
    store = _get_store(settings)
    project_root = detect_project_root(Path(cwd), settings.root_markers) if cwd else None
    rows = store.search("*", project_root, limit=500, include_global=include_global)
    if fmt == "json":
        typer.echo(json.dumps(rows, indent=2))
    else:
        lines: list[str] = ["# Memories"]
        for row in rows:
            lines.append(f"- [{row['kind']}] {row['text']} (id:{row['id']})")
        typer.echo("\n".join(lines))
    store.close()


@app.command()
def reconcile(spool_file: Optional[Path] = typer.Option(None, help="Override spool file")) -> None:
    """Import spooled turns."""
    settings = Settings.from_env()
    store = _get_store(settings)

    def ingest(entry: dict) -> bool:
        payload = entry.get("payload")
        if not payload:
            return False
        return ingest_event(payload, settings, store)

    entries = read_spool(spool_file)
    result = {"success": 0, "failures": 0}
    for entry in entries:
        if ingest(entry):
            result["success"] += 1
        else:
            result["failures"] += 1
    clear_spool(spool_file)
    typer.echo(json.dumps(result))
    store.close()


@app.command()
def doctor() -> None:
    """Check codex-mem health."""
    settings = Settings.from_env()
    issues: list[str] = []
    try:
        store = _get_store(settings)
        cur = store.conn.execute("SELECT COUNT(*) FROM turns")
        cur.fetchone()
        store.close()
    except Exception as exc:  # pragma: no cover - defensive
        issues.append(f"DB check failed: {exc}")
    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.exists():
        issues.append("~/.codex/config.toml not found; add notify + mcp_servers entries")
    if issues:
        typer.echo("Doctor found issues:")
        for issue in issues:
            typer.echo(f"- {issue}")
        raise typer.Exit(code=1)
    typer.echo("codex-mem looks OK.")


if __name__ == "__main__":  # pragma: no cover
    app()
