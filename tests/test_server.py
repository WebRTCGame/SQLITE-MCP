from __future__ import annotations

import io
import json
import logging

import pytest

from sqlite_mcp_server.server import _JsonLogFormatter, _run_logged_call


def _test_logger(name: str) -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonLogFormatter())
    logger = logging.getLogger(name)
    logger.handlers = []
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_run_logged_call_emits_start_and_finish_records() -> None:
    logger, stream = _test_logger("sqlite_mcp_server.test")
    result = _run_logged_call(
        "demo_tool",
        lambda: {"ok": True},
        logger=logger,
        database_path="D:/memory.db",
    )

    log_lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    assert result == {"ok": True}
    assert [line["event"] for line in log_lines] == ["tool.start", "tool.finish"]
    assert log_lines[1]["tool_name"] == "demo_tool"
    assert log_lines[1]["status"] == "ok"
    assert log_lines[1]["elapsed_ms"] >= 0
    assert log_lines[1]["response_bytes"] > 0


def test_run_logged_call_emits_error_record() -> None:
    logger, stream = _test_logger("sqlite_mcp_server.test_error")

    with pytest.raises(RuntimeError):
        _run_logged_call(
            "broken_tool",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            logger=logger,
            database_path="D:/memory.db",
        )

    log_lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    assert [line["event"] for line in log_lines] == ["tool.start", "tool.error"]
    assert log_lines[-1]["error_type"] == "RuntimeError"
    assert log_lines[-1]["status"] == "error"