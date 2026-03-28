from __future__ import annotations

from pathlib import Path

import pytest

from sqlite_mcp_server.db import DatabaseManager, ValidationError


@pytest.fixture()
def db(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager(tmp_path / "memory.db")
    manager.connect()
    yield manager
    manager.close()


def test_bootstrap_project_memory_creates_project_and_memory_areas(db: DatabaseManager) -> None:
    result = db.bootstrap_project_memory(
        project_id="project.sqlite-mcp",
        project_name="SQLite MCP",
        description="Project memory store",
        tags=["demo"],
    )

    assert result["project"]["id"] == "project.sqlite-mcp"
    assert len(result["memory_areas"]) == 6

    relationships = db.list_relationships(entity_id="project.sqlite-mcp", direction="out")
    assert len(relationships) == 6
    assert {item["type"] for item in relationships} == {"has_memory_area"}


def test_upsert_and_connect_are_idempotent(db: DatabaseManager) -> None:
    db.create_entity("project.sqlite-mcp", "project", name="SQLite MCP")
    first = db.upsert_entity(
        "task.bootstrap",
        "task",
        name="Bootstrap",
        status="pending",
        attributes={"priority": "high"},
        tags=["backend"],
    )
    second = db.upsert_entity(
        "task.bootstrap",
        "task",
        description="Initialize project memory",
        attributes={"owner": "ai"},
        tags=["backend", "memory"],
    )

    assert first["id"] == second["id"]
    assert second["attributes"]["priority"] == "high"
    assert second["attributes"]["owner"] == "ai"
    assert second["tags"] == ["backend", "memory"]

    edge_one = db.connect_entities("project.sqlite-mcp", "task.bootstrap", "tracks")
    edge_two = db.connect_entities("project.sqlite-mcp", "task.bootstrap", "tracks")

    assert edge_one["id"] == edge_two["id"]
    assert len(db.list_relationships(entity_id="project.sqlite-mcp", direction="out")) == 1


def test_read_query_blocks_writes(db: DatabaseManager) -> None:
    db.create_entity("task.bootstrap", "task", name="Bootstrap")

    result = db.execute_read_query("SELECT id, type FROM entities ORDER BY id")
    assert result["row_count"] == 1
    assert result["rows"][0]["id"] == "task.bootstrap"

    with pytest.raises(ValidationError):
        db.execute_read_query("DELETE FROM entities")


def test_render_markdown_views_uses_database_as_source_of_truth(db: DatabaseManager) -> None:
    db.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")
    db.upsert_entity(
        "task.bootstrap",
        "task",
        name="Bootstrap memory",
        status="pending",
        attributes={"priority": "high"},
    )
    db.append_content(
        "task.bootstrap",
        "reasoning",
        "Use explicit MCP verbs for write operations.",
    )

    rendered = db.render_markdown_views(["todo", "notes", "overview"])

    assert set(rendered) == {"todo.md", "notes.md", "overview.md"}
    assert "Bootstrap memory" in rendered["todo.md"]
    assert "Use explicit MCP verbs for write operations." in rendered["notes.md"]
    assert "Project Memory Overview" in rendered["overview.md"]