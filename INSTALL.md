# Quickstart: SQLite MCP Server (Clean VS Code Insiders + Git repo)

This guide assumes:
- Windows 10/11 or similar (works on Linux/macOS with path tweaks)
- VS Code Insiders installed
- Git installed
- A new empty project folder with `git init` already run
- No existing Python virtual environment in the folder

## 0. Keep local files up to date (new install behavior)

If you re-run `install.ps1`, it now syncs your working tree from `origin` first (auto `git fetch` and `git pull --ff-only`), so local code reflects the latest GitHub changes. Existing database state at `data/project_memory.db` is preserved.

If the target repository already has `./data` or `./exports`, they are not moved by default. To migrate existing project artifacts into the self-contained `Project Memory` folder (to `pm_data` and `pm_exports`), run:

If the path you pass with `--project-root` does not contain `pyproject.toml`, the installer will use the checkout location (`sqlite-mcp`) as the source for `pip install -e` and still write runtime state under `Project Memory`.

```powershell
.\install.ps1 -MigrateExisting
```

To keep the config local in `.vscode/mcp.json` (works for non-Insiders editors and other tools such as Claude Code), run:

```powershell
.\install.ps1 -UseProjectConfig
```

To explicitly use global Code/Insiders MCP config:

```powershell
.\install.ps1 -UseGlobalConfig
```

To specify an explicit path in any environment:

```powershell
.\install.ps1 -McpConfigPath "D:\custom\mcp.json"
```

### Advanced automation modes

- `-CiMode`: non-interactive CI-friendly mode (forces project config + no confirmation)
- `-FetchOnly`: run only git fetch and exit
- `-Branch <name>`: checkout and merge this branch
- `-NonInteractive`: suppress any prompt behaviour
- `post_install` hook: place `.scripts\post_install.ps1` in repo for custom post steps

## 1. Clone or initialize project

```powershell
cd "D:\Programming Projects"
mkdir "SQLITE-MCP" # if needed
cd "SQLITE-MCP"
git init
```

Or if cloning an existing repo:

```powershell
git clone https://github.com/WebRTCGame/SQLITE-MCP.git .
```

## 2. One-shot install and self-check

### Windows (PowerShell)
```powershell
.\install.ps1 -ProjectRoot . -MigrateExisting -UseProjectConfig -CiMode -LogFile install.log
.\Project Memory\.venv\Scripts\Activate.ps1
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" project-state
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" health
```

### Linux/macOS (bash)
```bash
chmod +x ./install.sh
./install.sh --project-root . --migrate-existing --use-project-config --ci --log-file install.log
source "Project Memory/.venv/bin/activate"
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" project-state
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" health
```
```

## 2. Open folder in VS Code Insiders

- Launch VS Code Insiders
- File -> Open Folder -> select `D:\Programming Projects\SQLITE-MCP`
- Confirm the workspace folder is active and your terminal defaults to it.

## 3. Create Python virtual environment (.venv)

In the integrated terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> `.venv` is local to this project. Each project should create its own virtual environment; you do not copy the `.venv` folder between projects.

## 4. Install dependencies

Within the activated environment:

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
```

If this project uses Poetry or pip-tools, follow that repo’s guidance instead.

## 5. Initial run

```powershell
python -m sqlite_mcp_server
```

Expected:
- Server starts
- Default DB path is `data/project_memory.db`
- A read-only query interface is available via MCP tool wiring (stdio/HTTP).

## 6. Validate with admin CLI

```powershell
sqlite-project-memory-admin bootstrap-self --repo-root .
sqlite-project-memory-admin project-state
sqlite-project-memory-admin health
```

## 7. MCP client configuration

The installer now writes only the global MCP host config at:
`%APPDATA%\Code - Insiders\User\mcp.json`

This avoids per-project `.vscode/mcp.json` collisions and ensures a consistent handler across projects.

If you need project-specific behavior, use `get_project_context`/`set_project_root` in the MCP API.

## 7. Common workflow notes

- This project treats SQLite as the authoritative memory store.
- Markdown files are generated views (via `export-markdown-views`) and are not the canonical source.
- To write state, use MCP tools: `upsert_entity`, `connect_entities`, `append_content`, etc.

## 8. Optional: export docs

```powershell
sqlite-project-memory-admin export-views --user-requested --request-reason "Initial docs export" --force todo roadmap architecture
```

## 9. Troubleshooting

- Activate `.venv` before running commands to ensure the right Python environment.
- If `sqlite-project-memory-admin` is not found, confirm `python -m pip install -e .` succeeded and `.venv\Scripts` is in PATH.
- For database issues, remove `data/project_memory.db` and rerun bootstrap.

## 10. Cleanup

When done, deactivate:

```powershell
deactivate
```

## 11. Bash/macOS/Linux install

### AI-friendly one-shot

```bash
cd /path/to/project/root
# clone the installer repository
git clone https://github.com/YOUR_ORG/SQLITE-MCP.git sqlite-mcp
cd sqlite-mcp
# run installer explicitly in project path
chmod +x ./install.sh
./install.sh --project-root "$PWD" --migrate-existing --use-project-config --ci --log-file install.log
```

1. Make script executable `chmod +x ./install.sh`
2. Run `./install.sh`
3. Options:
   - `--migrate-existing` (move edges into Project Memory)
   - `--use-global-config` (use $HOME/.config Code config instead of `.vscode/mcp.json`)
   - `--mcp-config-path <path>` (explicit config file path)
   - `--fetch-only` (only git fetch)
   - `--branch <name>`
   - `--ci` (non-interactive)
