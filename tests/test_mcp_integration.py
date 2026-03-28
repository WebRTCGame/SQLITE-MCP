from __future__ import annotations

import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


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
                    "get_project_state",
                    {"limit": 5, "compact": True},
                )
                payload = project_state.content[0].text
                assert 'project_state.v1' in payload
                assert 'project.sqlite-mcp' in payload

    anyio.run(run_session)