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
    --project-memory-root) PROJECT_MEMORY_ROOT="$2"; shift 2 ;; 
    *) echo "Unknown option: $1"; exit 1 ;; 
  esac
done

script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "$PROJECT_ROOT" ]; then
  repo_root="$PROJECT_ROOT"
else
  repo_root="$(pwd)"
fi

if [ -n "$PROJECT_MEMORY_ROOT" ]; then
  if [[ "$PROJECT_MEMORY_ROOT" = /* || "$PROJECT_MEMORY_ROOT" = ~* ]]; then
    project_memory="$PROJECT_MEMORY_ROOT"
  else
    project_memory="$repo_root/$PROJECT_MEMORY_ROOT"
  fi
elif [ -n "$SQLITE_MCP_PROJECT_MEMORY_ROOT" ]; then
  project_memory="$SQLITE_MCP_PROJECT_MEMORY_ROOT"
else
  project_memory="$repo_root/Project Memory"
fi
installation_marker="$project_memory/.install-complete"

flatten_nested_checkout() {
  local script_root="$1"
  local repo_root="$2"
  local project_memory="$3"

  if [ "$script_root" = "$repo_root" ]; then
    return
  fi

  if [ ! -f "$script_root/pyproject.toml" ]; then
    echo "No nested checkout pyproject.toml at $script_root; skipping flattening."
    return
  fi

  echo "Moving repository source from $script_root into Project Memory: $project_memory"

  shopt -s dotglob nullglob
  for item in "$script_root"/*; do
    # Skip project memory folder itself
    if [ "$item" = "$project_memory" ]; then
      continue
    fi

    # Skip installer script being executed
    if [ "$item" = "${BASH_SOURCE[0]}" ]; then
      echo "Skipping running install script file in move: $item"
      continue
    fi

    dest="$project_memory/$(basename "$item")"
    if [ -e "$dest" ]; then
      echo "Destination already exists, not overwriting: $dest"
      continue
    fi

    mv "$item" "$dest" || echo "Warning: failed to move $item -> $dest"
  done
  shopt -u dotglob nullglob

  # Remove empty nested directory if now empty
  if [ -z "$(ls -A "$script_root")" ]; then
    rmdir "$script_root" || true
  fi
}

printf 'Using project root: %s\n' "$repo_root"

if [ "$LOG_FILE" ]; then
  echo "Logging to $LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
fi

if [ -f "$installation_marker" ]; then
  echo "Install marker already exists. Running in idempotent mode."
fi

if [ ! -f "$repo_root/pyproject.toml" ]; then
  echo "WARNING: pyproject.toml not found in $repo_root. Proceeding anyway (assumed external host project)."
fi

mkdir -p "$project_memory"

# Track whether this is a nested install (sqlite-mcp repo lives inside the user's project).
if [ "$script_root" != "$repo_root" ]; then
  is_nested_install=true
else
  is_nested_install=false
fi

# Move repo contents into Project Memory so nothing from sqlite-mcp pollutes the user's project root.
flatten_nested_checkout "$script_root" "$repo_root" "$project_memory"

# Resolve source root: developer scenario (repo_root IS the repo), PM folder (nested install), fallback.
if [ -f "$repo_root/pyproject.toml" ]; then
  source_root="$repo_root"
elif [ -f "$project_memory/pyproject.toml" ]; then
  source_root="$project_memory"
  echo "Using Project Memory folder as source root for pip install: $source_root"
elif [ -f "$script_root/pyproject.toml" ]; then
  source_root="$script_root"
  echo "Using script location as source root for pip install: $source_root"
else
  echo "WARNING: pyproject.toml not found. Proceeding with repo_root as source root."
  source_root="$repo_root"
fi

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
  if ! timeout 300 "$python_exec" -m venv "$project_memory/.venv"; then
    echo "Warning: venv creation failed or timed out; retrying with --without-pip fallback."
    "$python_exec" -m venv --without-pip "$project_memory/.venv"
    "$project_memory/.venv/bin/python" -m ensurepip --default-pip
    "$project_memory/.venv/bin/python" -m pip install --upgrade pip
  fi
fi

source "$project_memory/.venv/bin/activate"

pip install --upgrade pip
pip install -e "$source_root"

export SQLITE_MCP_DB_PATH="$project_memory/pm_data/project_memory.db"
export SQLITE_MCP_EXPORT_DIR="$project_memory/pm_exports"

sqlite-project-memory-admin --db-path "$SQLITE_MCP_DB_PATH" bootstrap-self --repo-root "$repo_root"

if ! command -v sqlite-project-memory-admin >/dev/null 2>&1; then
  echo "sqlite-project-memory-admin command not found after install."
  exit 1
fi

sqlite-project-memory-admin --db-path "$SQLITE_MCP_DB_PATH" project-state
sqlite-project-memory-admin --db-path "$SQLITE_MCP_DB_PATH" health

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

ensure_project_memory_layout() {
  local root="$repo_root"
  local pm="$project_memory"

  mkdir -p "$pm"
  for item in .venv data exports; do
    local src="$root/$item"
    local dst=""
    case "$item" in
      .venv) dst="$pm/.venv" ;;
      data) dst="$pm/pm_data" ;;
      exports) dst="$pm/pm_exports" ;;
    esac
    if [ -e "$src" ] && [ ! -e "$dst" ]; then
      echo "Moving existing $item from $src to $dst"
      mkdir -p "$(dirname "$dst")"
      mv "$src" "$dst"
    fi
  done

  mkdir -p "$pm/pm_data"
  mkdir -p "$pm/pm_exports"
  if [ ! -f "$pm/.install-complete" ]; then
    touch "$pm/.install-complete"
    echo "Created missing install marker for coherence: $pm/.install-complete"
  fi

  echo "Project Memory layout verification complete."
}

ensure_project_memory_layout

# For nested installs: remove any sqlite-mcp source files that leaked into project root.
# (All source should have moved into Project Memory; this is a safety net only.)
if [ "$is_nested_install" = true ]; then
  for artifact in src tests pyproject.toml README.md INSTALL.md 'API SUMMARY.md' Chart.mmd install.ps1 .gitignore tmp_views tmp_smoke_test.py tmp.db tmp.db-shm tmp.db-wal; do
    path="$repo_root/$artifact"
    if [ -e "$path" ]; then
      echo "Removing leaked source artifact from project root: $path"
      rm -rf "$path" || echo "Warning: failed to remove $path"
    fi
  done
  echo "Nested install complete. Project Memory contains all sqlite-mcp source and runtime files."
fi

# Cleanup: nested checkout is handled by flatten_nested_checkout earlier.
if [ "$repo_root" != "$script_root" ]; then
  echo "Cleanup: source moved from $script_root into Project Memory: $project_memory"
fi

echo "Install complete. Run: ${project_memory}/.venv/bin/python -m sqlite_mcp_server"
