#!/usr/bin/env bash
set -eo pipefail

# install.sh
# Cross-platform install script for SQLite MCP (Linux/macOS with bash/zsh)
# Usage: ./install.sh [--migrate-existing] [--use-global-config] [--mcp-config-path PATH] [--fetch-only] [--branch BRANCH] [--ci]

MIGRATE_EXISTING=false
USE_GLOBAL_CONFIG=false
MCP_CONFIG_PATH=""
FETCH_ONLY=false
BRANCH=""
CI=false
LOG_FILE=""
PROJECT_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --migrate-existing) MIGRATE_EXISTING=true; shift ;; 
    --use-global-config) USE_GLOBAL_CONFIG=true; shift ;; 
    --mcp-config-path) MCP_CONFIG_PATH="$2"; shift 2 ;; 
    --fetch-only) FETCH_ONLY=true; shift ;; 
    --branch) BRANCH="$2"; shift 2 ;; 
    --ci) CI=true; shift ;; 
    --log-file) LOG_FILE="$2"; shift 2 ;; 
    --project-root) PROJECT_ROOT="$2"; shift 2 ;; 
    *) echo "Unknown option: $1"; exit 1 ;; 
  esac
done

if [ -n "$PROJECT_ROOT" ]; then
  repo_root="$PROJECT_ROOT"
else
  repo_root="$(pwd)"
fi
project_memory="$repo_root/Project Memory"
installation_marker="$project_memory/.install-complete"

printf 'Using project root: %s\n' "$repo_root"

if [ "$LOG_FILE" ]; then
  echo "Logging to $LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
fi

if [ -f "$installation_marker" ]; then
  echo "Install marker already exists. Running in idempotent mode."
fi

if [ ! -f "$repo_root/pyproject.toml" ]; then
  echo "pyproject.toml not found; run from repository root"
  exit 1
fi

mkdir -p "$project_memory"

map_migration() {
  local src="$1" dst="$2" label="$3"
  if [ -d "$src" ] && [ ! -d "$dst" ]; then
    if [ "$MIGRATE_EXISTING" = true ]; then
      echo "Migrating $label from $src to $dst"
      mv "$src" "$dst"
    else
      echo "Found existing '$label' at $src; rerun with --migrate-existing to move into Project Memory"
    fi
  fi
}

map_migration "$repo_root/.venv" "$project_memory/.venv" ".venv"
map_migration "$repo_root/data" "$project_memory/pm_data" "data"
map_migration "$repo_root/exports" "$project_memory/pm_exports" "exports"

if [ ! -d "$repo_root/.git" ]; then
  echo "Initializing git repository..."
  git init
else
  echo "Git repo already initialized." 
fi

NON_INTERACTIVE=false
if [ "$CI" = true ]; then
  NON_INTERACTIVE=true
fi

if [ -n "$BRANCH" ]; then
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
  else
    git fetch origin "$BRANCH" --depth=1 || true
    git checkout -b "$BRANCH" "origin/$BRANCH" 2>/dev/null || git checkout -b "$BRANCH"
  fi
fi

if [ "$FETCH_ONLY" = true ]; then
  git fetch origin --depth=1
  echo "Fetch-only mode, exiting.";
  exit 0
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "Pulling latest from origin/$BRANCH..."
  git fetch origin --depth=1
  branch_to_pull="${BRANCH:-main}"
  git pull --ff-only origin "$branch_to_pull" || echo "Could not fast-forward; resolve manually."
else
  echo "No origin remote configured; skipping fetch/pull."
fi

python_exec="$(command -v python3 || command -v python)"
if [ -z "$python_exec" ]; then
  echo "Python not found. Install Python 3 and retry."
  exit 1
fi

if [ ! -d "$project_memory/.venv" ]; then
  "$python_exec" -m venv "$project_memory/.venv"
fi

source "$project_memory/.venv/bin/activate"

pip install --upgrade pip
pip install -e "$repo_root"

sqlite-project-memory-admin bootstrap-self --repo-root "$repo_root"

if ! command -v sqlite-project-memory-admin >/dev/null 2>&1; then
  echo "sqlite-project-memory-admin command not found after install."
  exit 1
fi

sqlite-project-memory-admin project-state
sqlite-project-memory-admin health

get_mcp_config_path() {
  if [ -n "$MCP_CONFIG_PATH" ]; then
    echo "$MCP_CONFIG_PATH"
    return
  fi

  if [ "$USE_GLOBAL_CONFIG" = true ]; then
    if [ -d "$HOME/.config/Code - Insiders/User" ]; then
      echo "$HOME/.config/Code - Insiders/User/mcp.json"
      return
    fi
    echo "$HOME/.config/Code/User/mcp.json"
    return
  fi

  mkdir -p "$repo_root/.vscode"
  echo "$repo_root/.vscode/mcp.json"
}

mcp_config_path="$(get_mcp_config_path)"

python - <<PY
import json, pathlib
config_path = pathlib.Path(r"$mcp_config_path")
server_entry = {
    "type": "stdio",
    "command": f"{project_memory}/.venv/bin/python",
    "args": ["-m", "sqlite_mcp_server"],
    "env": {
        "SQLITE_MCP_TRANSPORT": "stdio",
        "SQLITE_MCP_DB_PATH": f"{project_memory}/pm_data/project_memory.db",
        "SQLITE_MCP_EXPORT_DIR": f"{project_memory}/pm_exports"
    }
}
if config_path.exists():
    data = json.loads(config_path.read_text(encoding='utf-8'))
else:
    data = {}
if not isinstance(data, dict):
    data = {}
servers = data.get("servers")
if not isinstance(servers, dict):
    servers = {}
servers["sqlite-project-memory"] = server_entry

data["servers"] = servers
if "inputs" not in data or not isinstance(data["inputs"], list):
    data["inputs"] = []
config_path.parent.mkdir(parents=True, exist_ok=True)
config_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
PY

echo "Wrote MCP config: $mcp_config_path"

# Post-install hook support
post_install_hook="$repo_root/.scripts/post_install.sh"
if [ -f "$post_install_hook" ]; then
  echo "Running post-install hook: $post_install_hook"
  bash "$post_install_hook" --ci=${CI} --non-interactive=${NON_INTERACTIVE:-false} || echo "Post-install hook failed"
fi

# Install marker for idempotence
if [ ! -f "$installation_marker" ]; then
  touch "$installation_marker"
  echo "Created install marker: $installation_marker"
fi

# Cleanup: if running from a nested sqlite-mcp folder, move it into Project Memory
script_root="$(dirname "$(readlink -f "$0")")"
if [ "$repo_root" != "$script_root" ] && [ -d "$project_memory" ]; then
  repo_folder_name="$(basename "$script_root")"
  destination="$project_memory/$repo_folder_name"
  if [ ! -d "$destination" ]; then
    echo "Moving installer folder $script_root into $destination"
    mv "$script_root" "$destination"
    echo "Moved installer folder into Project Memory."
  else
    echo "Destination $destination already exists; skipping move."
  fi
fi

echo "Install complete. Run: ${project_memory}/.venv/bin/python -m sqlite_mcp_server"
