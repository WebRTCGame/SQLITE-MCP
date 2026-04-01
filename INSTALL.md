# Quickstart: SQLite MCP Server

This guide covers a fresh install and updates. Two use cases, one command each.

## Prerequisites

- Windows 10/11, Linux, or macOS
- VS Code (or another MCP-compatible editor)
- Git
- Python 3.11+

---

## Fresh install

Clone the repo into a `sqlite-mcp` subfolder of your project and run the installer.
The installer detects its location, places all runtime files inside `Project Memory/`, and writes `.vscode/mcp.json`.

### Windows (PowerShell)

```powershell
cd "C:\Your\Project"
git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
.\sqlite-mcp\install.ps1
```

### Linux / macOS

```bash
cd /your/project
git clone https://github.com/WebRTCGame/SQLITE-MCP.git sqlite-mcp
chmod +x ./sqlite-mcp/install.sh
./sqlite-mcp/install.sh
```

After the installer finishes you will see:

```
=== Install complete ===
Project Memory: C:\Your\Project\Project Memory
MCP config:     C:\Your\Project\.vscode\mcp.json
```

---

## Update

Re-run the same command from your project root. The installer is idempotent:
- skips venv creation if `.venv` already exists
- re-runs `pip install -e .` to pick up any package changes
- overwrites the `sqlite-project-memory` entry in `.vscode/mcp.json`

---

## Optional: transcript logging

Pass `-LogFile` (PowerShell) or `--log-file` (bash) to save a full transcript for debugging:

```powershell
.\sqlite-mcp\install.ps1 -LogFile install.log
```

```bash
./sqlite-mcp/install.sh --log-file install.log
```

---

## Post-install verification

```powershell
& ".\Project Memory\.venv\Scripts\Activate.ps1"
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" project-state
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" health
```

```bash
source "Project Memory/.venv/bin/activate"
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" project-state
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" health
```

---

## Runtime layout

After install, your project contains only:

```
<your-project>/
  .vscode/
    mcp.json                  <- MCP server config
  Project Memory/
    .venv/                    <- Python virtual environment
    pm_data/
      project_memory.db       <- SQLite database
    pm_exports/               <- Generated markdown exports
    .install-complete         <- Idempotence marker
    src/                      <- sqlite-mcp source (nested install only)
    ...
```

Nothing from the sqlite-mcp checkout pollutes your project root.

---

## Optional post-install hook

Place `.scripts/post_install.ps1` (Windows) or `.scripts/post_install.sh` (Linux/macOS) in your project root. The installer runs it at the end if present.

---

## Export docs

```powershell
sqlite-project-memory-admin export-views --user-requested --request-reason "Initial docs export" --force todo roadmap architecture
```

---

## Troubleshooting

- Activate `.venv` before running `sqlite-project-memory-admin` commands.
- If `sqlite-project-memory-admin` is not found, confirm `pip install -e .` succeeded and the venv is active.
- For database issues, remove `Project Memory/pm_data/project_memory.db` and re-run `bootstrap-self`.

```powershell
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" bootstrap-self --repo-root .
```
