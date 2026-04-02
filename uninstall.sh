#!/usr/bin/env bash
set -eo pipefail

# uninstall.sh
# SQLite MCP uninstaller for Linux/macOS.
#
# Usage:
#   ./sqlite-mcp/uninstall.sh                          # remove MCP config entry + AI customizations only (safe default)
#   ./sqlite-mcp/uninstall.sh --remove-runtime         # also remove Project Memory/.venv
#   ./sqlite-mcp/uninstall.sh --remove-data            # also remove Project Memory/pm_data + pm_exports (data loss — export runs first)
#   ./sqlite-mcp/uninstall.sh --remove-customizations  # also remove .github/agents + .github/skills entries
#   ./sqlite-mcp/uninstall.sh --remove-all             # all of the above + remove empty Project Memory folder
#   ./sqlite-mcp/uninstall.sh --force                  # skip confirmation prompts
#   ./sqlite-mcp/uninstall.sh --log-file uninstall.log # save a full transcript for debugging
#
# All destructive operations require interactive confirmation [y/N] unless --force is supplied.
# Data is exported to markdown and JSON before any deletion.

# Date modified: 2026-04-02

LOG_FILE=""
REMOVE_RUNTIME=false
REMOVE_DATA=false
REMOVE_CUSTOMIZATIONS=false
REMOVE_ALL=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remove-runtime)        REMOVE_RUNTIME=true; shift ;;
    --remove-data)           REMOVE_DATA=true; shift ;;
    --remove-customizations) REMOVE_CUSTOMIZATIONS=true; shift ;;
    --remove-all)            REMOVE_ALL=true; shift ;;
    --force)                 FORCE=true; shift ;;
    --log-file)              LOG_FILE="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [ -n "$LOG_FILE" ]; then
  echo "Logging to $LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
fi

if [ "$REMOVE_ALL" = true ]; then
  REMOVE_RUNTIME=true
  REMOVE_DATA=true
  REMOVE_CUSTOMIZATIONS=true
fi

echo "=== SQLite MCP uninstall script started ==="

# Locate project root the same way the installer does.
script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$(basename "$script_root")" = "sqlite-mcp" ]; then
  repo_root="$(dirname "$script_root")"
else
  repo_root="$script_root"
fi

echo "Using project root: $repo_root"
cd "$repo_root"

project_memory="$repo_root/Project Memory"
mcp_config_path="$repo_root/.vscode/mcp.json"
db_path="$project_memory/pm_data/project_memory.db"
export_dir="$project_memory/pm_exports"
agent_file="$repo_root/.github/agents/project-memory.agent.md"
skill_dir="$repo_root/.github/skills/sqlite-project-memory"
venv_path="$project_memory/.venv"
venv_python="$venv_path/bin/python"
install_marker="$project_memory/.install-complete"

confirm_action() {
  local message="$1"
  if [ "$FORCE" = true ]; then return 0; fi
  echo ""
  echo "$message"
  read -rp "Proceed? [y/N] " answer
  case "$answer" in
    [yY][eE][sS]|[yY]) return 0 ;;
    *) return 1 ;;
  esac
}

# ── Step 1: Export data before anything is removed ────────────────────────────
if [ -f "$db_path" ]; then
  if ! confirm_action "Export all project memory to markdown and JSON before uninstalling?"; then
    echo "Uninstall aborted — data not exported, nothing deleted."
    exit 0
  fi

  export_timestamp="$(date +%Y%m%d-%H%M%S)"
  export_target="$export_dir/uninstall-backup-$export_timestamp"
  mkdir -p "$export_target"
  echo "Exporting data to: $export_target"

  if [ -x "$venv_python" ]; then
    "$venv_python" -m sqlite_project_memory_admin --db-path "$db_path" \
      export-views \
      --output-dir "$export_target" \
      --force \
      --user-requested \
      --request-reason "Pre-uninstall data export" \
      && echo "Markdown views exported." \
      || echo "Warning: markdown export failed (non-fatal)."

    json_backup="$export_target/project_memory.snapshot.json"
    "$venv_python" -m sqlite_project_memory_admin --db-path "$db_path" \
      export-json \
      --output-path "$json_backup" \
      && echo "JSON snapshot exported: $json_backup" \
      || echo "Warning: JSON export failed (non-fatal)."
  else
    echo "Warning: virtual environment not found at $venv_python; skipping data export."
    echo "Your database file is still at: $db_path"
    if ! confirm_action "Continue uninstall without data export?"; then
      echo "Uninstall aborted."
      exit 0
    fi
  fi
else
  echo "No database found at $db_path — skipping data export."
fi

