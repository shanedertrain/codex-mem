from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from codex_mem import mcp_server
from codex_mem.paths import mcp_log_path


def test_setup_logging_configures_handlers_and_level(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_MEM_LOG_LEVEL", "debug")
    mcp_server._reset_logging_for_tests()
    try:
        log_path = mcp_server.setup_logging(force=True)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        assert any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers)
        assert any(isinstance(handler, RotatingFileHandler) for handler in root_logger.handlers)
        assert log_path is not None
        assert log_path.parent.exists()
        mcp_server.logger.info("logging setup validation")
        for handler in root_logger.handlers:
            try:
                handler.flush()
            except Exception:
                pass
        assert log_path.exists()
    finally:
        mcp_server._reset_logging_for_tests()


def test_setup_logging_falls_back_when_file_handler_fails(monkeypatch, caplog, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mcp_server._reset_logging_for_tests()

    class FailingHandler:
        def __init__(self, *args, **kwargs):
            raise OSError("boom")

    monkeypatch.setattr(mcp_server, "RotatingFileHandler", FailingHandler)
    with caplog.at_level(logging.WARNING, logger="codex_mem.mcp_server"):
        log_path = mcp_server.setup_logging(force=True)

    try:
        assert log_path is None
        assert "console only" in " ".join(caplog.messages)
        root_logger = logging.getLogger()
        assert any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers)
    finally:
        mcp_server._reset_logging_for_tests()


def test_run_writes_startup_and_shutdown_logs(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_MEM_HOME", str(tmp_path / "memhome"))
    mcp_server._reset_logging_for_tests()
    mcp_server._store = None
    mcp_server._settings = None

    ran = {"called": False}

    def fake_run(transport: str = "stdio") -> None:
        ran["called"] = True

    monkeypatch.setattr(mcp_server.mcp, "run", fake_run)

    try:
        mcp_server.run()
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        log_file = mcp_log_path()
        assert log_file.exists()
        content = log_file.read_text()
        assert "codex-mem starting" in content
        assert "transport=stdio" in content
        assert "codex-mem stopping" in content
        assert ran["called"] is True
    finally:
        mcp_server._reset_logging_for_tests()
