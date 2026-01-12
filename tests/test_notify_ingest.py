import os

from codex_mem.config import Settings
from codex_mem.notify import ingest_event
from codex_mem.store import Store


def test_ingest_event_writes_turn_and_memories(tmp_path):
    os.environ["CODEX_MEM_HOME"] = str(tmp_path / "memhome3")
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()

    payload = {
        "thread-id": "t1",
        "turn-id": "2",
        "cwd": str(project_dir),
        "input-messages": ["Please always run ruff format."],
        "last-assistant-message": "We decided to enable lint checks.",
    }
    settings = Settings.from_env()
    store = Store(settings)
    ok = ingest_event(payload, settings, store)
    assert ok

    turns = store.conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
    memories = store.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert turns == 1
    assert memories >= 1
    store.close()
