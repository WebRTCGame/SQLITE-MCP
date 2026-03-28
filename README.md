# SQLite Project Memory MCP

SQLite-backed MCP server for storing project memory as a graph-friendly relational core.

The server is designed around four rules:

1. Everything is an entity.
2. Everything can relate to everything.
3. State is authoritative.
4. Narrative is separate from structure.

Instead of generating and maintaining many parallel documents, the MCP server stores project state in SQLite and exposes tools for safe access. Files such as `todo.md` or `roadmap.md` can be generated later as views, not treated as the source of truth.

## What It Stores

The schema supports project memory such as:

- tasks
- file metadata
- dependencies
- decisions
- roadmap items
- architecture elements
- plans
- notes
- todos
- reasoning records
- snapshots and audit history

Everything is modeled through generic tables:

- `entities`
- `attributes`
- `relationships`
- `content`
- `events`
- `snapshots`
- `snapshot_entities`
- `tags`

The server also creates an FTS5 index for `content.body` when available.

## Key MCP Tools

- `create_entity`
- `upsert_entity`
- `update_entity`
- `get_entity`
- `list_entities`
- `find_similar_entities`
- `resolve_entity_by_name`
- `get_or_create_entity`
- `upsert_attributes`
- `set_tags`
- `add_relationship`
- `connect_entities`
- `list_relationships`
- `add_content`
- `append_content`
- `search_content`
- `create_snapshot`
- `get_snapshot`
- `get_project_overview`
- `get_project_state`
- `get_open_tasks`
- `get_decision_log`
- `get_architecture_summary`
- `get_recent_reasoning`
- `get_dependency_view`
- `get_recent_activity`
- `get_database_health`
- `prune_content_retention`
- `get_entity_graph`
- `bootstrap_project_memory`
- `run_read_query`
- `render_markdown_views` with `user_requested=true` and a request reason
- `export_markdown_views` with `user_requested=true` and a request reason
- `server_info`

High-frequency summary tools also support a `compact=true` mode that returns an explicit schema envelope for stable machine consumption.

## Resources And Prompt

- `memory://schema`
- `memory://overview`
- `memory://recent-activity`
- `entity://{entity_id}`
- prompt: `project_memory_policy`

## Run

### Option 1: pip

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m sqlite_mcp_server
```

### Option 2: uv

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -e .
python -m sqlite_mcp_server
```

The default database path is `data/project_memory.db` under the repository root.

## Admin CLI

For local bootstrap and inspection workflows, the package also exposes an admin CLI:

```powershell
sqlite-project-memory-admin bootstrap-self --repo-root .
sqlite-project-memory-admin project-state
sqlite-project-memory-admin health
sqlite-project-memory-admin export-views --user-requested --request-reason "User asked for a roadmap export" --require-existing-dir exports todo roadmap architecture
sqlite-project-memory-admin export-views --user-requested --request-reason "User asked for refreshed generated docs" --force todo roadmap architecture
sqlite-project-memory-admin sync-document architecture --input-path architecture.md
sqlite-project-memory-admin sync-document decisions --input-path decisions.md
sqlite-project-memory-admin export-json --output-path exports/project_memory.snapshot.json
sqlite-project-memory-admin import-json --input-path exports/project_memory.snapshot.json
```

This is mainly useful when you want the project to use its own SQLite memory store without writing one-off scripts.
Generated markdown export is locked by default: it refuses to render or write views unless the caller explicitly marks the request as user-requested and supplies a reason. It also refuses to overwrite existing view files unless `--force` is provided, and `--require-existing-dir` can be used when automation should fail instead of creating a new output directory.

## Sample MCP Config

A repo-local sample MCP client configuration is available at [.vscode/mcp.sample.json](d:/Programming%20Projects/SQLITE%20MCP/SQLITE-MCP/.vscode/mcp.sample.json). Adjust the Python path if needed for another machine.

## Configuration

Environment variables:

