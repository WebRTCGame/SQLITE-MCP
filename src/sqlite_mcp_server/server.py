from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from inspect import iscoroutinefunction
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import Context, FastMCP

from sqlite_mcp_server.db import DatabaseManager


def _normalize_path_config(value: str | None, default_root: Path, relative_default: str) -> Path:
    if value:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = default_root / candidate
        return candidate.resolve()
    return (default_root / relative_default).resolve()


def _default_db_path(project_root: Path | None = None) -> Path:
    root = (project_root or Path.cwd()).resolve()
    configured = os.getenv("SQLITE_MCP_DB_PATH")
    return _normalize_path_config(configured, root, "data/project_memory.db")


def _default_exports_dir(project_root: Path | None = None) -> Path:
    root = (project_root or Path.cwd()).resolve()
    configured = os.getenv("SQLITE_MCP_EXPORT_DIR")
    return _normalize_path_config(configured, root, "exports")


@dataclass
class AppContext:
    db: DatabaseManager
    project_root: Path
    db_path: Path
    export_dir: Path


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "event",
            "tool_name",
            "call_id",
            "status",
            "elapsed_ms",
            "response_bytes",
            "transport",
            "database_path",
            "error_type",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, sort_keys=True)


def _log_level() -> str:
    return os.getenv("SQLITE_MCP_LOG_LEVEL", "INFO").strip().upper() or "INFO"


def _log_format() -> str:
    return os.getenv("SQLITE_MCP_LOG_FORMAT", "json").strip().lower() or "json"


def _configure_logger() -> logging.Logger:
    logger = logging.getLogger("sqlite_mcp_server")
    level_name = _log_level()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    format_name = _log_format()
    if not logger.handlers:
        handler = logging.StreamHandler()
        if format_name == "text":
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s %(name)s %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%SZ",
                )
            )
        else:
            handler.setFormatter(_JsonLogFormatter())
        logger.addHandler(handler)
    return logger


SERVER_LOGGER = _configure_logger()


def _estimate_response_bytes(payload: Any) -> int:
    try:
        return len(json.dumps(payload, default=str))
    except TypeError:
        return len(str(payload))


