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
        attributes={"priority": "high", "phase_number": "4"},
    )
    db.append_content(
        "task.bootstrap",
        "reasoning",
        "Use explicit MCP verbs for write operations.",
    )

    with pytest.raises(ValidationError):
        db.render_markdown_views(["todo", "notes", "overview"])

    rendered = db.render_markdown_views(
        ["todo", "notes", "overview"],
        user_requested=True,
        request_reason="User explicitly asked for markdown views.",
    )

    assert set(rendered) == {"todo.md", "notes.md", "overview.md"}
    assert rendered["todo.md"].startswith("<!-- Generated file: do not edit manually. -->")
    assert "<!-- Non-authoritative generated view: use SQLite/MCP reads for current project state. -->" in rendered["todo.md"]
    assert "<!-- Description: Generated task backlog grouped from the SQLite source of truth. -->" in rendered["todo.md"]
    assert "<!-- Generated at: " in rendered["todo.md"]
    assert "## Phase 4" in rendered["todo.md"]
    assert "Bootstrap memory" in rendered["todo.md"]
    assert "Use explicit MCP verbs for write operations." in rendered["notes.md"]
    assert "Project Memory Overview" in rendered["overview.md"]


def test_export_markdown_views_requires_explicit_overwrite_and_can_require_existing_dir(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    db.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")

    missing_dir = tmp_path / "missing-exports"
    with pytest.raises(ValidationError):
        db.export_markdown_views(
            missing_dir,
            view_names=["todo"],
            require_existing_dir=True,
            user_requested=True,
            request_reason="User asked for a todo export.",
        )

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    existing_target = export_dir / "todo.md"
    existing_target.write_text("old content\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        db.export_markdown_views(
            export_dir,
            view_names=["todo"],
            user_requested=True,
            request_reason="User asked for a todo export.",
        )

    with pytest.raises(ValidationError):
        db.export_markdown_views(export_dir, view_names=["todo"], overwrite=True)

    result = db.export_markdown_views(
        export_dir,
        view_names=["todo"],
        overwrite=True,
        user_requested=True,
        request_reason="User asked for a todo export.",
    )

    assert result["view_count"] == 1
    assert result["overwrite"] is True
    assert result["request_reason"] == "User asked for a todo export."
    assert str(existing_target) in result["overwritten_files"]
    assert existing_target.read_text(encoding="utf-8").startswith("<!-- Generated file: do not edit manually. -->")


def test_document_views_include_synced_anchor_content_and_structured_sections(db: DatabaseManager) -> None:
    db.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")
    db.upsert_entity("module.api", "module", name="API Layer", status="active")
    db.upsert_entity("service.db", "service", name="DB Service", status="active")
    db.connect_entities("module.api", "service.db", "depends_on")
    db.upsert_entity("decision.schema", "decision", name="Schema direction", status="accepted")
    db.append_content("decision.schema", "reasoning", "Prefer compact contracts before storage redesign.")
    db.upsert_entity(
        "task.logging",
        "task",
        name="Add structured logging",
        status="pending",
        attributes={"phase_number": "4", "priority": "high"},
    )
    db.append_content("project.sqlite-mcp.architecture", "spec", "Current architecture document.", content_id="document.architecture.current")
    db.append_content("project.sqlite-mcp.decisions", "analysis", "Current decision log document.", content_id="document.decisions.current")
    db.append_content("project.sqlite-mcp.plan", "spec", "Current implementation plan.", content_id="document.plan.current")
    db.append_content("project.sqlite-mcp.notes", "note", "Current notes document.", content_id="document.notes.current")
    db.append_content("task.logging", "analysis", "Investigate stderr-safe logging for stdio transport.")

    rendered = db.render_markdown_views(
        ["architecture", "decisions", "plan", "notes"],
        user_requested=True,
        request_reason="User asked for document views.",
    )

    assert "## Current Architecture Document" in rendered["architecture.md"]
    assert "Current architecture document." in rendered["architecture.md"]
    assert "## Summary" in rendered["architecture.md"]
    assert "## Accepted" in rendered["decisions.md"]
    assert "Current decision log document." in rendered["decisions.md"]
    assert "## Prioritized Open Work" in rendered["plan.md"]
    assert "Current implementation plan." in rendered["plan.md"]
    assert "## Recent Narrative Entries" in rendered["notes.md"]
    assert "Current notes document." in rendered["notes.md"]
    assert "Investigate stderr-safe logging for stdio transport." in rendered["notes.md"]


def test_schema_overview_reports_schema_version_and_relationship_policy(db: DatabaseManager) -> None:
    overview = db.schema_overview()

    assert overview["schema_version"] >= 1
    assert "depends_on" in overview["validation"]["allowed_relationship_types"]
    assert overview["validation"]["custom_relationship_namespace"] == "custom."
    assert overview["policy"]["entity_id"]["generated_format"] == "<entity_type>.<slug>[.<n>]"
    assert overview["policy"]["relationships"]["registry_table"] is False
    assert "priority" in overview["policy"]["attributes"]["common_keys"]
    assert "task" in overview["policy"]["statuses"]["common_vocabulary"]
    assert overview["policy"]["retention"]["keep_latest"] == 20
    assert overview["policy"]["markdown_views"]["generation_policy"] == "on_demand_only"
    assert overview["policy"]["mcp_read_defaults"]["compact"] is True
    assert "get_recent_activity" in overview["policy"]["mcp_read_defaults"]["tools"]
    assert overview["policy"]["semantic_retrieval"]["default_strategy"] == "fts5_plus_structured_reads"
    assert overview["policy"]["semantic_retrieval"]["embeddings_enabled"] is False


def test_apply_performance_tuning_sets_pragmas_and_creates_summary(db: DatabaseManager) -> None:
    result = db.apply_performance_tuning(automatic_index=True)
    assert result["task_summary"]["task_summary_exists"] is True
    assert result["task_summary"]["total_tasks"] == 0
    assert str(result["pragmas"]["journal_mode"]).lower() == "wal"
    synchronous_value = result["pragmas"]["synchronous"]
    assert str(synchronous_value).lower() in {"normal", "1", "2", "3"}


def test_refresh_task_summary_creates_task_summary_items(db: DatabaseManager) -> None:
    db.create_entity(
        "task.performance",
        "task",
        name="Tune performance",
        status="active",
        attributes={"priority": "high", "rank": "1", "phase_number": "10"},
    )
    summary = db.refresh_task_summary()
    assert summary["task_summary_exists"] is True
    assert summary["entity_count"] == 1
    rows = db._fetch_all("SELECT id, rank, priority FROM task_summary")
    assert rows[0]["id"] == "task.performance"


def test_archive_and_delete_require_safe_lifecycle(db: DatabaseManager) -> None:
    db.create_entity("task.cleanup", "task", name="Cleanup", status="active")
    db.create_entity("task.blocker", "task", name="Blocker", status="active")
    relationship = db.connect_entities("task.cleanup", "task.blocker", "blocks")

    with pytest.raises(ValidationError):
        db.delete_entity("task.cleanup")

    archived = db.archive_entity("task.cleanup", reason="Completed")
    assert archived["status"] == "archived"

    with pytest.raises(ValidationError):
        db.delete_entity("task.cleanup")

    deleted_relationship = db.delete_relationship(relationship["id"])
    assert deleted_relationship["id"] == relationship["id"]

    deleted = db.delete_entity("task.cleanup")
    assert deleted["deleted_entity"]["id"] == "task.cleanup"

    with pytest.raises(ValidationError):
        db.get_entity("task.cleanup")


def test_merge_entities_moves_related_records_and_deduplicates_edges(db: DatabaseManager) -> None:
    db.create_entity("task.target", "task", name="Canonical task", attributes={"priority": "high"})
    db.create_entity("task.source", "task", name="Duplicate task", attributes={"owner": "ai"}, tags=["memory"])
    db.create_entity("task.dependency", "task", name="Dependency")
    db.create_entity("task.parent", "task", name="Parent")
    db.append_content("task.source", "reasoning", "Preserve this reasoning.")
    db.connect_entities("task.source", "task.dependency", "depends_on")
    db.connect_entities("task.parent", "task.source", "tracks")
    db.connect_entities("task.parent", "task.target", "tracks")

    merged = db.merge_entities("task.source", "task.target")

    assert merged["attributes"]["priority"] == "high"
    assert merged["attributes"]["owner"] == "ai"
    assert merged["tags"] == ["memory"]
    assert any(item["content_type"] == "reasoning" for item in merged["content"])

    relationships = db.list_relationships(entity_id="task.target", direction="both")
    assert any(item["type"] == "depends_on" and item["from_entity"] == "task.target" for item in relationships)
    assert len([item for item in relationships if item["type"] == "tracks" and item["to_entity"] == "task.target"]) == 1

    with pytest.raises(ValidationError):
        db.get_entity("task.source")


def test_relationship_type_validation_allows_known_or_custom_namespaces(db: DatabaseManager) -> None:
    db.create_entity("task.a", "task", name="A")
    db.create_entity("task.b", "task", name="B")

    db.connect_entities("task.a", "task.b", "depends_on")
    db.connect_entities("task.a", "task.b", "custom.reviewed_by")

    with pytest.raises(ValidationError):
        db.connect_entities("task.a", "task.b", "made_up_edge")


def test_get_or_create_reuses_exact_match_and_creates_stable_id_for_new_entity(db: DatabaseManager) -> None:
    db.create_entity("task.bootstrap", "task", name="Bootstrap memory")

    existing = db.get_or_create_entity("task", "Bootstrap memory")
    assert existing["created"] is False
    assert existing["entity"]["id"] == "task.bootstrap"

    created = db.get_or_create_entity(
        "task",
        "Add health checks",
        attributes={"owner": "ai"},
        tags=["quality"],
    )
    assert created["created"] is True
    assert created["entity"]["id"] == "task.add-health-checks"
    assert created["entity"]["attributes"]["owner"] == "ai"
    assert created["entity"]["tags"] == ["quality"]


def test_resolve_entity_by_name_reports_ambiguity_and_similarity_candidates(db: DatabaseManager) -> None:
    db.create_entity("task.first", "task", name="Sync roadmap")
    db.create_entity("task.second", "task", name="Sync roadmap")
    db.create_entity("task.third", "task", name="Sync architecture")

    ambiguous = db.resolve_entity_by_name("Sync roadmap", entity_type="task")
    assert ambiguous["match_type"] == "ambiguous"
    assert len(ambiguous["candidates"]) == 2

    similar = db.find_similar_entities("architecture", entity_type="task")
    assert len(similar) == 1
    assert similar[0]["id"] == "task.third"


def test_database_health_reports_duplicates_invalid_status_and_low_signal_attributes(db: DatabaseManager) -> None:
    db.create_entity("task.one", "task", name="Duplicate Name", status="pending")
    db.create_entity("task.two", "task", name="Duplicate Name", status="pending")
    db.create_entity("task.weird", "task", name="Odd status", status="stalled")
    db.upsert_attributes("task.weird", {"owner": "unknown"})
    db.upsert_attributes("task.weird", {"customflag": "true"})
    for index in range(21):
        db.append_content("task.weird", "reasoning", f"reasoning item {index}")

    health = db.get_database_health()

    assert health["healthy"] is False
    assert health["issue_counts"]["duplicate_candidates"] >= 1
    assert health["issue_counts"]["invalid_statuses"] >= 1
    assert health["issue_counts"]["low_quality_attributes"] >= 1
    assert health["issue_counts"]["attribute_namespace_issues"] >= 1
    assert health["issue_counts"]["high_volume_content"] >= 1


def test_prune_content_retention_supports_dry_run_and_deletion(db: DatabaseManager) -> None:
    db.create_entity("task.logs", "task", name="Log-heavy task")
    for index in range(5):
        db.append_content("task.logs", "log", f"log item {index}", content_id=f"log.{index}")

    preview = db.prune_content_retention(content_types=["log"], keep_latest=2, dry_run=True)
    assert preview["delete_count"] == 3
    assert len(preview["candidates"]) == 3

    pruned = db.prune_content_retention(content_types=["log"], keep_latest=2, dry_run=False)
    assert pruned["delete_count"] == 3

    entity = db.get_entity("task.logs", include_related=True)
    remaining_logs = [item for item in entity["content"] if item["content_type"] == "log"]
    assert len(remaining_logs) == 2


def test_project_state_and_open_tasks_return_compact_summary_shapes(db: DatabaseManager) -> None:
    db.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")
    db.upsert_entity(
        "task.open",
        "task",
        name="Open task",
        status="pending",
        attributes={"priority": "high", "owner": "ai"},
    )
    db.upsert_entity("task.done", "task", name="Done task", status="done")

    project_state = db.get_project_state(limit=5)
    assert project_state["project"]["id"] == "project.sqlite-mcp"
    assert project_state["open_task_count"] == 1
    assert any(item["id"] == "project.sqlite-mcp.todo" for item in project_state["memory_areas"])

    open_tasks = db.get_open_tasks(limit=10, offset=0)
    assert open_tasks["total_count"] == 1
    assert open_tasks["items"][0]["id"] == "task.open"
    assert open_tasks["items"][0]["priority"] == "high"
    assert open_tasks["items"][0]["owner"] == "ai"

    compact_state = db.get_project_state(limit=5, compact=True)
    assert compact_state["schema"] == "project_state.v1"
    assert compact_state["compact"] is True
    assert compact_state["data"]["project"]["id"] == "project.sqlite-mcp"

    compact_tasks = db.get_open_tasks(limit=10, offset=0, compact=True)
    assert compact_tasks["schema"] == "open_tasks.v1"
    assert compact_tasks["data"]["has_more"] is False


def test_decision_log_architecture_summary_reasoning_and_dependency_views(db: DatabaseManager) -> None:
    db.create_entity("decision.schema", "decision", name="Schema direction", status="accepted")
    db.append_content(
        "decision.schema",
        "reasoning",
        "Prefer compact MCP responses before changing storage encoding.",
    )
    db.create_entity("module.api", "module", name="API Layer", status="active")
    db.create_entity("service.db", "service", name="DB Service", status="active")
    db.create_entity("file.server", "file", name="server.py", status="active")
    db.connect_entities("module.api", "service.db", "depends_on")
    db.connect_entities("service.db", "file.server", "contains")

    decision_log = db.get_decision_log(limit=10, offset=0)
    assert decision_log["total_count"] == 1
    assert decision_log["items"][0]["id"] == "decision.schema"
    assert "compact MCP responses" in decision_log["items"][0]["latest_note"]

    architecture = db.get_architecture_summary(node_limit=10, relationship_limit=10)
    assert architecture["node_count"] >= 3
    assert any(item["id"] == "module.api" for item in architecture["nodes"])
    assert any(item["type"] == "depends_on" for item in architecture["relationships"])

    reasoning = db.get_recent_reasoning(limit=10, offset=0)
    assert reasoning["total_count"] == 1
    assert reasoning["items"][0]["entity_id"] == "decision.schema"

    dependency_view = db.get_dependency_view(root_entity_id="module.api", max_depth=2, limit=20)
    assert dependency_view["root"]["id"] == "module.api"
    assert any(item["to_entity"] == "service.db" for item in dependency_view["relationships"])


def test_dependency_view_without_root_returns_filtered_graph_slice(db: DatabaseManager) -> None:
    db.create_entity("task.alpha", "task", name="Alpha")
    db.create_entity("task.beta", "task", name="Beta")
    db.create_entity("task.gamma", "task", name="Gamma")
    db.connect_entities("task.alpha", "task.beta", "depends_on")
    db.connect_entities("task.beta", "task.gamma", "blocks")
    db.connect_entities("task.alpha", "task.gamma", "relates_to")

    dependency_view = db.get_dependency_view(limit=10)

    assert dependency_view["root"] is None
    assert dependency_view["relationship_types"] == ["blocks", "depends_on"]
    assert dependency_view["relationship_count"] == 2
    assert all(item["type"] in {"blocks", "depends_on"} for item in dependency_view["relationships"])


def test_recent_activity_paginates_with_compact_metadata(db: DatabaseManager) -> None:
    db.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")
    for index in range(4):
        entity_id = f"task.activity-{index}"
        db.upsert_entity(entity_id, "task", name=f"Activity {index}", status="pending")
        db.append_content(entity_id, "note", f"note {index}")

    recent = db.get_recent_activity(limit=2, offset=1, compact=True)

    assert recent["schema"] == "recent_activity.v1"
    assert recent["data"]["limit"] == 2
    assert recent["data"]["offset"] == 1
    assert len(recent["data"]["recent_events"]) <= 2
    assert len(recent["data"]["recent_entities"]) <= 2
    assert len(recent["data"]["recent_content"]) <= 2
    assert recent["data"]["has_more_events"] is True


def test_entity_graph_applies_edge_and_node_limits(db: DatabaseManager) -> None:
    for index in range(6):
        db.create_entity(f"task.graph-{index}", "task", name=f"Graph {index}")
    for index in range(5):
        db.connect_entities(f"task.graph-{index}", f"task.graph-{index + 1}", "depends_on")

    graph = db.get_entity_graph(
        "task.graph-0",
        max_depth=5,
        edge_limit=2,
        node_limit=2,
        compact=True,
    )

    assert graph["schema"] == "entity_graph.v1"
    assert graph["data"]["relationship_count"] == 2
    assert graph["data"]["node_count"] == 2
    assert graph["data"]["has_more_edges"] is True
    assert graph["data"]["has_more_nodes"] is True


def test_json_snapshot_export_and_import_round_trip(db: DatabaseManager, tmp_path: Path) -> None:
    db.bootstrap_project_memory("project.sqlite-mcp", "SQLite MCP")
    db.upsert_entity("task.backup", "task", name="Backup state", status="planned")
    snapshot = db.export_json_snapshot()

    restored = DatabaseManager(tmp_path / "restored.db")
    restored.connect()
    try:
        result = restored.import_json_snapshot(snapshot, replace=True)
        assert result["schema"] == "sqlite_project_memory_snapshot.v1"

        project_state = restored.get_project_state(limit=5)
        assert project_state["project"]["id"] == "project.sqlite-mcp"
        assert any(item["id"] == "task.backup" for item in restored.get_open_tasks(limit=20)["items"])
    finally:
        restored.close()