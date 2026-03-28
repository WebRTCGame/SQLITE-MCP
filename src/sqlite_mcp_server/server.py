from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from sqlite_mcp_server.db import DatabaseManager


def _default_db_path() -> Path:
    configured = os.getenv("SQLITE_MCP_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / "data" / "project_memory.db").resolve()


@dataclass
class AppContext:
    db: DatabaseManager


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    db = DatabaseManager(_default_db_path())
    db.connect()
    try:
        yield AppContext(db=db)
    finally:
        db.close()


mcp = FastMCP(
    name="SQLite Project Memory",
    instructions=(
        "Store project memory in a graph-oriented SQLite database. "
        "Use entities for authoritative state, relationships for graph structure, "
        "attributes and tags for metadata, and content for narrative knowledge. "
        "Prefer stable ids, deliberate relationship types, and avoid duplicate or meaningless records."
    ),
    lifespan=app_lifespan,
    json_response=True,
)


def _db(ctx: Context) -> DatabaseManager:
    return ctx.request_context.lifespan_context.db


def _default_exports_dir() -> Path:
    configured = os.getenv("SQLITE_MCP_EXPORT_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / "exports").resolve()


@mcp.tool()
def server_info(ctx: Context) -> dict[str, Any]:
    """Return server metadata and schema settings."""
    db = _db(ctx)
    return {
        "name": ctx.fastmcp.name,
        "database_path": str(db.db_path),
        "transport_hint": os.getenv("SQLITE_MCP_TRANSPORT", "stdio"),
        "schema": db.schema_overview(),
    }


@mcp.tool()
def create_entity(
    entity_id: str,
    entity_type: str,
    name: str | None = None,
    description: str | None = None,
    status: str = "active",
    attributes: dict[str, str] | None = None,
    tags: list[str] | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create a new authoritative project entity."""
    assert ctx is not None
    return _db(ctx).create_entity(
        entity_id=entity_id,
        entity_type=entity_type,
        name=name,
        description=description,
        status=status,
        attributes=attributes,
        tags=tags,
    )


@mcp.tool()
def upsert_entity(
    entity_id: str,
    entity_type: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    attributes: dict[str, str] | None = None,
    tags: list[str] | None = None,
    replace_attributes: bool = False,
    replace_tags: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create an entity if missing or merge updates into an existing entity."""
    assert ctx is not None
    return _db(ctx).upsert_entity(
        entity_id=entity_id,
        entity_type=entity_type,
        name=name,
        description=description,
        status=status,
        attributes=attributes,
        tags=tags,
        replace_attributes=replace_attributes,
        replace_tags=replace_tags,
    )


@mcp.tool()
def update_entity(
    entity_id: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Update an existing entity's top-level state."""
    assert ctx is not None
    return _db(ctx).update_entity(
        entity_id=entity_id,
        name=name,
        description=description,
        status=status,
    )


@mcp.tool()
def archive_entity(
    entity_id: str,
    reason: str | None = None,
    archived_status: str = "archived",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Archive an entity without deleting its history or related project memory."""
    assert ctx is not None
    return _db(ctx).archive_entity(
        entity_id=entity_id,
        reason=reason,
        archived_status=archived_status,
    )


@mcp.tool()
def delete_entity(
    entity_id: str,
    force: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Delete an entity with guardrails; non-forced deletion requires prior archiving and no critical dependents."""
    assert ctx is not None
    return _db(ctx).delete_entity(entity_id=entity_id, force=force)


@mcp.tool()
def merge_entities(
    source_entity_id: str,
    target_entity_id: str,
    attribute_conflict: str = "target_wins",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Merge a duplicate source entity into a target entity with deterministic conflict handling."""
    assert ctx is not None
    return _db(ctx).merge_entities(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        attribute_conflict=attribute_conflict,
    )


@mcp.tool()
def get_entity(entity_id: str, include_related: bool = True, ctx: Context | None = None) -> dict[str, Any]:
    """Fetch an entity and optionally include related metadata, content, and events."""
    assert ctx is not None
    return _db(ctx).get_entity(entity_id=entity_id, include_related=include_related)


@mcp.tool()
def list_entities(
    entity_type: str | None = None,
    status: str | None = None,
    attribute_key: str | None = None,
    attribute_value: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    limit: int = 50,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """List entities with optional type, status, attribute, tag, and text filters."""
    assert ctx is not None
    return _db(ctx).list_entities(
        entity_type=entity_type,
        status=status,
        attribute_key=attribute_key,
        attribute_value=attribute_value,
        tag=tag,
        search=search,
        limit=limit,
    )


@mcp.tool()
def find_similar_entities(
    name: str,
    entity_type: str | None = None,
    limit: int = 10,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Find likely duplicate or related entities before creating a new one."""
    assert ctx is not None
    return _db(ctx).find_similar_entities(name=name, entity_type=entity_type, limit=limit)


@mcp.tool()
def resolve_entity_by_name(
    name: str,
    entity_type: str | None = None,
    limit: int = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Resolve a human-readable name to an existing entity when possible."""
    assert ctx is not None
    return _db(ctx).resolve_entity_by_name(name=name, entity_type=entity_type, limit=limit)


@mcp.tool()
def get_or_create_entity(
    entity_type: str,
    name: str,
    entity_id: str | None = None,
    description: str | None = None,
    status: str = "active",
    attributes: dict[str, str] | None = None,
    tags: list[str] | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Reuse an exact entity when it already exists or create one with a generated stable id."""
    assert ctx is not None
    return _db(ctx).get_or_create_entity(
        entity_type=entity_type,
        name=name,
        entity_id=entity_id,
        description=description,
        status=status,
        attributes=attributes,
        tags=tags,
    )


@mcp.tool()
def upsert_attributes(
    entity_id: str,
    attributes: dict[str, str],
    replace: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create or update flexible metadata for an entity."""
    assert ctx is not None
    return _db(ctx).upsert_attributes(entity_id=entity_id, attributes=attributes, replace=replace)


@mcp.tool()
def set_tags(
    entity_id: str,
    tags: list[str],
    replace: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Set or merge tag labels for an entity."""
    assert ctx is not None
    return _db(ctx).set_tags(entity_id=entity_id, tags=tags, replace=replace)


@mcp.tool()
def add_relationship(
    relationship_id: str,
    from_entity: str,
    to_entity: str,
    relationship_type: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create a typed graph edge between two entities."""
    assert ctx is not None
    return _db(ctx).add_relationship(
        relationship_id=relationship_id,
        from_entity=from_entity,
        to_entity=to_entity,
        relationship_type=relationship_type,
    )


@mcp.tool()
def connect_entities(
    from_entity: str,
    to_entity: str,
    relationship_type: str,
    relationship_id: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create a relationship if missing, otherwise return the existing edge."""
    assert ctx is not None
    return _db(ctx).connect_entities(
        from_entity=from_entity,
        to_entity=to_entity,
        relationship_type=relationship_type,
        relationship_id=relationship_id,
    )


@mcp.tool()
def delete_relationship(relationship_id: str, ctx: Context | None = None) -> dict[str, Any]:
    """Delete a relationship by id and record the removal in project history."""
    assert ctx is not None
    return _db(ctx).delete_relationship(relationship_id=relationship_id)


@mcp.tool()
def list_relationships(
    entity_id: str | None = None,
    relationship_type: str | None = None,
    direction: str = "both",
    limit: int = 200,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """List graph edges, optionally constrained to an entity and direction."""
    assert ctx is not None
    return _db(ctx).list_relationships(
        entity_id=entity_id,
        relationship_type=relationship_type,
        direction=direction,
        limit=limit,
    )


@mcp.tool()
def add_content(
    content_id: str,
    entity_id: str,
    content_type: str,
    body: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Attach narrative content such as notes, specs, analysis, or reasoning to an entity."""
    assert ctx is not None
    return _db(ctx).add_content(
        content_id=content_id,
        entity_id=entity_id,
        content_type=content_type,
        body=body,
    )


@mcp.tool()
def append_content(
    entity_id: str,
    content_type: str,
    body: str,
    content_id: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Append narrative content and generate a content id when one is not supplied."""
    assert ctx is not None
    return _db(ctx).append_content(
        entity_id=entity_id,
        content_type=content_type,
        body=body,
        content_id=content_id,
    )


@mcp.tool()
def search_content(query: str, limit: int = 10, ctx: Context | None = None) -> list[dict[str, Any]]:
    """Search narrative content using FTS5 when available."""
    assert ctx is not None
    return _db(ctx).search_content(query=query, limit=limit)


@mcp.tool()
def create_snapshot(
    snapshot_id: str,
    name: str,
    description: str | None = None,
    entity_ids: list[str] | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create a named snapshot of current project state."""
    assert ctx is not None
    return _db(ctx).create_snapshot(
        snapshot_id=snapshot_id,
        name=name,
        description=description,
        entity_ids=entity_ids,
    )


@mcp.tool()
def get_snapshot(snapshot_id: str, ctx: Context | None = None) -> dict[str, Any]:
    """Fetch a named snapshot and its captured entities."""
    assert ctx is not None
    return _db(ctx).get_snapshot(snapshot_id=snapshot_id)


@mcp.tool()
def get_project_overview(ctx: Context | None = None) -> dict[str, Any]:
    """Return summary counts, recent events, and top tags for the project memory store."""
    assert ctx is not None
    return _db(ctx).get_project_overview()


@mcp.tool()
def get_project_state(limit: int = 10, compact: bool = False, ctx: Context | None = None) -> dict[str, Any]:
    """Return a compact project-state summary for AI resumption and status checks."""
    assert ctx is not None
    return _db(ctx).get_project_state(limit=limit, compact=compact)


@mcp.tool()
def get_open_tasks(
    limit: int = 25,
    offset: int = 0,
    compact: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return open task-like entities in a compact, deterministic shape."""
    assert ctx is not None
    return _db(ctx).get_open_tasks(limit=limit, offset=offset, compact=compact)


@mcp.tool()
def get_decision_log(
    limit: int = 25,
    offset: int = 0,
    compact: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return decisions and recent supporting note excerpts without requiring ad hoc SQL."""
    assert ctx is not None
    return _db(ctx).get_decision_log(limit=limit, offset=offset, compact=compact)


@mcp.tool()
def get_architecture_summary(
    node_limit: int = 100,
    relationship_limit: int = 150,
    compact: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return a compact architecture-oriented node and relationship summary."""
    assert ctx is not None
    return _db(ctx).get_architecture_summary(
        node_limit=node_limit,
        relationship_limit=relationship_limit,
        compact=compact,
    )


@mcp.tool()
def get_recent_reasoning(
    limit: int = 20,
    offset: int = 0,
    compact: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return recent reasoning excerpts for quick AI context recovery."""
    assert ctx is not None
    return _db(ctx).get_recent_reasoning(limit=limit, offset=offset, compact=compact)


@mcp.tool()
def get_dependency_view(
    root_entity_id: str | None = None,
    max_depth: int = 2,
    relationship_types: list[str] | None = None,
    limit: int = 200,
    compact: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return dependency-oriented graph data with stable compact fields."""
    assert ctx is not None
    return _db(ctx).get_dependency_view(
        root_entity_id=root_entity_id,
        max_depth=max_depth,
        relationship_types=relationship_types,
        limit=limit,
        compact=compact,
    )


@mcp.tool()
def get_recent_activity(limit: int = 20, ctx: Context | None = None) -> dict[str, Any]:
    """Return recent entities, content, and events to help an AI resume context quickly."""
    assert ctx is not None
    return _db(ctx).get_recent_activity(limit=limit)


@mcp.tool()
def get_database_health(limit: int = 25, ctx: Context | None = None) -> dict[str, Any]:
    """Report likely duplicates, low-quality records, and retention pressure in project memory."""
    assert ctx is not None
    return _db(ctx).get_database_health(limit=limit)


@mcp.tool()
def prune_content_retention(
    content_types: list[str] | None = None,
    keep_latest: int = 20,
    entity_id: str | None = None,
    dry_run: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Prune older reasoning/log content while keeping the most recent records per entity and type."""
    assert ctx is not None
    return _db(ctx).prune_content_retention(
        content_types=content_types,
        keep_latest=keep_latest,
        entity_id=entity_id,
        dry_run=dry_run,
    )


@mcp.tool()
def get_entity_graph(
    entity_id: str,
    max_depth: int = 2,
    relationship_type: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Traverse outward relationship dependencies from an entity."""
    assert ctx is not None
    return _db(ctx).get_entity_graph(
        entity_id=entity_id,
        max_depth=max_depth,
        relationship_type=relationship_type,
    )


@mcp.tool()
def bootstrap_project_memory(
    project_id: str,
    project_name: str,
    description: str | None = None,
    tags: list[str] | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Initialize a project root entity and standard memory-area anchor entities."""
    assert ctx is not None
    return _db(ctx).bootstrap_project_memory(
        project_id=project_id,
        project_name=project_name,
        description=description,
        tags=tags,
    )


@mcp.tool()
def run_read_query(
    sql: str,
    parameters: list[Any] | None = None,
    limit: int = 200,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Run a constrained read-only SQL query for diagnostics, analytics, and ad hoc retrieval."""
    assert ctx is not None
    return _db(ctx).execute_read_query(sql=sql, parameters=parameters, limit=limit)


@mcp.tool()
def render_markdown_views(
    view_names: list[str] | None = None,
    ctx: Context | None = None,
) -> dict[str, str]:
    """Render markdown document views from the SQLite source of truth without writing files."""
    assert ctx is not None
    return _db(ctx).render_markdown_views(view_names=view_names)


@mcp.tool()
def export_markdown_views(
    view_names: list[str] | None = None,
    output_dir: str | None = None,
    overwrite: bool = False,
    require_existing_dir: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Write generated markdown view files to disk so humans can consume exported project documents."""
    assert ctx is not None
    export_dir = Path(output_dir).expanduser().resolve() if output_dir else _default_exports_dir()
    return _db(ctx).export_markdown_views(
        output_dir=export_dir,
        view_names=view_names,
        overwrite=overwrite,
        require_existing_dir=require_existing_dir,
    )


@mcp.resource("memory://schema")
def schema_resource(ctx: Context | None = None) -> str:
    """Read the server schema and validation rules."""
    assert ctx is not None
    return json.dumps(_db(ctx).schema_overview(), indent=2)


@mcp.resource("memory://overview")
def overview_resource(ctx: Context | None = None) -> str:
    """Read the latest project-memory summary as JSON."""
    assert ctx is not None
    return json.dumps(_db(ctx).get_project_overview(), indent=2)


@mcp.resource("memory://recent-activity")
def recent_activity_resource(ctx: Context | None = None) -> str:
    """Read recent activity as JSON for quick AI resumption."""
    assert ctx is not None
    return json.dumps(_db(ctx).get_recent_activity(), indent=2)


@mcp.resource("entity://{entity_id}")
def entity_resource(entity_id: str, ctx: Context | None = None) -> str:
    """Read a single entity and its related state as JSON."""
    assert ctx is not None
    return json.dumps(_db(ctx).get_entity(entity_id=entity_id, include_related=True), indent=2)


@mcp.prompt(title="Project Memory Policy")
def project_memory_policy(project_name: str = "this project") -> str:
    """Guide an AI to store project memory cleanly and avoid data pollution."""
    return (
        f"When writing to the SQLite project-memory store for {project_name}, follow these rules:\n"
        "- Treat entities as the authoritative source of state.\n"
        "- Use stable ids and broad durable types.\n"
        "- Put flexible metadata in attributes, not new pseudo-types.\n"
        "- Use tags only for useful filtering, not as a dumping ground.\n"
        "- Create relationships only when they express a meaningful graph edge.\n"
        "- Store narrative reasoning, notes, and specs in content, separated from state.\n"
        "- Avoid duplicate entities. Reuse existing ids when representing the same object.\n"
        "- Prefer concise, information-dense records over verbose document copies.\n"
        "- Use run_read_query for diagnostics only; do not treat raw SQL as the primary write interface.\n"
        "- Generate markdown views when human-readable documents are needed, but keep SQLite authoritative."
    )


def main() -> None:
    transport = os.getenv("SQLITE_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run()
        return
    if transport in {"streamable-http", "http"}:
        mcp.run(transport="streamable-http")
        return
    raise ValueError("SQLITE_MCP_TRANSPORT must be either 'stdio' or 'streamable-http'")
