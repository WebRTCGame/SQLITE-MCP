# SQLite Project Memory MCP

SQLite-backed MCP server for storing project memory as a graph-friendly relational core.

## Why this project

- Keeps authoritative state in SQLite (single source of truth).
- Provides graph semantics (`entities`, `relationships`, `content`, `tags`).
- Supports structured reads (`query_view`) and explicit generated markdown views.
- Designed for AI-agent-safe workflows.

## Core model

- `entities`
- `attributes`
- `relationships`
- `content`
- `tags`
- `events`, `snapshots`, `snapshot_entities` (audit/history)

## Supported `sync-document` targets

- Core documents: `architecture`, `decisions`, `plan`, `notes`, `roadmap`
- Extended docks: `kpi`, `okr`, `strategy`, `risk`, `issue`, `epic`, `story`, `feature`, `milestone`, `release`, `dependency`, `objective`, `initiative`, `metric`, `capability`, `assumption`, `problem_statement`, `retrospective`, `action_item`

## Install

Clone the repo into a `sqlite-mcp` subfolder of your project, then run the installer once.
The script detects its location, places all runtime files inside `Project Memory/`, and writes `.vscode/mcp.json`.

**No Python installation required.** The installer downloads `uv` and uses it to fetch
a pinned CPython 3.12.9 interpreter automatically. The interpreter is cached in
`Project Memory/.uv/python/` and the virtual environment is created in `Project Memory/.venv`.
If the `uv` download fails (e.g. behind a firewall) the installer falls back to any
Python 3.11+ already on the machine.

Important: open VS Code on your project root (the parent folder), not on the `sqlite-mcp` subfolder.
The MCP config is written to the project root at `.vscode/mcp.json`.

### Windows (PowerShell)

```powershell
# from your project root
git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
.\sqlite-mcp\install.ps1
```

Optional flag:
- `-LogFile install.log` — save a full transcript for debugging
- `-AppendInstructions` — append snippet to the suggested instructions file (idempotent)

### Linux / macOS

```bash
# from your project root
git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
chmod +x ./sqlite-mcp/install.sh
./sqlite-mcp/install.sh
```

Optional flag:
- `--log-file install.log` — save a full transcript for debugging
- `--append-instructions` — append snippet to the suggested instructions file (idempotent)

**To update:** after a successful nested install, the scripts live under `Project Memory/` because the `sqlite-mcp` checkout is moved there. Re-run the installer from your project root with `Project Memory\install.ps1` (Windows) or `Project Memory/install.sh` (Linux/macOS). For in-place/developer installs, re-run the same command.

### pip only (developer / advanced)

