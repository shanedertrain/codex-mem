import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from codex_mem import mcp_server
from codex_mem.paths import mcp_log_path


@pytest.fixture(autouse=True)
def reset_logging_state():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    mcp_server._logging_configured = False
    mcp_server._log_file = None
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        if handler not in original_handlers:
            handler.close()
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)
    mcp_server._logging_configured = False
    mcp_server._log_file = None


def test_setup_logging_configures_handlers_and_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("CODEX_MEM_LOG_LEVEL", "DEBUG")

    log_file = mcp_server.setup_logging(force=True)

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert any(isinstance(handler, logging.StreamHandler) for handler in root.handlers)

    rotating_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert rotating_handlers
    rotating = rotating_handlers[0]
    assert Path(rotating.baseFilename) == mcp_log_path()
    assert rotating.maxBytes == 5 * 1024 * 1024
    assert rotating.backupCount == 3
    assert rotating.formatter is not None
    assert rotating.formatter.converter == time.gmtime
    assert log_file == mcp_log_path()


def test_mcp_log_path_prefers_mcp_home(monkeypatch, tmp_path):
    mcp_dir = tmp_path / "custom-mcp-home"
    monkeypatch.setenv("CODEX_MCP_HOME", str(mcp_dir))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home-overridden"))

    assert mcp_log_path() == mcp_dir / "codex-mem.log"


def test_setup_logging_creates_directory_with_home_override(monkeypatch, tmp_path):
    home_dir = tmp_path / "alt-home"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CODEX_MCP_HOME", raising=False)

    log_file = mcp_server.setup_logging(force=True)

    expected_dir = home_dir / ".codex" / "mcp"
    assert log_file is not None
    assert log_file.parent == expected_dir
    assert expected_dir.exists()
    assert log_file.exists()
