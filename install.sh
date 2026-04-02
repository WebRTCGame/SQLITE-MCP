#!/usr/bin/env bash
set -eo pipefail

# install.sh
# SQLite MCP installer for Linux/macOS.
#
# Usage:
#   ./install.sh                        # fresh install or update
#   ./install.sh --log-file install.log # with transcript logging
#   ./install.sh --append-instructions   # append snippet to suggested instructions file

LOG_FILE=""
APPEND_INSTRUCTIONS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --log-file) LOG_FILE="$2"; shift 2 ;;
    --append-instructions) APPEND_INSTRUCTIONS=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [ -n "$LOG_FILE" ]; then
  echo "Logging to $LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
fi

echo "=== SQLite MCP install script started ==="

# The install script lives inside the sqlite-mcp checkout.
# If the directory is named 'sqlite-mcp', the user's project root is its parent.
script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$(basename "$script_root")" = "sqlite-mcp" ]; then
  repo_root="$(dirname "$script_root")"
else
  repo_root="$script_root"
fi

echo "Using project root: $repo_root"
cd "$repo_root"

project_memory="$repo_root/Project Memory"
installation_marker="$project_memory/.install-complete"
mkdir -p "$project_memory"

# Track whether this is a nested install (sqlite-mcp repo lives inside the user's project).
if [ "$script_root" != "$repo_root" ]; then
  is_nested_install=true
else
  is_nested_install=false
fi