Used when you want to manage the environment yourself (requires Python 3.11+):

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install -e .
```

Or with uv directly (no system Python needed — uv downloads Python automatically):

```bash
uv venv --python 3.12.9 .venv
uv pip install -e .
```

Full example:

```bash
./sqlite-mcp/install.sh
```

### Start server

```powershell
& ".\Project Memory\.venv\Scripts\python.exe" -m sqlite_mcp_server
```

## Paths

- `Project Memory/.venv` — virtual environment (pinned Python 3.12.9)
- `Project Memory/.uv/bin/uv[.exe]` — uv runtime manager (downloaded by installer)
- `Project Memory/.uv/python/` — pinned CPython interpreter (fetched by uv on first run)
- `Project Memory/pm_data/project_memory.db`
- `Project Memory/pm_exports`
- `.vscode/mcp.json`
- `.vscode/settings.json` may also be created automatically by Copilot/VS Code with `chat.mcp.serverSampling` entries for `sqlite-project-memory`; this is expected.

To override the pinned Python version:
```powershell
$env:SQLITE_MCP_PYTHON_VERSION = "3.13.0"; .\sqlite-mcp\install.ps1
```
```bash
SQLITE_MCP_PYTHON_VERSION=3.13.0 ./sqlite-mcp/install.sh
```

## CLI tools

```powershell
sqlite-project-memory-admin bootstrap-self --repo-root .
sqlite-project-memory-admin project-state
sqlite-project-memory-admin health
sqlite-project-memory-admin sync-document architecture --input-path architecture.md
sqlite-project-memory-admin sync-document decisions --input-path decisions.md
sqlite-project-memory-admin sync-document roadmap --input-path roadmap.md
sqlite-project-memory-admin export-views --user-requested --request-reason "User asked for a roadmap export" --require-existing-dir exports todo roadmap architecture
sqlite-project-memory-admin export-views --user-requested --request-reason "User asked for refreshed generated docs" --force todo roadmap architecture
sqlite-project-memory-admin export-json --output-path exports/project_memory.snapshot.json
sqlite-project-memory-admin import-json --input-path exports/project_memory.snapshot.json
```

## Configuration

Environment variables:

- `SQLITE_MCP_PROJECT_ROOT`
- `SQLITE_MCP_DB_PATH`
- `SQLITE_MCP_EXPORT_DIR`
- `SQLITE_MCP_TRANSPORT` (`stdio` or `streamable-http`)
- `SQLITE_MCP_LOG_LEVEL` (`INFO` default)
- `SQLITE_MCP_LOG_FORMAT` (`json` or `text`)

## Post-install hook

- Create `.scripts/post_install.ps1` (PowerShell) or `.scripts/post_install.sh`.
- The install script executes the hook if present.

## Quick start (Windows)

1. Clone the repo into your project.
2. Run the installer:
   ```powershell
   git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
   .\sqlite-mcp\install.ps1
   ```
   After install, ensure VS Code is opened at the parent project root (for example `C:\CODE\TestProject`), not `C:\CODE\TestProject\sqlite-mcp`.
3. Activate runtime venv:
   ```powershell
   & ".\Project Memory\.venv\Scripts\Activate.ps1"
   ```
4. Run self-check:
   ```powershell
   sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" project-state
   sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" health
   ```
5. Start the server:
   ```powershell
   python -m sqlite_mcp_server
   ```

## Quick start (Linux/macOS)

1. Clone the repo into your project.
2. Run the installer:
   ```bash
   git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
   chmod +x ./sqlite-mcp/install.sh
   ./sqlite-mcp/install.sh
   ```
   After install, ensure VS Code is opened at the parent project root, not the `sqlite-mcp` subfolder.
3. Activate runtime venv:
   ```bash
   source "Project Memory/.venv/bin/activate"
   ```
4. Run self-check:
   ```bash
   sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" project-state
   sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" health
   ```
5. Start the server:
   ```bash
   python -m sqlite_mcp_server
   ```

## Notes

- `render_markdown_views`/`export_markdown_views` require `user_requested=true` and `request_reason`.
- `sync-document` is anchored (no unstructured free-text record in roadmap state).
- `project_state` and `health` are primary diagnostics.

## AI-first design

- Write entities/content through MCP tools.
- Generate docs only on explicit user request.

## Add AI instructions to your project

After running the installer, paste the snippet below into your AI instructions file
(`copilot-instructions.md`, `AGENTS.md`, `CLAUDE.md`, or equivalent).
The installer also prints this snippet to the terminal as a reminder.

```markdown
## SQLite Project Memory

This project uses the **`sqlite-project-memory` MCP server** as the single source of truth for all project state.

### Mandatory rules

- **NEVER** create, modify, or delete `.md` files for notes, tasks, decisions, roadmaps, or architecture.
- **ALWAYS** use `sqlite-project-memory` MCP tools to store and retrieve project knowledge.
- `README.md` is the **only** markdown file you may edit directly.
- Files in `Project Memory/pm_exports/` are read-only derived artifacts — never edit them directly.

### Tool usage guide

| Intent | Tool to use |
|--------|-------------|
| Add a task / todo | `create_entity` (entity_type: `task`) |
| Record a decision | `create_entity` (entity_type: `decision`) |
| Document a component | `create_entity` (entity_type: `component`) + `write_content` |
| Add a note to an item | `write_content` or `append_content` |
| Query project state | `query_view`, `list_entities`, `get_entity` |
| Search knowledge | `search_content` |
| Link two items | `add_relationship` or `connect_entities` |
| Export to markdown | `export_markdown_views` with `user_requested: true` — only when explicitly asked |

### First action each session

Before making changes, call `get_project_context` to confirm the database path and project root, then call `get_recent_activity` or `query_view` to orient yourself.
```

## Usage gates checklist

For best reliability, confirm all of the following:

1. `.vscode/mcp.json` contains the `sqlite-project-memory` server.
2. VS Code MCP approval/trust prompt was accepted for this workspace.
3. Chat is in Agent mode (not regular chat/edit mode).
4. `Project Memory` agent is available in the agents dropdown.
5. `/sqlite-project-memory` skill is available in slash commands.
6. Your project instructions file includes the SQLite Project Memory snippet.
7. Start each session with `get_project_context` then `get_recent_activity` or `query_view`.

The installer prints a `Usage Gates Report` with `PASS` or `ACTION REQUIRED` for the gates it can validate automatically.
If tools still do not appear, first fully reload or restart VS Code and start a new Agent chat session.
If the server is not already running after restart, run `MCP: Start Server` from the Command Palette, select `sqlite-project-memory`, and restart the chat session.

