from __future__ import annotations

from pathlib import Path

from sqlite_mcp_server.cli import _bootstrap_self, _sync_roadmap
from sqlite_mcp_server.db import DatabaseManager


def test_bootstrap_self_is_idempotent_and_tracks_repo_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src/sqlite_mcp_server").mkdir(parents=True)
    (repo_root / "tests").mkdir()

    for relative_path in [
        "pyproject.toml",
        "README.md",
        "roadmap.md",
        "src/sqlite_mcp_server/db.py",
        "src/sqlite_mcp_server/server.py",
        "src/sqlite_mcp_server/cli.py",
        "tests/test_db.py",
    ]:
        target = repo_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("placeholder\n", encoding="utf-8")

    manager = DatabaseManager(tmp_path / "memory.db")
    manager.connect()
    try:
        first = _bootstrap_self(manager, repo_root)
        second = _bootstrap_self(manager, repo_root)

        assert first["project_state"]["project"]["id"] == "project.sqlite-mcp"
        assert second["project_state"]["project"]["id"] == "project.sqlite-mcp"
        assert "src/sqlite_mcp_server/cli.py" in second["tracked_files"]

        notes = manager._fetch_all(
            "SELECT id FROM content WHERE id IN ('note.self-hosting', 'note.roadmap-focus') ORDER BY id"
        )
        assert [item["id"] for item in notes] == ["note.roadmap-focus", "note.self-hosting"]

        project_state = manager.get_project_state(limit=10)
        assert project_state["counts"]["entities"] >= 9
    finally:
        manager.close()


def test_sync_roadmap_creates_phase_task_and_decision_entities(tmp_path: Path) -> None:
    roadmap_path = tmp_path / "roadmap.md"
    roadmap_path.write_text(
    """# Sample Roadmap

## Goal

Finish the SQLite-backed project memory MCP.

## Current State

Already implemented:

- Generic graph-friendly schema.

## Phase 4: Compact Contracts And Controlled Vocabularies

Objective: improve AI efficiency without redesigning the storage model.

Tasks:

- Define stable response schemas for all high-frequency MCP tools.
- Add compact response modes where large or repetitive payloads are expected.

Acceptance criteria:

- The AI can complete common workflows with fewer tool calls and fewer tokens.

## Open Decisions

- Canonical entity id format.
""",
        encoding="utf-8",
    )

    manager = DatabaseManager(tmp_path / "memory.db")
    manager.connect()
    try:
        manager.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")

        first = _sync_roadmap(manager, roadmap_path)
        second = _sync_roadmap(manager, roadmap_path)

        assert first["phase_count"] == 1
        assert first["task_count"] == 2
        assert first["open_decision_count"] == 1
        assert first["section_count"] >= 2
        assert second["task_count"] == 2

        phase = manager.get_entity("phase.4.compact-contracts-and-controlled-vocabularies", include_related=True)
        assert phase["description"] == "improve AI efficiency without redesigning the storage model."
        assert any(item["content_type"] == "spec" for item in phase["content"])

        task = manager.get_entity(first["task_ids"][0], include_related=True)
        assert task["status"] == "planned"

        decision = manager.get_entity("decision.canonical-entity-id-format", include_related=True)
        assert decision["status"] == "draft"

        health = manager.get_database_health(limit=10)
        assert health["issue_counts"]["invalid_statuses"] == 0

        rendered = manager.render_markdown_views(["todo", "roadmap"])
        assert "Todo (status=active)" not in rendered["todo.md"]
        assert "[file] roadmap.md" not in rendered["roadmap.md"]
        assert "## Goal" in rendered["roadmap.md"]
        assert "Finish the SQLite-backed project memory MCP." in rendered["roadmap.md"]
        assert "## Open Decisions" in rendered["roadmap.md"]
        assert "## Phase 4: Compact Contracts And Controlled Vocabularies" in rendered["roadmap.md"]
        assert "### Tasks" in rendered["roadmap.md"]
        assert "## Phase 4" in rendered["todo.md"]
    finally:
        manager.close()