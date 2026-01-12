import os

from codex_mem.config import Settings
from codex_mem.models import MemoryCandidate, MemoryKind
from codex_mem.store import Store


def test_store_insert_and_search(tmp_path):
    os.environ["CODEX_MEM_HOME"] = str(tmp_path / "memhome")
    settings = Settings.from_env()
    store = Store(settings)

    project_root = tmp_path / "project"
    project_root.mkdir()

    candidate = MemoryCandidate(kind=MemoryKind.FACT, text="Using Python 3.12", importance=4)
    mem_id = store.add_memory(candidate, project_root=project_root)
    assert mem_id

    rows = store.search("Python", project_root=project_root, limit=5, include_global=False)
    assert rows
    assert rows[0]["id"] == mem_id

    stats = store.stats()
    assert "db_path" in stats
    store.close()


def test_store_merge_similar(tmp_path):
    os.environ["CODEX_MEM_HOME"] = str(tmp_path / "memhome2")
    settings = Settings.from_env()
    store = Store(settings)

    candidate = MemoryCandidate(kind=MemoryKind.DECISION, text="We will use Typer", importance=3)
    mem_id = store.add_memory(candidate, project_root=None)
    merged_id = store.add_memory(candidate, project_root=None)
    assert merged_id == mem_id
    store.close()