- `SQLITE_MCP_DB_PATH`: override the SQLite database file path.
- `SQLITE_MCP_TRANSPORT`: `stdio` or `streamable-http`.
- `SQLITE_MCP_EXPORT_DIR`: default output directory for generated markdown views.
- `SQLITE_MCP_LOG_LEVEL`: log level for server lifecycle and tool request logs. Defaults to `INFO`.
- `SQLITE_MCP_LOG_FORMAT`: `json` or `text` for stderr logs. Defaults to `json`.

Example:

```powershell
$env:SQLITE_MCP_DB_PATH = "D:\memory\project.db"
$env:SQLITE_MCP_TRANSPORT = "stdio"
python -m sqlite_mcp_server
```

## Design Notes

- Entity ids, relationship ids, tags, types, and attribute keys are validated.
- Duplicate entities are prevented by primary key.
- Duplicate edges are prevented by a unique constraint on `(from_entity, to_entity, type)`.
- Narrative content is stored separately from authoritative state.
- Mutating operations record audit events.
- Raw arbitrary SQL write access is intentionally not exposed through MCP tools.
- A constrained read-only SQL tool is available for diagnostics and ad hoc retrieval.
- Markdown files are treated as generated views, not storage.

## AI-First Tooling Guidance

If this server is going to be called frequently by an AI, the useful surface is not a single `RUN SQL` tool. The practical surface is:

- `bootstrap_project_memory` to initialize a project root and standard memory areas.
- `upsert_entity` so the AI can write idempotently instead of guessing whether to create or update.
- `connect_entities` so repeated graph writes do not produce duplicate edges.
- `append_content` so narrative memory can be added without the AI having to mint content ids every time.
- `get_recent_activity` so an AI can resume context quickly after a new session.
- `run_read_query` for controlled read-only analytics when the built-in tools are not enough.
- `render_markdown_views` and `export_markdown_views` only after the user explicitly asks for a human-readable `todo`, `roadmap`, `plan`, `architecture`, `decisions`, or `notes` document.

`render_markdown_views` and `export_markdown_views` are intentionally locked behind an explicit user-request contract so an AI does not casually generate markdown and then start using those files as a substitute for SQLite.

`export_markdown_views` also supports explicit overwrite control so generated documents do not silently replace existing files.

For the remaining human-facing documents, `sync-document` provides a structured migration path into the anchor memory areas for `architecture`, `decisions`, `plan`, and `notes`. The generated views then combine that synced document content with the structured SQLite state instead of rendering a flat dump.

The intended pattern is:

1. Use explicit domain tools for writes.
2. Use summary-first read tools such as `get_project_state`, `get_open_tasks`, `get_decision_log`, `get_architecture_summary`, `get_recent_reasoning`, and `get_dependency_view` before falling back to lower-level queries.
3. Use `run_read_query` only for read-only inspection when the built-in summaries are not enough.
4. Generate markdown views only when a user explicitly asks for a document, and pass that request through the MCP call.
5. Keep SQLite authoritative.

For long-running AI usage, the hygiene tools matter as much as the write tools:

- `find_similar_entities` helps avoid creating duplicate memory objects.
- `resolve_entity_by_name` lets the AI reuse existing entities when a human-style name is all it has.
- `get_or_create_entity` gives the AI a safer name-first workflow with stable id generation.
- `get_database_health` reports duplicate candidates, invalid statuses, low-signal attributes, and retention pressure.
- `prune_content_retention` provides a controlled cleanup path for high-volume `reasoning` and `log` content.

## Suggested Modeling Conventions

- Use stable ids such as `task.auth-flow`, `file.src.server`, `decision.schema-graph-core`.
- Keep `type` broad and durable: `task`, `file`, `module`, `decision`, `feature`, `plan`, `note`.
- Put volatile metadata in `attributes`, not in new tables.
- Use `content_type` to distinguish `note`, `spec`, `analysis`, `reasoning`, `log`.
- Use relationships deliberately: `depends_on`, `implements`, `blocks`, `calls`, `owns`.
