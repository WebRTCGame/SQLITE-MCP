# SQLite Project Memory MCP API Summary

This file provides a compact reference for the MCP server toolset and integration patterns.

> Total MCP tools exposed: 41
> All listed functions are exported as `@mcp.tool` endpoints in `src/sqlite_mcp_server/server.py`.

## Server entrypoint

- Start the MCP service:
  - `python -m sqlite_mcp_server`

- Transport:
  - default: `SQLITE_MCP_TRANSPORT=stdio`
  - alternative: `SQLITE_MCP_TRANSPORT=streamable-http`

- Config via environment:
  - `SQLITE_MCP_PROJECT_ROOT` (optional)
  - `SQLITE_MCP_DB_PATH` (optional, default: `data/project_memory.db`)
  - `SQLITE_MCP_EXPORT_DIR` (optional, default: `exports`)
  - `SQLITE_MCP_LOG_LEVEL` (`INFO` default)
  - `SQLITE_MCP_LOG_FORMAT` (`json` or `text`)

## System

- `get_project_context` — return current project root, DB path, and export directory (read-only)
- `set_project_root` — switch active project context and reconnect database
- `server_info` — full server metadata and schema overview

## Entities

- `create_entity` — create a new authoritative project entity (errors if id already exists)
- `upsert_entity` — create if missing or merge updates into an existing entity
- `update_entity` — update top-level fields (name, description, status) of an existing entity
- `archive_entity` — mark an entity archived without deleting history or relationships
- `delete_entity` — delete with guardrails; non-forced deletion requires prior archiving
- `merge_entities` — merge a duplicate source entity into a target with deterministic conflict handling
- `get_entity` — fetch a single entity and optionally its related metadata, content, and events
- `get_or_create_entity` — reuse an exact match when it exists or create with a generated stable id
- `list_entities` — filter/search entity list; supports type, status, attribute, tag, text; limit=50 default
- `find_similar_entities` — find likely duplicate or related entities before creating a new one
- `resolve_entity_by_name` — resolve a human-readable name to an existing entity

## Metadata

- `upsert_attributes` — create or update flexible key/value metadata for an entity
- `set_tags` — set or merge tag labels for an entity

## Relationships

- `add_relationship` — create a typed graph edge (caller supplies relationship_id)
- `connect_entities` — create a relationship if missing, otherwise return the existing edge (idempotent)
- `delete_relationship` — remove a relationship by id and record removal in project history
- `list_relationships` — list graph edges; filter by entity, type, and direction

## Content

- `write_content` — unified append|replace API; supports `text`, `markdown`, `json` content types
- `append_content` — convenience wrapper to add a new content record to an entity
- `search_content` — full-text search using FTS5 when available; LIKE fallback otherwise

## Snapshots

- `create_snapshot` — capture a named snapshot of current project state
- `get_snapshot` — fetch a named snapshot and its captured entities

## Views and query

- `list_views` — list available view names for `query_view` discovery
- `query_view` — query a named SQL view for reporting and model projections
- `run_read_query` — safe read-only SQL (SELECT/WITH/PRAGMA/EXPLAIN only); 200 row limit default

## Specialized read views

Dedicated tools that return pre-shaped payloads without requiring ad hoc SQL:

- `get_recent_activity` — recent entities, content, and events for AI context resumption
- `get_decision_log` — decisions with supporting note excerpts
- `get_architecture_summary` — compact architecture-oriented node and relationship summary
- `get_recent_reasoning` — recent reasoning excerpts for quick AI context recovery
- `get_dependency_view` — dependency-oriented graph data; supports root entity and max depth
- `get_entity_graph` — outward relationship traversal from a single entity

## Database health and maintenance

- `get_database_health` — report likely duplicates, low-quality records, and retention pressure
- `refresh_task_summary` — rebuild the task summary materialized table for faster open-task queries
- `apply_performance_tuning` — tune SQLite PRAGMA settings for heavy workloads (WAL, cache, mmap)
- `prune_content_retention` — prune older reasoning/log content; keeps most recent N records per entity

## Bootstrap and export

- `bootstrap_project_memory` — initialize a project root entity and standard memory-area anchors
- `render_markdown_views` — render markdown views in-memory; requires `user_requested=True` + reason
- `export_markdown_views` — write markdown views to disk; requires `user_requested=True` + reason

## Available `query_view` view names

- `open_tasks`
- `project_state`
- `project_summary`
- `decision_log`
- `architecture_summary`
- `recent_reasoning`
- `dependency_view`
- `recent_activity`
- `entity_graph`

> `project_summary` is implemented as a SQL view and is only accessible via `query_view(view_name='project_summary')` — there is no separate `@mcp.tool` for it.

## Resource endpoints

- `memory://schema`
- `memory://overview`
- `memory://recent-activity`
- `entity://{entity_id}`

## High-level AI-friendly guidance

1. Bootstrap once with `bootstrap_project_memory`.
2. For entity writes, prefer `upsert_entity` for idempotent upserts; use `create_entity` when you want strict creation errors. Use `update_entity` for simple field changes on known entities.
3. For content, use `write_content` (append or replace) as the primary API; use `append_content` as a convenience shortcut.
4. For read projections, prefer `query_view` as the unified interface or the dedicated read-view tools (`get_recent_activity`, `get_decision_log`, `get_architecture_summary`, etc.) over ad hoc SQL.
5. Use `find_similar_entities` or `resolve_entity_by_name` before creating new entities to avoid duplicates.
6. For relationship creation, prefer `connect_entities` (idempotent) over `add_relationship` unless you need to supply your own id.
7. Reserve maintenance tools for explicit workflows:
   - `render_markdown_views` / `export_markdown_views` — require `user_requested=True` + reason
   - `apply_performance_tuning` — run once post-bootstrap or after heavy bulk writes
   - `refresh_task_summary` — run after large task bulk operations
8. Use `get_database_health` and `prune_content_retention` for periodic hygiene.

## Installed CLI (`sqlite-project-memory-admin`)

Available after `pip install -e .` (or via installed package).

| Command | Purpose |
|---|---|
| `bootstrap-self` | Bootstrap the admin DB for self-hosting |
| `project-state` | Print project state summary |
| `health` | Run database health check |
| `performance-tune` | Apply performance PRAGMA settings |
| `refresh-task-summary` | Rebuild task summary table |
| `export-views` | Export markdown views to disk (supports `--force`, `--user-requested`, `--request-reason`) |
| `export-json` | Export full DB snapshot as JSON |
| `import-json` | Import a JSON snapshot |
| `sync-document` | Upsert a structured document into the memory store |

> `sync-document` is a CLI-only command; there is no corresponding `@mcp.tool` endpoint.

---

This summary is intended for integration engineers and external automation workflows.