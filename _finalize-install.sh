#!/usr/bin/env bash
# _finalize-install.sh
#
# Post-install file reorganization for nested SQLite MCP installs.
#
# Moves the sqlite-mcp source tree (including install.sh, install.ps1, and this
# script itself) into Project Memory, then removes the now-empty source folder.
#
# Called automatically by install.sh as a detached background process.
# Do not run this script directly unless you know what you are doing.
#
# Args: <script_root> <project_root> <project_memory>
#
# Date modified: 2026-04-02

set -eo pipefail

SCRIPT_ROOT="$1"
PROJECT_ROOT="$2"
PROJECT_MEMORY="$3"

echo "=== SQLite MCP post-install finalize started ==="
echo "Source:      $SCRIPT_ROOT"
echo "Destination: $PROJECT_MEMORY"

# Wait for install.sh to fully exit and release any file locks.
sleep 3

moved=0
skipped=0
errors=0

# Move every item from SCRIPT_ROOT (sqlite-mcp/) to PROJECT_MEMORY (Project Memory/).
shopt -s dotglob nullglob
for item in "$SCRIPT_ROOT"/*; do

    # Skip Project Memory folder itself.
    [ "$item" = "$PROJECT_MEMORY" ] && continue

    # Skip self — bash does not lock running script files, but handle it last for clarity.
    [ "$item" = "${BASH_SOURCE[0]}" ] && continue

    name="$(basename "$item")"
    dst="$PROJECT_MEMORY/$name"

    if [ -e "$dst" ]; then
        echo "Destination exists, skipping: $name"
        skipped=$((skipped + 1))
        continue
    fi

    if mv "$item" "$dst"; then
        echo "Moved: $name"
        moved=$((moved + 1))
    else
        echo "Warning: failed to move $item"
        errors=$((errors + 1))
    fi
done
shopt -u dotglob nullglob

# Clean up any source-repo artifacts that leaked directly into PROJECT_ROOT.
leaked=(src tests pyproject.toml README.md INSTALL.md "API SUMMARY.md" Chart.mmd .gitignore \
        tmp_views tmp_smoke_test.py tmp.db tmp.db-shm tmp.db-wal)
for artifact in "${leaked[@]}"; do
    path="$PROJECT_ROOT/$artifact"
    if [ -e "$path" ]; then
        rm -rf "$path" && echo "Removed leaked artifact: $artifact" \
            || echo "Warning: could not remove $path"
    fi
done

echo "Finalize: moved=$moved  skipped=$skipped  errors=$errors"

# ── Self-move ────────────────────────────────────────────────────────────────
# On Linux/macOS bash does not hold a file lock on the running script, so
# moving (or deleting) the script file from its original path is safe.
self_src="${BASH_SOURCE[0]}"
self_name="$(basename "$self_src")"
self_dst="$PROJECT_MEMORY/$self_name"

if [ ! -e "$self_dst" ]; then
    mv "$self_src" "$self_dst" && echo "Moved self: $self_name" \
        || echo "Warning: could not move self ($self_src)"
fi

# Remove ScriptRoot if now empty.
if [ -d "$SCRIPT_ROOT" ] && [ -z "$(ls -A "$SCRIPT_ROOT" 2>/dev/null)" ]; then
    rmdir "$SCRIPT_ROOT" && echo "Removed empty source folder: $SCRIPT_ROOT" || true
fi

echo "=== Post-install finalize complete ==="
