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

### Windows (PowerShell)

```powershell
# from your project root
git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
.\sqlite-mcp\install.ps1
```

Optional flag:
- `-LogFile install.log` — save a full transcript for debugging

### Linux / macOS

```bash
# from your project root
git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
chmod +x ./sqlite-mcp/install.sh
./sqlite-mcp/install.sh
```

Optional flag:
- `--log-file install.log` — save a full transcript for debugging

**To update:** re-run the same command. The installer is idempotent — it skips steps already done and upgrades the package in place.

### pip only (developer / advanced)

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install -e .
```

Full example:

```bash
./sqlite-mcp/install.sh
```

### Start server

```powershell
python -m sqlite_mcp_server
```

## Paths

- `Project Memory/.venv`
- `Project Memory/pm_data/project_memory.db`
- `Project Memory/pm_exports`
- `.vscode/mcp.json`

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

