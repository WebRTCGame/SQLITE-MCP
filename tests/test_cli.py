# SQLite MCP source file
#
# Description:
#   Test module for SQLite MCP CLI behavior.
#   Bootstraps/implements functionality for the SQLite MCP project.
#
# Date modified: 2026-04-01
#
from __future__ import annotations

from pathlib import Path

from sqlite_mcp_server.cli import _bootstrap_self, _sync_document
from sqlite_mcp_server.db import DatabaseManager, DOCUMENT_TARGETS


def test_bootstrap_self_is_idempotent_and_tracks_repo_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src/sqlite_mcp_server").mkdir(parents=True)
    (repo_root / "tests").mkdir()

    for relative_path in [
        "pyproject.toml",
        "README.md",
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
        assert project_state["counts"]["entities"] >= 8
    finally:
        manager.close()


def test_sync_document_supports_extended_document_targets(tmp_path: Path) -> None:
    manager = DatabaseManager(tmp_path / "memory.db")
    manager.connect()
    try:
        manager.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")

        extra_targets = [
            "kpi",
            "okr",
            "strategy",
            "risk",
            "issue",
            "epic",
            "story",
            "feature",
            "milestone",
            "release",
            "dependency",
            "objective",
            "initiative",
            "metric",
            "capability",
            "assumption",
            "problem statement",
            "retrospective",
            "action item",
        ]

        for target in extra_targets:
            normalized_target = target.replace(" ", "_")
            input_path = tmp_path / f"{normalized_target}.md"
            input_path.write_text(f"# {target.title()}\n\nAuto-sync for {target}.\n", encoding="utf-8")

            result = _sync_document(manager, target, input_path)
            assert result["target"] == normalized_target
            assert result["content_id"] == DOCUMENT_TARGETS[normalized_target]["content_id"]

            anchor = manager.get_entity(result["entity_id"], include_related=True)
            assert anchor["attributes"]["source_path"] == str(input_path.resolve())
            assert any(item["id"] == DOCUMENT_TARGETS[normalized_target]["content_id"] for item in anchor["content"])

            # These category targets are meant for sync-document anchors.  
            # Rendering of custom view names is not supported by default.
            # We assert the anchor content exists and can be retrieved.
            content_rows = manager._fetch_all(
                "SELECT id, body FROM content WHERE entity_id = ? AND id = ?",
                (result["entity_id"], DOCUMENT_TARGETS[normalized_target]["content_id"]),
            )
            assert len(content_rows) == 1
            assert "Auto-sync for" in content_rows[0]["body"]

    finally:
        manager.close()


def test_roadmap_renders_from_db_native_writes(tmp_path: Path) -> None:
    manager = DatabaseManager(tmp_path / "memory.db")
    manager.connect()
    try:
        manager.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")

        manager.upsert_entity(
            "project.sqlite-mcp.roadmap",
            "roadmap",
            name="Roadmap",
            description="Structured roadmap state maintained directly in SQLite.",
            status="active",
            tags=["roadmap"],
        )
        manager.connect_entities("project.sqlite-mcp", "project.sqlite-mcp.roadmap", "has_memory_area")
        manager.append_content(
            "project.sqlite-mcp.roadmap",
            "spec",
            "Finish the SQLite-backed project memory MCP.",
            content_id="roadmap-section.goal",
        )
        manager.append_content(
            "project.sqlite-mcp.roadmap",
            "spec",
            "Already implemented:\n\n- Generic graph-friendly schema.",
            content_id="roadmap-section.current-state",
        )
        manager.create_entity(
            "phase.5.content-migration",
            "phase",
            name="Phase 5: Content Migration",
            description="Move remaining hand-maintained markdown into structured memory.",
            status="planned",
            attributes={"phase_number": "5", "source": "sqlite"},
            tags=["roadmap", "phase"],
        )
        manager.connect_entities("project.sqlite-mcp.roadmap", "phase.5.content-migration", "contains")
        manager.append_content(
            "phase.5.content-migration",
            "spec",
            "- Generated roadmap output only reflects the current SQLite roadmap state.",
            content_id="spec.phase.5.content-migration",
        )
        manager.create_entity(
            "task.phase5.sync-remaining-human-authored-notes-into-sqlite",
            "task",
            name="Sync remaining human-authored notes into SQLite.",
            description="Roadmap task for Phase 5.",
            status="planned",
            attributes={"phase_number": "5", "task_order": "1", "source": "sqlite"},
            tags=["roadmap", "task"],
        )
        manager.connect_entities(
            "phase.5.content-migration",
            "task.phase5.sync-remaining-human-authored-notes-into-sqlite",
            "contains",
        )
        manager.create_entity(
            "decision.canonical-entity-id-format",
            "decision",
            name="Canonical entity id format.",
            description="Open roadmap decision requiring resolution.",
            status="draft",
            attributes={"source": "sqlite"},
            tags=["decision", "roadmap", "open-decision"],
        )
        manager.connect_entities("project.sqlite-mcp.roadmap", "decision.canonical-entity-id-format", "tracks")

        health = manager.get_database_health(limit=10)
        assert health["issue_counts"]["invalid_statuses"] == 0

        rendered = manager.render_markdown_views(
            ["todo", "roadmap"],
            user_requested=True,
            request_reason="User asked for roadmap views.",
        )
        assert "Todo (status=active)" not in rendered["todo.md"]
        assert "[file] roadmap.md" not in rendered["roadmap.md"]
        assert "## Goal" in rendered["roadmap.md"]
        assert "Finish the SQLite-backed project memory MCP." in rendered["roadmap.md"]
        assert "## Open Decisions" in rendered["roadmap.md"]
        assert "## Phase 5: Content Migration" in rendered["roadmap.md"]
        assert "### Tasks" in rendered["roadmap.md"]
        assert "## Phase 5" in rendered["todo.md"]
    finally:
        manager.close()


def test_sync_document_updates_memory_area_anchor_and_rendered_view(tmp_path: Path) -> None:
    manager = DatabaseManager(tmp_path / "memory.db")
    manager.connect()
    try:
        manager.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")
        input_path = tmp_path / "architecture.md"
        input_path.write_text(
            "# Architecture Notes\n\nThe MCP server centers authoritative state in SQLite.\n",
            encoding="utf-8",
        )

        result = _sync_document(manager, "architecture", input_path)

        assert result["entity_id"] == "project.sqlite-mcp.architecture"
        anchor = manager.get_entity("project.sqlite-mcp.architecture", include_related=True)
        assert anchor["attributes"]["source_path"] == str(input_path.resolve())
        assert any(item["id"] == "document.architecture.current" for item in anchor["content"])

        rendered = manager.render_markdown_views(
            ["architecture"],
            user_requested=True,
            request_reason="User asked for architecture view.",
        )
        assert "## Current Architecture Document" in rendered["architecture.md"]
        assert "The MCP server centers authoritative state in SQLite." in rendered["architecture.md"]
    finally:
        manager.close()


def test_sync_document_roadmap_target_is_supported_and_renders(tmp_path: Path) -> None:
    manager = DatabaseManager(tmp_path / "memory.db")
    manager.connect()
    try:
        manager.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")

        input_path = tmp_path / "roadmap.md"
        input_path.write_text(
            "# Roadmap Narrative\n\nTrack migration completion and strategic direction.\n",
            encoding="utf-8",
        )

        result = _sync_document(manager, "roadmap", input_path)

        assert result["entity_id"] == "project.sqlite-mcp.roadmap"
        anchor = manager.get_entity("project.sqlite-mcp.roadmap", include_related=True)
        assert anchor["attributes"]["source_path"] == str(input_path.resolve())
        assert any(item["id"] == "document.roadmap.current" for item in anchor["content"])

        rendered = manager.render_markdown_views(
            ["roadmap"],
            user_requested=True,
            request_reason="User asked for roadmap view.",
        )
        assert "## Current Roadmap Document" in rendered["roadmap.md"]
        assert "Track migration completion and strategic direction." in rendered["roadmap.md"]
    finally:
        manager.close()