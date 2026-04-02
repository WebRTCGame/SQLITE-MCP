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

Optional: append the SQLite Project Memory snippet automatically to the suggested instructions file:

```powershell
.\sqlite-mcp\install.ps1 -AppendInstructions
```

```bash
./sqlite-mcp/install.sh --append-instructions
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
  .github/
    agents/
      project-memory.agent.md <- Custom agent for project memory tasks
    skills/
      sqlite-project-memory/
        SKILL.md              <- Agent skill for on-demand MCP tool guidance
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

## AI customizations deployed

The installer writes three files into `.github/` so Copilot (and other compatible AI agents) know to use the MCP server instead of creating markdown files:

| File | Purpose |
|------|---------|
| `assets/copilot-instructions-snippet.md` | Printed to the terminal at install time — copy and paste into your existing instructions file |
| `.github/agents/project-memory.agent.md` | Custom agent persona — select **Project Memory** in the Agents dropdown |
| `.github/skills/sqlite-project-memory/SKILL.md` | On-demand skill — type `/sqlite-project-memory` or let Copilot auto-load it |

The agent and skill files are copied automatically. The instructions snippet is **not** written automatically — you may already have a `copilot-instructions.md`, `AGENTS.md`, `CLAUDE.md`, or another file you want to preserve. The installer prints the snippet to the terminal so you can paste it wherever is appropriate for your setup.

The installer also helps with this step:

- best-effort copies the snippet to your clipboard (`Set-Clipboard` on PowerShell; `pbcopy`/`wl-copy`/`xclip`/`xsel` on Linux/macOS)
- suggests a target file path (`.github/copilot-instructions.md`, `AGENTS.md`, or `CLAUDE.md`)
- if `code` is available on PATH, opens the suggested target in VS Code
- optional `-AppendInstructions` / `--append-instructions` appends the snippet automatically (once) to the suggested target file
- prints a `Usage Gates Report` at the end showing `PASS` vs `ACTION REQUIRED`

> **Important:** Use **Agent mode** in VS Code Chat (the lightning-bolt icon). MCP tools are not invoked in regular Copilot Chat or Edit mode.

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
- Verify the MCP server was approved/trusted in VS Code after install; if not approved, tools will not load.
- Use Agent mode and select `Project Memory` agent (or invoke `/sqlite-project-memory`) before asking memory-management tasks.
- In VS Code Chat, use `...` -> `Diagnostics` to verify custom instructions, skills, and agents were discovered.

```powershell
sqlite-project-memory-admin --db-path "Project Memory/pm_data/project_memory.db" bootstrap-self --repo-root .
```

## Usage gates checklist

To maximize reliable MCP usage, all gates below should be true:

1. `.vscode/mcp.json` contains `sqlite-project-memory` server config.
2. VS Code has approved/trusted the MCP server for this workspace.
3. Agent mode is active in Chat.
4. `.github/agents/project-memory.agent.md` exists and is selectable.
5. `.github/skills/sqlite-project-memory/SKILL.md` exists and can be invoked as `/sqlite-project-memory`.
6. Your project instructions file contains the SQLite Project Memory snippet.
7. First prompt in session calls `get_project_context` and then `get_recent_activity` or `query_view`.

If tools still do not appear after all file-based gates pass, reload the VS Code window and re-open Agent mode.

---

## Uninstall

Two scripts are provided. Run from inside the repository (or the target project root if you installed into one).

```powershell
# Windows
.\sqlite-mcp\uninstall.ps1
```

```bash
# Linux / macOS
bash sqlite-mcp/uninstall.sh
```

### Default behaviour (safe)

- Exports all project memory to markdown views + a JSON snapshot under `Project Memory/pm_exports/uninstall-backup-<timestamp>/` **before any deletion**.
- Removes the `sqlite-project-memory` entry from `.vscode/mcp.json`.
- Removes the deployed agent and skill files from `.github/`.
- Removes the `.install-complete` marker.
- Prompts `[y/N]` before each destructive step unless `--force` / `-Force` is supplied.
- Does **not** delete the virtual environment, database, or exports by default.

### Optional flags

| Flag (PowerShell / Bash) | Effect |
|---|---|
| `-RemoveRuntime` / `--remove-runtime` | Also delete `Project Memory/.venv` |
| `-RemoveData` / `--remove-data` | Also delete `pm_data` and `pm_exports` (the pre-uninstall backup too) |
| `-RemoveCustomizations` / `--remove-customizations` | Also remove `.github/agents/project-memory.agent.md` and `.github/skills/sqlite-project-memory/` |
| `-RemoveAll` / `--remove-all` | All three flags above plus remove the empty `Project Memory/` folder |
| `-Force` / `--force` | Skip all `[y/N]` prompts (for automation) |
| `-LogFile <path>` / `--log-file <path>` | Save full transcript to a file |

### Manual cleanup

If you added the SQLite Project Memory instructions snippet to your own instructions file (`copilot-instructions.md`, `AGENTS.md`, `CLAUDE.md`, etc.), remove that section manually — the uninstall scripts do not modify user-owned instruction files.
