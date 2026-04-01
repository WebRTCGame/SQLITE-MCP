# SQLite MCP source file
#
# Description:
#   Integration test module for SQLite MCP MCP transport and CLI.
#   Bootstraps/implements functionality for the SQLite MCP project.
#
# Date modified: 2026-04-01
#
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from sqlite_mcp_server.cli import main as cli_main
from sqlite_mcp_server.db import DatabaseManager


def _run_cli(args: list[str]) -> dict[str, object]:
    original_argv = sys.argv[:]
    output = io.StringIO()
    try:
        sys.argv = ["sqlite-project-memory-admin", *args]
        with redirect_stdout(output):
            cli_main()
    finally:
        sys.argv = original_argv
    return json.loads(output.getvalue())


def test_mcp_stdio_initialize_and_get_project_state(tmp_path: Path) -> None:
    db_path = tmp_path / "integration.db"
    repo_root = Path(__file__).resolve().parents[1]

    async def run_session() -> None:
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "sqlite_mcp_server"],
            cwd=str(repo_root),
            env={
                "SQLITE_MCP_TRANSPORT": "stdio",
                "SQLITE_MCP_DB_PATH": str(db_path),
                "SQLITE_MCP_EXPORT_DIR": str(tmp_path / "exports"),
            },
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                bootstrap = await session.call_tool(
                    "bootstrap_project_memory",
                    {"project_id": "project.sqlite-mcp", "project_name": "SQLite MCP"},
                )
                assert bootstrap.content

                project_state = await session.call_tool(
                    "query_view",
                    {"view_name": "project_state", "params": {"limit": 5, "offset": 0}},
                )
                payload = project_state.content[0].text
                assert 'project.sqlite-mcp' in payload

    anyio.run(run_session)


def test_end_to_end_project_memory_acceptance_flow(tmp_path: Path) -> None:
    source_db_path = tmp_path / "source.db"
    restored_db_path = tmp_path / "restored.db"
    snapshot_path = tmp_path / "snapshot.json"
    source_exports = tmp_path / "source-exports"
    restored_exports = tmp_path / "restored-exports"
    architecture_doc = tmp_path / "architecture.md"
    plan_doc = tmp_path / "plan.md"
    repo_root = Path(__file__).resolve().parents[1]

    architecture_doc.write_text(
        "# Architecture\n\nThe project memory server keeps authoritative state in SQLite and emits generated docs on demand.\n",
        encoding="utf-8",
    )
    plan_doc.write_text(
        "# Plan\n\n1. Keep MCP writes explicit.\n2. Generate human-facing markdown only as needed.\n",
        encoding="utf-8",
    )

    async def run_session() -> None:
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "sqlite_mcp_server"],
            cwd=str(repo_root),
            env={
                "SQLITE_MCP_TRANSPORT": "stdio",
                "SQLITE_MCP_DB_PATH": str(source_db_path),
                "SQLITE_MCP_EXPORT_DIR": str(source_exports),
            },
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                bootstrap = await session.call_tool(
                    "bootstrap_project_memory",
                    {
                        "project_id": "project.sqlite-mcp",
                        "project_name": "SQLite MCP",
                        "description": "Acceptance test project memory bootstrap.",
                    },
                )
                assert bootstrap.content

                await session.call_tool(
                    "upsert_entity",
                    {
                        "entity_id": "task.acceptance-flow",
                        "entity_type": "task",
                        "name": "Acceptance flow",
                        "status": "pending",
                        "attributes": {"phase_number": "6", "priority": "high", "owner": "ai"},
                        "tags": ["acceptance", "quality"],
                    },
                )
                await session.call_tool(
                    "append_content",
                    {
                        "entity_id": "task.acceptance-flow",
                        "content_type": "reasoning",
                        "body": "Use MCP for authoritative writes, then prove backup and restore preserve generated outputs.",
                    },
                )
                await session.call_tool(
                    "upsert_entity",
                    {
                        "entity_id": "decision.acceptance-coverage",
                        "entity_type": "decision",
                        "name": "Acceptance coverage",
                        "status": "accepted",
                        "description": "Keep one end-to-end workflow that exercises MCP, CLI, export, and restore together.",
                    },
                )

                project_state = await session.call_tool(
                    "query_view",
                    {"view_name": "project_state", "params": {"limit": 5, "offset": 0}},
                )
                payload = project_state.content[0].text
                assert 'task.acceptance-flow' not in payload or 'project.sqlite-mcp' in payload

    anyio.run(run_session)

    _run_cli([
        "--db-path",
        str(source_db_path),
        "sync-document",
        "architecture",
        "--input-path",
        str(architecture_doc),
    ])
    _run_cli([
        "--db-path",
        str(source_db_path),
        "sync-document",
        "plan",
        "--input-path",
        str(plan_doc),
    ])

    source_export_result = _run_cli([
        "--db-path",
        str(source_db_path),
        "export-views",
        "--output-dir",
        str(source_exports),
        "--user-requested",
        "--request-reason",
        "User explicitly asked for generated acceptance-test views.",
        "architecture",
        "plan",
        "todo",
        "notes",
    ])
    assert source_export_result["view_count"] == 4

    export_json_result = _run_cli([
        "--db-path",
        str(source_db_path),
        "export-json",
        "--output-path",
        str(snapshot_path),
    ])
    assert export_json_result["output_path"] == str(snapshot_path.resolve())

    import_json_result = _run_cli([
        "--db-path",
        str(restored_db_path),
        "import-json",
        "--input-path",
        str(snapshot_path),
    ])
    assert import_json_result["schema"] == "sqlite_project_memory_snapshot.v1"

    restored_export_result = _run_cli([
        "--db-path",
        str(restored_db_path),
        "export-views",
        "--output-dir",
        str(restored_exports),
        "--user-requested",
        "--request-reason",
        "User explicitly asked for restored acceptance-test views.",
        "architecture",
        "plan",
        "todo",
        "notes",
    ])
    assert restored_export_result["view_count"] == 4

    restored = DatabaseManager(restored_db_path)
    restored.connect()
    try:
        state = restored.get_project_state(limit=10)
        assert state["project"]["id"] == "project.sqlite-mcp"
        assert any(item["id"] == "task.acceptance-flow" for item in restored.get_open_tasks(limit=20)["items"])

        architecture_anchor = restored.get_entity("project.sqlite-mcp.architecture", include_related=True)
        assert any(item["id"] == "document.architecture.current" for item in architecture_anchor["content"])

        architecture_render = (restored_exports / "architecture.md").read_text(encoding="utf-8")
        plan_render = (restored_exports / "plan.md").read_text(encoding="utf-8")
        todo_render = (restored_exports / "todo.md").read_text(encoding="utf-8")
        notes_render = (restored_exports / "notes.md").read_text(encoding="utf-8")

        assert "The project memory server keeps authoritative state in SQLite" in architecture_render
        assert "Keep MCP writes explicit." in plan_render
        assert "Acceptance flow" in todo_render
        assert "Use MCP for authoritative writes" in notes_render
    finally:
        restored.close()