import os

from codex_mem import mcp_server


def test_mcp_tools_round_trip(tmp_path):
    os.environ["CODEX_MEM_HOME"] = str(tmp_path / "memhome4")
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()

    # reset globals
    mcp_server._store = None
    mcp_server._settings = None

    add_resp = mcp_server.mem_add(
        text="Use pytest for integration tests",
        kind="todo",
        cwd=str(project_dir),
        project_scoped=True,
        importance=4,
    )
    assert add_resp["id"] is not None

    hits = mcp_server.mem_search(query="pytest", cwd=str(project_dir))
    assert hits

    context = mcp_server.mem_recall(prompt="testing", cwd=str(project_dir))
    assert "Relevant memories" in context

    # cleanup
    if mcp_server._store:
        mcp_server._store.close()
        mcp_server._store = None
        mcp_server._settings = None
