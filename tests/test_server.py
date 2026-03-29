from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest

import sqlite_mcp_server.server as server
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


@pytest.mark.parametrize(
    ("view_name", "params"),
    [
        ("open_tasks", {"limit": 5}),
        ("recent_activity", {"limit": 5}),
    ],
)
def test_query_view_tool_dispatch(monkeypatch: pytest.MonkeyPatch, view_name: str, params: dict[str, object]) -> None:
    class FakeDb:
        def query_view(self, view_name: str, params: dict[str, object] | None = None):
            return {"view": view_name, "params": params}

    monkeypatch.setattr(server, "_db", lambda ctx: FakeDb())
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=SimpleNamespace(db=None)))

    result = server.query_view(view_name=view_name, params=params, ctx=ctx)

    assert result["view"] == view_name
    assert result["params"] == params


def test_apply_performance_tuning_tool_exposes_db_method(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.called = False

        def apply_performance_tuning(self, **kwargs: Any) -> dict[str, Any]:
            self.called = True
            return {"applied": True, "kwargs": kwargs}

    fake_db = FakeDb()
    monkeypatch.setattr(server, "_db", lambda ctx: fake_db)
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=SimpleNamespace(db=None)))

    response = server.apply_performance_tuning(ctx=ctx)

    assert response["applied"] is True
    assert fake_db.called is True


def test_project_summary_view_via_query_view(tmp_path: Path) -> None:
    repo_root = tmp_path
    db_path = repo_root / 'project_memory.db'
    manager = server.DatabaseManager(db_path)
    manager.connect()

    try:
        manager.bootstrap_project_memory('project.sqlite-mcp', 'SQLite MCP')

        class Ctx:
            request_context = type('x', (), {'lifespan_context': type('y', (), {'db': manager})()})()

        ctx = Ctx()
        summary = server.query_view(view_name='project_summary', ctx=ctx)

        sections = {row['section'] for row in summary['items']}
        assert 'project_state' in sections
        assert 'open_tasks' in sections
        assert 'database_health' in sections
    finally:
        manager.close()


def test_app_lifespan_applies_performance_tuning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called = []

    monkeypatch.setattr(server, "_initial_project_root", lambda: tmp_path)

    def fake_apply(self, **kwargs: Any) -> dict[str, Any]:
        called.append(True)
        return {"pragmas": {"journal_mode": "wal"}}

    monkeypatch.setattr(server.DatabaseManager, "apply_performance_tuning", fake_apply)

    async def runner() -> None:
        async with server.app_lifespan(None) as ctx:
            assert str(ctx.project_root) == str(tmp_path)

    anyio.run(runner)
    assert called
