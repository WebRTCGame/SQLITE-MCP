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

## Install (cross-platform)

### AI-friendly install from scratch

```powershell
# from project parent folder
git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
cd sqlite-mcp
.\install.ps1 -ProjectRoot ".." -MigrateExisting -UseProjectConfig -CiMode -LogFile install.log

# OR on Linux/macOS
chmod +x ./install.sh
./install.sh --project-root ".." --migrate-existing --use-project-config --ci --log-file install.log
```

> Note: If your host project folder is not the checkout path or does not contain `pyproject.toml`, the install scripts will detect that and use the script checkout as the Python package source for `pip install -e`. The `Project Memory` folder still holds runtime state (`pm_data`, `.venv`, `pm_exports`).

### Option A: pip only

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # windows
# or source .venv/bin/activate  # linux/macos
python -m pip install -e .
```

### Option B: PowerShell script (Windows or pwsh)

```powershell
.\install.ps1
```

Recommended options:
- `-MigrateExisting` (move old `.venv`, `data`, `exports` into `Project Memory`)
- `-UseProjectConfig` (default; writes `.vscode/mcp.json`)
- `-UseGlobalConfig` (writes to VS Code AppData location)
- `-McpConfigPath <path>` (explicit config file path)
- `-CiMode` (non-interactive CI install)
- `-FetchOnly` (git fetch only)
- `-Branch <branch>` (checkout branch first)
- `-LogFile <path>` (transcript logging)

Full example:

```powershell
.\install.ps1 -MigrateExisting -UseProjectConfig -CiMode -LogFile install.log
```

### Option C: Bash script (Linux/macOS)

```bash
chmod +x ./install.sh
./install.sh
```

Recommended options:
- `--migrate-existing`
- `--use-project-config`
- `--use-global-config`
- `--mcp-config-path <path>`
- `--ci`
- `--fetch-only`
- `--branch <branch>`
- `--log-file <path>`

Full example:

```bash
./install.sh --migrate-existing --use-project-config --ci --log-file install.log
```

### Start server

```powershell
python -m sqlite_mcp_server
```

## Paths

- `Project Memory/.venv`
- `Project Memory/pm_data/project_memory.db`
- `Project Memory/pm_exports`
- `.vscode/mcp.json` (default local config) or global path

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

## Quick start

1. Clone the repo.
2. Run the one-shot installer (from checkout):
   ```powershell
   .\install.ps1 -ProjectRoot . -MigrateExisting -UseProjectConfig -CiMode -LogFile install.log
   ```
3. Activate runtime venv:
   ```powershell
   .\Project Memory\.venv\Scripts\Activate.ps1
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

## Notes

- `render_markdown_views`/`export_markdown_views` require `user_requested=true` and `request_reason`.
- `sync-document` is anchored (no unstructured free-text record in roadmap state).
- `project_state` and `health` are primary diagnostics.

## AI-first design

- Write entities/content through MCP tools.
- Generate docs only on explicit user request.

