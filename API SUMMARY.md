# SQLite Project Memory MCP API Summary

This file provides a compact reference for the MCP server toolset and integration patterns.

> Total MCP tools exposed: 35
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

## Entities (Core)

- `upsert_entity` (core, done, covered by tests, active)
  - status: primary write API; create/update merge.
  - tests: included in test cases and 41-pass suite.
- `get_entity` (core, done, covered, active)
  - status: single-entity retrieval with optional related payload.
- `list_entities` (core, done, covered, active)
  - status: filter/search entity list; limit=50 default.
- `delete_entity` (core, done, covered, active)
  - status: safe delete with optional force semantics and event audit.

## Relationships (Core)

- `connect_entities` (core, done, covered, active)
  - status: idempotent edge creation; avoids duplicate relationships.
- `list_relationships` (core, done, covered, active)
  - status: graph traversal with filtering by direction/type.
- `delete_relationship` (core, done, covered, active)
  - status: safely removes graph edges; updates audit events.

## Content (Core)

- `write_content` (core, done, covered, active)
  - status: unified append|replace with strict mode; supports `text`, `markdown`, `json` content types.
- `search_content` (core, done, covered, active)
  - status: full-text and LIKE fallback; FTS5 optimized when enabled.

## Metadata (Core)

- `upsert_attributes` (core, done, covered, active)
- `set_tags` (core, done, covered, active)

## Query / Views (Core)

- `query_view` (core, done, covered, active)
  - status: central reporting API; serves model projections from SQL views.
- `run_read_query` (core, done, covered, active)
  - status: safe read-only SQL with token filtering and 1000 row limit.

## System (Core)

- `get_project_context` (system, done, covered, active)
  - status: runtime project context read.
- `server_info` (system, done, covered, active)
  - status: full server metadata and schema overview.
- `get_database_health` (system, done, covered, active)
  - status: quality and reference checks, used by design.

## Utilities

- `create_snapshot` (done, covered, active)
- `get_snapshot` (done, covered, active)
- `sync_document` (new target list support):
  - `architecture`, `decisions`, `plan`, `notes`, `roadmap`
  - `kpi`, `okr`, `strategy`, `risk`, `issue`, `epic`, `story`, `feature`,
  - `milestone`, `release`, `dependency`, `objective`, `initiative`, `metric`,
  - `capability`, `assumption`, `problem_statement`, `retrospective`, `action_item`

## Maintenance tools

- `run_read_query` (read only: SELECT/WITH/PRAGMA/EXPLAIN, no writes)
- `render_markdown_views` (strict user_requested policy)
- `export_markdown_views` (strict user_requested + force + require_existing_dir policy)
- `prune_content_retention`
- `bootstrap_project_memory`
- `apply_performance_tuning`
- `refresh_task_summary`

## Context and management tools

- `list_views` returns all supported summary views: `open_tasks`, `project_state`, `project_summary`, `decision_log`, `architecture_summary`, `recent_reasoning`, `dependency_view`, `recent_activity`, `entity_graph`.
- `query_view` now consolidates all projection views, including `open_tasks`, `project_state`, `project_summary`, `decision_log`, `architecture_summary`, `recent_reasoning`, `dependency_view`, `recent_activity`, `entity_graph`.
- `project_summary` is implemented as a SQL view and is accessible only through `query_view(view_name='project_summary')`; no separate `@mcp.tool` endpoint exists.
- Legacy dedicated summary wrapper endpoints are removed from the core projection path; read projections should use `query_view`.

## Maintenance tools

- `run_read_query` (read only: SELECT/WITH/PRAGMA/EXPLAIN, no writes)
- `render_markdown_views` (strict user_requested policy)
- `export_markdown_views` (strict user_requested + force + require_existing_dir policy)
- `prune_content_retention`
- `bootstrap_project_memory`
- `apply_performance_tuning`
- `refresh_task_summary`

## Context and management tools

- `get_project_context` (read-only)
- `set_project_root` (mutable, switches active project context and reconnects DB)
- `server_info`

## Resource endpoints

- `memory://schema`
- `memory://overview`
- `memory://recent-activity`
- `entity://{entity_id}`

## High-level AI-friendly guidance

1. Bootstrap once with `bootstrap_project_memory`.
2. For write operations, use core primitives: `upsert_entity`, `connect_entities`, and `write_content`.
3. For read projections, prefer `query_view` as the unified interface (including `project_summary`).
   - `open_tasks`
   - `project_state`
   - `project_summary`
   - `recent_activity`
   - `decision_log`
   - `architecture_summary`
   - `recent_reasoning`
   - `dependency_view`
   - `entity_graph`
4. Reserve the following admin/ops tools for maintenance workflows (not core AI retrieval):
   - `render_markdown_views` (requires `user_requested=true` + reason)
   - `export_markdown_views` (requires `user_requested=true` + reason)
   - `apply_performance_tuning`
   - `refresh_task_summary`
5. Use `get_database_health` and `prune_content_retention` for hygiene.
6. No wrapper tools: use primitive CRUD and `query_view` only.

## Installed CLI

- `sqlite-project-memory-admin` is available after `pip install -e .`
- common commands:
  - `bootstrap-self`
  - `project-state`
  - `health`
  - `export-views`
  - `sync-document`
  - `export-json` / `import-json`

---

This summary is intended for integration engineers and external automation workflows.