# SQLite Project Memory MCP

SQLite-backed MCP server for storing project memory as a graph-friendly relational core.

The server is designed around four rules:

1. Everything is an entity.
2. Everything can relate to everything.
3. State is authoritative.
4. Narrative is separate from structure.

Instead of generating and maintaining many parallel documents, the MCP server stores project state in SQLite and exposes tools for safe access. Files such as `todo.md` or `roadmap.md` can be generated later on explicit request as views, not treated as the source of truth.

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
- `project_summary` is now provided through `query_view(view_name='project_summary')` (SQL view) and is deprecated as direct helper.
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

High-frequency summary tools default to `compact=true` at the MCP boundary and return an explicit schema envelope for stable machine consumption unless a caller opts out.
`get_recent_activity` now supports `limit`, `offset`, and `compact`, and `get_entity_graph` uses explicit node and edge limits so large graph reads stay bounded.

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
```

# Global MCP config (preferred)
The install script now registers the MCP server entry in the global user-level old `mcp.json` only:
`%APPDATA%\Code - Insiders\User\mcp.json`. This avoids duplicate project-local entries.

Then launch the server once:

```powershell
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

- `SQLITE_MCP_PROJECT_ROOT`: optional explicit project directory root for context-sensitive DB and export paths.
- `SQLITE_MCP_DB_PATH`: optional override path for the SQLite database file, interpreted relative to `SQLITE_MCP_PROJECT_ROOT` when not absolute; default is `data/project_memory.db` under project root.
- `SQLITE_MCP_EXPORT_DIR`: optional override path for generated markdown export files, interpreted relative to project root when not absolute; default is `exports` under project root.
- `SQLITE_MCP_TRANSPORT`: `stdio` or `streamable-http`.
- `SQLITE_MCP_LOG_LEVEL`: log level for server lifecycle and tool request logs. Defaults to `INFO`.
- `SQLITE_MCP_LOG_FORMAT`: `json` or `text` for stderr logs. Defaults to `json`.

Project context tools (in MCP API):

- `get_project_context()` returns the currently configured project root, db_path, and export_dir.
- `set_project_root(project_root)` switches the active project context at runtime and reconnects using project-local file paths.

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

Roadmap state is different: it is maintained directly through SQLite entities, attributes, relationships, and content. There is no supported `roadmap.md` import workflow anymore. If an AI needs to change roadmap state, it should use normal MCP write tools such as `upsert_entity`, `append_content`, `set_tags`, and `connect_entities`, then generate `roadmap.md` only when a user explicitly asks for that artifact.

The intended pattern is:

1. Use explicit domain tools for writes.
2. Use `query_view` for summary and projection reads.
   - `query_view(view_name='project_summary')`
   - `query_view(view_name='open_tasks')`
   - `query_view(view_name='project_state')`
   - `query_view(view_name='recent_activity')`
   - `query_view(view_name='decision_log')`
   - `query_view(view_name='architecture_summary')`
   - `query_view(view_name='recent_reasoning')`
   - `query_view(view_name='dependency_view')`

3. Use `run_read_query` only for read-only inspection when the built-in summary views are not enough.
4. Generate markdown views only when a user explicitly asks for a document, and pass that request through the MCP call.
5. Keep SQLite authoritative.

For long-running AI usage, the hygiene tools matter as much as the write tools:

- `find_similar_entities` helps avoid creating duplicate memory objects.
- `resolve_entity_by_name` lets the AI reuse existing entities when a human-style name is all it has.
- `get_or_create_entity` gives the AI a safer name-first workflow with stable id generation.
- `get_database_health` reports duplicate candidates, invalid statuses, low-signal attributes, and retention pressure.
- `prune_content_retention` provides a controlled cleanup path for high-volume `reasoning` and `log` content.

## Policy Decisions

The remaining phase 7 modeling decisions are now explicit:

- Canonical entity ids: generated ids use `<entity_type>.<slug>[.<n>]`. Project-scoped memory-area anchors may use project-prefixed ids such as `project.sqlite-mcp.roadmap`.
- Relationship vocabulary: use the built-in relationship set when possible, and use the `custom.` namespace for project-specific edges. There is no registry table.
- Attribute keys: common unnamespaced keys are reserved for shared fields such as `priority`, `owner`, `phase_number`, `path`, and `source`. New custom keys should use lowercase dotted namespaces such as `meta.*`, `source.*`, `client.*`, `trace.*`, or `ui.*`.
- Status vocabulary: common entity types use a shared status vocabulary exposed by the schema, and other entity types may use stable identifier-style statuses when a specialized lifecycle is required.
- Retention: `reasoning` and `log` content are the only default retention-managed content types, with a recommended keep-latest count of `20` and dry-run-first pruning.
- Markdown generation: markdown views are on-demand only and SQLite remains authoritative.
- MCP read defaults: high-frequency read tools default to `compact=true` and callers opt out with `compact=false` when they need fuller payloads.
- Semantic retrieval: the baseline stays on SQLite FTS5 plus structured read models. Embeddings are intentionally out of scope unless a concrete retrieval gap appears that those mechanisms cannot cover.

These policy decisions are also exposed programmatically through `schema_overview()` / `memory://schema` and checked in `get_database_health()` where appropriate.

## Suggested Modeling Conventions

- Use stable ids such as `task.auth-flow`, `file.src.server`, `decision.schema-graph-core`.
- Keep `type` broad and durable: `task`, `file`, `module`, `decision`, `feature`, `plan`, `note`.
- Put volatile metadata in `attributes`, not in new tables.
- Use `content_type` to distinguish `note`, `spec`, `analysis`, `reasoning`, `log`.
- Use relationships deliberately: `depends_on`, `implements`, `blocks`, `calls`, `owns`.

## Quick start scripts

For a one-command local setup from an empty repo root on Windows, run:

PowerShell:
```powershell
.\install.ps1
```

CMD/Bash:
```bash
install.bat
```

These scripts perform:
- `git init` (if needed)
- `python -m venv .venv`
- Activate `.venv`
- `pip install -e .`
- `sqlite-project-memory-admin bootstrap-self --repo-root .`
- `sqlite-project-memory-admin project-state`
- `sqlite-project-memory-admin health`

Then start server with:
```powershell
python -m sqlite_mcp_server
```