# ── Step 2: Remove sqlite-project-memory entry from .vscode/mcp.json ──────────
if [ -f "$mcp_config_path" ]; then
  if confirm_action "Remove sqlite-project-memory entry from .vscode/mcp.json?"; then
    python3 - <<PY
import json, pathlib, sys
config_path = pathlib.Path(r"$mcp_config_path")
try:
    data = json.loads(config_path.read_text(encoding='utf-8'))
    servers = data.get("servers", {})
    if isinstance(servers, dict) and "sqlite-project-memory" in servers:
        del servers["sqlite-project-memory"]
        data["servers"] = servers
        config_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        print("Removed sqlite-project-memory from", config_path)
    else:
        print("sqlite-project-memory not found in servers — nothing to remove.")
except Exception as e:
    print("Warning: could not update mcp.json:", e, file=sys.stderr)
PY
  fi
else
  echo "No .vscode/mcp.json found — skipping."
fi

# ── Step 3: Remove AI customization files ─────────────────────────────────────
if [ "$REMOVE_CUSTOMIZATIONS" = true ]; then
  if confirm_action "Remove project-memory agent and skill files from .github/?"; then
    if [ -f "$agent_file" ]; then
      rm -f "$agent_file"
      echo "Removed: $agent_file"
    fi
    if [ -d "$skill_dir" ]; then
      rm -rf "$skill_dir"
      echo "Removed: $skill_dir"
    fi
    # Clean up empty parent dirs
    for dir in "$repo_root/.github/agents" "$repo_root/.github/skills"; do
      if [ -d "$dir" ] && [ -z "$(ls -A "$dir")" ]; then
        rmdir "$dir"
        echo "Removed empty directory: $dir"
      fi
    done
  fi
fi

# ── Step 4: Remove .venv (runtime) ────────────────────────────────────────────
if [ "$REMOVE_RUNTIME" = true ]; then
  if [ -d "$venv_path" ]; then
    if confirm_action "Remove virtual environment at '$venv_path'?"; then
      rm -rf "$venv_path"
      echo "Removed: $venv_path"
    fi
  else
    echo "No .venv found at $venv_path — skipping."
  fi
fi

# ── Step 5: Remove data (pm_data + pm_exports, including the backup) ──────────
if [ "$REMOVE_DATA" = true ]; then
  pm_data="$project_memory/pm_data"
  pm_exports="$project_memory/pm_exports"
  if confirm_action "Remove database and exports at '$pm_data' and '$pm_exports'? Your pre-uninstall backup will also be deleted."; then
    for target in "$pm_data" "$pm_exports"; do
      if [ -e "$target" ]; then
        rm -rf "$target"
        echo "Removed: $target"
      fi
    done
  fi
fi

# ── Step 6: Remove install marker ─────────────────────────────────────────────
if [ -f "$install_marker" ]; then
  rm -f "$install_marker"
  echo "Removed install marker: $install_marker"
fi

# ── Step 7: Remove empty Project Memory folder (only if --remove-all) ─────────
if [ "$REMOVE_ALL" = true ]; then
  if [ -d "$project_memory" ] && [ -z "$(ls -A "$project_memory")" ]; then
    if confirm_action "Remove now-empty 'Project Memory' folder?"; then
      rmdir "$project_memory"
      echo "Removed: $project_memory"
    fi
  fi
fi

# ── Final report ──────────────────────────────────────────────────────────────
echo ""
echo "=== Uninstall Report ==="

if [ ! -f "$mcp_config_path" ] || ! grep -q '"sqlite-project-memory"' "$mcp_config_path" 2>/dev/null; then
  echo "[PASS] sqlite-project-memory removed from .vscode/mcp.json"
else
  echo "[PENDING] sqlite-project-memory still present in .vscode/mcp.json"
fi

if [ ! -f "$agent_file" ]; then
  echo "[PASS] AI agent file removed"
else
  echo "[SKIPPED] AI agent file still present"
fi

if [ ! -d "$skill_dir" ]; then
  echo "[PASS] AI skill directory removed"
else
  echo "[SKIPPED] AI skill directory still present"
fi

if [ ! -d "$venv_path" ]; then
  echo "[PASS] Virtual environment removed"
else
  echo "[SKIPPED] Virtual environment still present"
fi

if [ ! -f "$db_path" ]; then
  echo "[PASS] Database removed"
else
  echo "[SKIPPED] Database still present (data preserved)"
fi

echo ""
echo "Note: if you manually added the SQLite Project Memory snippet to an instructions file"
echo "(copilot-instructions.md, AGENTS.md, CLAUDE.md, etc.), remove that section manually."
echo ""
echo "=== Uninstall complete ==="