flatten_nested_checkout() {
  local s_root="$1"
  local r_root="$2"
  local pm="$3"

  if [ "$s_root" = "$r_root" ]; then return; fi

  if [ ! -f "$s_root/pyproject.toml" ]; then
    echo "No nested checkout pyproject.toml at $s_root; skipping flattening."
    return
  fi

  echo "Moving repository source from $s_root into Project Memory: $pm"

  shopt -s dotglob nullglob
  for item in "$s_root"/*; do
    if [ "$item" = "$pm" ]; then continue; fi
    if [ "$item" = "${BASH_SOURCE[0]}" ]; then
      echo "Skipping running install script in move: $item"
      continue
    fi
    dest="$pm/$(basename "$item")"
    if [ -e "$dest" ]; then
      echo "Destination already exists, not overwriting: $dest"
      continue
    fi
    mv "$item" "$dest" || echo "Warning: failed to move $item -> $dest"
  done
  shopt -u dotglob nullglob

  if [ -z "$(ls -A "$s_root")" ]; then
    rmdir "$s_root" || true
  fi
}

# Move repo contents into Project Memory so nothing from sqlite-mcp pollutes the user's project root.
if [ "$is_nested_install" = true ]; then
  flatten_nested_checkout "$script_root" "$repo_root" "$project_memory"
fi

# Resolve source root: developer scenario (repo_root IS the repo), PM folder (nested install), fallback.
if [ -f "$repo_root/pyproject.toml" ]; then
  source_root="$repo_root"
elif [ -f "$project_memory/pyproject.toml" ]; then
  source_root="$project_memory"
  echo "Using Project Memory folder as source root: $source_root"
else
  echo "WARNING: pyproject.toml not found. Proceeding with repo_root as source root."
  source_root="$repo_root"
fi

# Auto-migrate legacy artifact locations (no-op if already in PM or source doesn't exist).
for mapping in ".venv:.venv" "data:pm_data" "exports:pm_exports"; do
  src_name="${mapping%%:*}"
  dst_name="${mapping##*:}"
  src="$repo_root/$src_name"
  dst="$project_memory/$dst_name"
  if [ -e "$src" ] && [ ! -e "$dst" ]; then
    echo "Migrating $src_name from $src to $dst"
    mv "$src" "$dst"
  fi
done

python_exec="$(command -v python3 || command -v python)"
if [ -z "$python_exec" ]; then
  echo "Python not found. Install Python 3 and retry."
  exit 1
fi

if [ ! -d "$project_memory/.venv" ]; then
  echo "Creating Python virtual environment in $project_memory/.venv..."
  if ! timeout 300 "$python_exec" -m venv "$project_memory/.venv"; then
    echo "Warning: venv creation failed or timed out; retrying with --without-pip fallback."
    "$python_exec" -m venv --without-pip "$project_memory/.venv"
    "$project_memory/.venv/bin/python" -m ensurepip --default-pip
    "$project_memory/.venv/bin/python" -m pip install --upgrade pip
  fi
else
  echo ".venv already exists, skipping creation."
fi

source "$project_memory/.venv/bin/activate"

echo "Installing package from $source_root..."
pip install --upgrade pip
pip install -e "$source_root"

db_path="$project_memory/pm_data/project_memory.db"
export_dir="$project_memory/pm_exports"
mkdir -p "$project_memory/pm_data"
mkdir -p "$export_dir"

export SQLITE_MCP_DB_PATH="$db_path"
export SQLITE_MCP_EXPORT_DIR="$export_dir"

echo "Bootstrapping project memory..."
sqlite-project-memory-admin --db-path "$db_path" bootstrap-self --repo-root "$repo_root"

if ! command -v sqlite-project-memory-admin >/dev/null 2>&1; then
  echo "sqlite-project-memory-admin not found after install."
  exit 1
fi

echo "Running health checks..."
sqlite-project-memory-admin --db-path "$db_path" project-state
sqlite-project-memory-admin --db-path "$db_path" health

# Write .vscode/mcp.json (always project-local)
mkdir -p "$repo_root/.vscode"
mcp_config_path="$repo_root/.vscode/mcp.json"
echo "Writing MCP config: $mcp_config_path"

python - <<PY
import json, pathlib
config_path = pathlib.Path(r"$mcp_config_path")
server_entry = {
    "type": "stdio",
    "command": "$project_memory/.venv/bin/python",
    "args": ["-m", "sqlite_mcp_server"],
    "env": {
        "SQLITE_MCP_TRANSPORT": "stdio",
        "SQLITE_MCP_DB_PATH": "$db_path",
        "SQLITE_MCP_EXPORT_DIR": "$export_dir"
    }
}
data = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
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

echo "Updated MCP config at $mcp_config_path"

# Deploy copilot customizations (.github/copilot-instructions.md, skill, agent) to the target project.
# Source files live under assets/ inside the sqlite-mcp repo (or Project Memory for nested installs).
assets_dir="$source_root/assets"
if [ -d "$assets_dir" ]; then
    github_dir="$repo_root/.github"

    # --- Skill ---------------------------------------------------------------
    skill_src="$assets_dir/skills/sqlite-project-memory/SKILL.md"
    skill_dst_dir="$github_dir/skills/sqlite-project-memory"
    if [ -f "$skill_src" ]; then
        mkdir -p "$skill_dst_dir"
        cp -f "$skill_src" "$skill_dst_dir/SKILL.md"
        echo "Deployed skill: $skill_dst_dir/SKILL.md"
    fi

    # --- Agent ---------------------------------------------------------------
    agent_src="$assets_dir/agents/project-memory.agent.md"
    agent_dst_dir="$github_dir/agents"
    if [ -f "$agent_src" ]; then
        mkdir -p "$agent_dst_dir"
        cp -f "$agent_src" "$agent_dst_dir/project-memory.agent.md"
        echo "Deployed agent: $agent_dst_dir/project-memory.agent.md"
    fi

    # --- copilot-instructions snippet (print notice — user must add manually) ---
    snippet_src="$assets_dir/copilot-instructions-snippet.md"
    if [ -f "$snippet_src" ]; then
      snippet_copied=false
      instructions_target=""
      for candidate in "$repo_root/.github/copilot-instructions.md" "$repo_root/AGENTS.md" "$repo_root/CLAUDE.md"; do
        if [ -f "$candidate" ]; then
          instructions_target="$candidate"
          break
        fi
      done
      if [ -z "$instructions_target" ]; then
        instructions_target="$repo_root/.github/copilot-instructions.md"
      fi

      if [ "$APPEND_INSTRUCTIONS" = true ]; then
        mkdir -p "$(dirname "$instructions_target")"
        [ -f "$instructions_target" ] || touch "$instructions_target"
        if ! grep -q "sqlite-project-memory" "$instructions_target"; then
          printf '\n---\n' >> "$instructions_target"
          cat "$snippet_src" >> "$instructions_target"
          echo "Appended SQLite Project Memory snippet to: $instructions_target"
        else
          echo "Instructions target already contains sqlite-project-memory section: $instructions_target"
        fi
      fi

      if command -v pbcopy >/dev/null 2>&1; then
        cat "$snippet_src" | pbcopy
        snippet_copied=true
      elif command -v wl-copy >/dev/null 2>&1; then
        cat "$snippet_src" | wl-copy
        snippet_copied=true
      elif command -v xclip >/dev/null 2>&1; then
        xclip -selection clipboard < "$snippet_src"
        snippet_copied=true
      elif command -v xsel >/dev/null 2>&1; then
        xsel --clipboard --input < "$snippet_src"
        snippet_copied=true
      fi

        echo ""
        echo "=== ACTION REQUIRED: Add AI instructions ==="
        echo "Append the snippet below to your AI instructions file"
        echo "(.github/copilot-instructions.md, AGENTS.md, CLAUDE.md, etc.)."
      echo "Suggested target: $instructions_target"
        echo "A copy is saved at: $snippet_src"
      if [ "$snippet_copied" = true ]; then
        echo "Snippet copied to clipboard."
      else
        echo "Clipboard copy unavailable; copy from the snippet below."
      fi
        echo "--- snippet start ---"
        cat "$snippet_src"
        echo "--- snippet end ---"

      if command -v code >/dev/null 2>&1; then
        mkdir -p "$(dirname "$instructions_target")"
        [ -f "$instructions_target" ] || touch "$instructions_target"
        code "$instructions_target" >/dev/null 2>&1 || true
        echo "Opened in VS Code: $instructions_target"
      fi
        echo ""
    fi
else
    echo "Assets directory not found at $assets_dir; skipping copilot customization deployment."
fi

# Optional post-install hook
post_install_hook="$repo_root/.scripts/post_install.sh"
if [ -f "$post_install_hook" ]; then
  echo "Running post-install hook: $post_install_hook"
  bash "$post_install_hook" || echo "Post-install hook failed"
fi

# Install marker
if [ ! -f "$installation_marker" ]; then
  touch "$installation_marker"
  echo "Created install marker: $installation_marker"
else
  echo "Install marker already present (update complete): $installation_marker"
fi

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

echo "=== Install complete ==="
echo "Project Memory: $project_memory"
echo "MCP config:     $mcp_config_path"

agent_path="$repo_root/.github/agents/project-memory.agent.md"
skill_path="$repo_root/.github/skills/sqlite-project-memory/SKILL.md"
instructions_found=false
for candidate in "$repo_root/.github/copilot-instructions.md" "$repo_root/AGENTS.md" "$repo_root/CLAUDE.md"; do
  if [ -f "$candidate" ] && grep -q "sqlite-project-memory" "$candidate"; then
    instructions_found=true
    break
  fi
done

echo ""
echo "=== Usage Gates Report ==="
if grep -q '"sqlite-project-memory"' "$mcp_config_path" 2>/dev/null; then
  echo "[PASS] .vscode/mcp.json has sqlite-project-memory entry: true"
else
  echo "[ACTION REQUIRED] .vscode/mcp.json has sqlite-project-memory entry: false"
fi
if [ -f "$agent_path" ]; then
  echo "[PASS] Project Memory agent file exists: true"
else
  echo "[ACTION REQUIRED] Project Memory agent file exists: false"
fi
if [ -f "$skill_path" ]; then
  echo "[PASS] sqlite-project-memory skill file exists: true"
else
  echo "[ACTION REQUIRED] sqlite-project-memory skill file exists: false"
fi
if [ "$instructions_found" = true ]; then
  echo "[PASS] Instructions snippet found in project instructions file"
else
  echo "[ACTION REQUIRED] Instructions snippet found in project instructions file"
fi
echo "[ACTION REQUIRED] Approve/trust MCP server in VS Code if prompted."
echo "[ACTION REQUIRED] Reload VS Code window after install if tools do not appear."
echo "[ACTION REQUIRED] Use Agent mode and choose Project Memory agent (or /sqlite-project-memory)."
if [ "$instructions_found" != true ]; then
  echo "Next: paste the SQLite Project Memory snippet into your project instructions file."
fi