def _run_logged_call(
    tool_name: str,
    action: Callable[[], Any],
    *,
    logger: logging.Logger | None = None,
    database_path: str | None = None,
) -> Any:
    active_logger = logger or SERVER_LOGGER
    transport = os.getenv("SQLITE_MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
    call_id = uuid4().hex[:12]
    active_logger.info(
        "tool.start",
        extra={
            "event": "tool.start",
            "tool_name": tool_name,
            "call_id": call_id,
            "transport": transport,
            "database_path": database_path,
        },
    )
    started_at = perf_counter()
    try:
        result = action()
    except Exception as exc:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        active_logger.error(
            "tool.error",
            exc_info=True,
            extra={
                "event": "tool.error",
                "tool_name": tool_name,
                "call_id": call_id,
                "status": "error",
                "elapsed_ms": elapsed_ms,
                "transport": transport,
                "database_path": database_path,
                "error_type": type(exc).__name__,
            },
        )
        raise

    elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
    active_logger.info(
        "tool.finish",
        extra={
            "event": "tool.finish",
            "tool_name": tool_name,
            "call_id": call_id,
            "status": "ok",
            "elapsed_ms": elapsed_ms,
            "response_bytes": _estimate_response_bytes(result),
            "transport": transport,
            "database_path": database_path,
        },
    )
    return result


async def _run_logged_async_call(
    tool_name: str,
    action: Callable[[], Any],
    *,
    logger: logging.Logger | None = None,
    database_path: str | None = None,
) -> Any:
    active_logger = logger or SERVER_LOGGER
    transport = os.getenv("SQLITE_MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
    call_id = uuid4().hex[:12]
    active_logger.info(
        "tool.start",
        extra={
            "event": "tool.start",
            "tool_name": tool_name,
            "call_id": call_id,
            "transport": transport,
            "database_path": database_path,
        },
    )
    started_at = perf_counter()
    try:
        result = await action()
    except Exception as exc:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        active_logger.error(
            "tool.error",
            exc_info=True,
            extra={
                "event": "tool.error",
                "tool_name": tool_name,
                "call_id": call_id,
                "status": "error",
                "elapsed_ms": elapsed_ms,
                "transport": transport,
                "database_path": database_path,
                "error_type": type(exc).__name__,
            },
        )
        raise

    elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
    active_logger.info(
        "tool.finish",
        extra={
            "event": "tool.finish",
            "tool_name": tool_name,
            "call_id": call_id,
            "status": "ok",
            "elapsed_ms": elapsed_ms,
            "response_bytes": _estimate_response_bytes(result),
            "transport": transport,
            "database_path": database_path,
        },
    )
    return result


def _instrumented_tool(*tool_args: Any, **tool_kwargs: Any) -> Callable[[Callable[..., Any]], Any]:
    base_decorator = FastMCP.tool(mcp, *tool_args, **tool_kwargs)

    def decorator(func: Callable[..., Any]) -> Any:
        tool_name = tool_kwargs.get("name") or func.__name__

        def _database_path_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
            ctx = kwargs.get("ctx")
            if ctx is None and args:
                ctx = args[-1]
            if ctx is None:
                return None
            try:
                return str(_db(ctx).db_path)
            except Exception:
                return None

        if iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                database_path = _database_path_from_call(args, kwargs)
                return await _run_logged_async_call(
                    tool_name,
                    lambda: func(*args, **kwargs),
                    database_path=database_path,
                )

            return base_decorator(async_wrapper)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            database_path = _database_path_from_call(args, kwargs)
            return _run_logged_call(
                tool_name,
                lambda: func(*args, **kwargs),
                database_path=database_path,
            )

        return base_decorator(wrapper)

    return decorator


def _initial_project_root() -> Path:
    configured = os.getenv("SQLITE_MCP_PROJECT_ROOT")
    if configured:
        project_root = Path(configured).expanduser().resolve()
        if project_root.is_dir():
            return project_root
    return Path.cwd().resolve()


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    project_root = _initial_project_root()
    db_path = _default_db_path(project_root)
    export_dir = _default_exports_dir(project_root)

    db = DatabaseManager(db_path)
    db.connect()

    try:
        tune = db.apply_performance_tuning()
        SERVER_LOGGER.info(
            "server.performance_tuning",
            extra={
                "event": "server.performance_tuning",
                "details": tune,
                "database_path": str(db.db_path),
            },
        )
    except Exception as exc:
        SERVER_LOGGER.warning(
            "server.performance_tuning_failed",
            extra={
                "event": "server.performance_tuning_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "database_path": str(db.db_path),
            },
        )

    SERVER_LOGGER.info(
        "server.start",
        extra={
            "event": "server.start",
            "transport": os.getenv("SQLITE_MCP_TRANSPORT", "stdio").strip().lower() or "stdio",
            "database_path": str(db.db_path),
            "project_root": str(project_root),
            "export_dir": str(export_dir),
        },
    )
    try:
        yield AppContext(db=db, project_root=project_root, db_path=db_path, export_dir=export_dir)
    finally:
        SERVER_LOGGER.info(
            "server.stop",
            extra={
                "event": "server.stop",
                "transport": os.getenv("SQLITE_MCP_TRANSPORT", "stdio").strip().lower() or "stdio",
                "database_path": str(db.db_path),
                "project_root": str(project_root),
                "export_dir": str(export_dir),
            },
        )
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

mcp.tool = _instrumented_tool  # type: ignore[method-assign]


def _db(ctx: Context) -> DatabaseManager:
    return ctx.request_context.lifespan_context.db


def _app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


@mcp.tool()
def get_project_context(ctx: Context | None = None) -> dict[str, str]:
    """Return the current project root, DB path, and export directory."""
    assert ctx is not None
    app_ctx = _app_context(ctx)
    return {
        "project_root": str(app_ctx.project_root),
        "db_path": str(app_ctx.db_path),
        "export_dir": str(app_ctx.export_dir),
    }


@mcp.tool()
def set_project_root(project_root: str, ctx: Context | None = None) -> dict[str, str]:
    """Switch project context (root + db + export path) and reconnect database."""
    assert ctx is not None
    app_ctx = _app_context(ctx)
    root = Path(project_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValidationError(f"project_root {project_root!r} must be an existing directory")

    db_path = _default_db_path(root)
    export_dir = _default_exports_dir(root)

    app_ctx.db.close()
    app_ctx.db = DatabaseManager(db_path)
    app_ctx.db.connect()
    app_ctx.project_root = root
    app_ctx.db_path = db_path
    app_ctx.export_dir = export_dir

    SERVER_LOGGER.info(
        "project.updated",
        extra={
            "event": "project.updated",
            "project_root": str(root),
            "database_path": str(db_path),
            "export_dir": str(export_dir),
        },
    )

    return {"project_root": str(root), "db_path": str(db_path), "export_dir": str(export_dir)}


def _default_exports_dir(project_root: Path | None = None) -> Path:
    root = (project_root or Path.cwd()).resolve()
    configured = os.getenv("SQLITE_MCP_EXPORT_DIR")
    return _normalize_path_config(configured, root, "exports")


@mcp.tool()
def server_info(ctx: Context) -> dict[str, Any]:
    """Return server metadata and schema settings."""
    db = _db(ctx)
    app_ctx = _app_context(ctx)
    return {
        "name": ctx.fastmcp.name,
        "project_root": str(app_ctx.project_root),
        "database_path": str(db.db_path),
        "export_dir": str(app_ctx.export_dir),
        "transport_hint": os.getenv("SQLITE_MCP_TRANSPORT", "stdio"),
        "logging": {
            "level": _log_level().lower(),
            "format": _log_format(),
            "request_timing": True,
            "destination": "stderr",
        },
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
def get_project_state(limit: int = 10, compact: bool = True, ctx: Context | None = None) -> dict[str, Any]:
    """Return a compact project-state summary for AI resumption and status checks."""
    assert ctx is not None
    return _db(ctx).get_project_state(limit=limit, compact=compact)


@mcp.tool()
def get_open_tasks(
    limit: int = 25,
    offset: int = 0,
    compact: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return open task-like entities in a compact, deterministic shape."""
    assert ctx is not None
    return _db(ctx).get_open_tasks(limit=limit, offset=offset, compact=compact)


@mcp.tool()
def refresh_task_summary(ctx: Context | None = None) -> dict[str, Any]:
    """Rebuild a task summary materialized table for faster open task queries."""
    assert ctx is not None
    return _db(ctx).refresh_task_summary()


@mcp.tool()
def apply_performance_tuning(
    journal_mode: str = "WAL",
    synchronous: str = "NORMAL",
    temp_store: str = "MEMORY",
    cache_size: int = 20000,
    mmap_size: int = 268435456,
    automatic_index: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Tune SQLite settings for throughput during heavy project-memory workloads."""
    assert ctx is not None
    return _db(ctx).apply_performance_tuning(
        journal_mode=journal_mode,
        synchronous=synchronous,
        temp_store=temp_store,
        cache_size=cache_size,
        mmap_size=mmap_size,
        automatic_index=automatic_index,
    )


@mcp.tool()
def get_decision_log(
    limit: int = 25,
    offset: int = 0,
    compact: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return decisions and recent supporting note excerpts without requiring ad hoc SQL."""
    assert ctx is not None
    return _db(ctx).get_decision_log(limit=limit, offset=offset, compact=compact)


@mcp.tool()
def get_architecture_summary(
    node_limit: int = 100,
    relationship_limit: int = 150,
    compact: bool = True,
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
    compact: bool = True,
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
    compact: bool = True,
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
def get_recent_activity(
    limit: int = 20,
    offset: int = 0,
    compact: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return recent entities, content, and events to help an AI resume context quickly."""
    assert ctx is not None
    return _db(ctx).get_recent_activity(limit=limit, offset=offset, compact=compact)


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
    edge_limit: int = 200,
    node_limit: int = 250,
    compact: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Traverse outward relationship dependencies from an entity."""
    assert ctx is not None
    return _db(ctx).get_entity_graph(
        entity_id=entity_id,
        max_depth=max_depth,
        relationship_type=relationship_type,
        edge_limit=edge_limit,
        node_limit=node_limit,
        compact=compact,
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
    user_requested: bool = False,
    request_reason: str | None = None,
    ctx: Context | None = None,
) -> dict[str, str]:
    """Render markdown document views only after an explicit user request for a human-readable artifact."""
    assert ctx is not None
    return _db(ctx).render_markdown_views(
        view_names=view_names,
        user_requested=user_requested,
        request_reason=request_reason,
    )


@mcp.tool()
def export_markdown_views(
    view_names: list[str] | None = None,
    output_dir: str | None = None,
    overwrite: bool = False,
    require_existing_dir: bool = False,
    user_requested: bool = False,
    request_reason: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Write generated markdown views only after an explicit user request for a human-readable artifact."""
    assert ctx is not None
    export_dir = Path(output_dir).expanduser().resolve() if output_dir else _default_exports_dir()
    return _db(ctx).export_markdown_views(
        output_dir=export_dir,
        view_names=view_names,
        overwrite=overwrite,
        require_existing_dir=require_existing_dir,
        user_requested=user_requested,
        request_reason=request_reason,
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
        "- Maintain roadmap state directly in SQLite entities and content; do not import or depend on roadmap.md as a source file.\n"
        "- Do not generate markdown views unless the user explicitly asks for a human-readable document.\n"
        "- Never treat generated markdown views as authoritative state; use SQLite/MCP reads instead."
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
