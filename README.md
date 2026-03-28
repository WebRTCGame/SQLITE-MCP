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
- `get_recent_activity`
- `get_entity_graph`
- `bootstrap_project_memory`
- `run_read_query`
- `render_markdown_views`
- `export_markdown_views`
- `server_info`

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

## Configuration

Environment variables:

- `SQLITE_MCP_DB_PATH`: override the SQLite database file path.
- `SQLITE_MCP_TRANSPORT`: `stdio` or `streamable-http`.
- `SQLITE_MCP_EXPORT_DIR`: default output directory for generated markdown views.

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
- `render_markdown_views` and `export_markdown_views` when human-readable `todo`, `roadmap`, `plan`, `architecture`, `decisions`, or `notes` files are needed.

The intended pattern is:

1. Use explicit domain tools for writes.
2. Use `run_read_query` only for read-only inspection.
3. Generate markdown views only when a person or downstream tool needs a document.
4. Keep SQLite authoritative.

## Suggested Modeling Conventions

- Use stable ids such as `task.auth-flow`, `file.src.server`, `decision.schema-graph-core`.
- Keep `type` broad and durable: `task`, `file`, `module`, `decision`, `feature`, `plan`, `note`.
- Put volatile metadata in `attributes`, not in new tables.
- Use `content_type` to distinguish `note`, `spec`, `analysis`, `reasoning`, `log`.
- Use relationships deliberately: `depends_on`, `implements`, `blocks`, `calls`, `owns`.
