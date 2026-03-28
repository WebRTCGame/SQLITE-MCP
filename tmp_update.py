import sqlite3
conn = sqlite3.connect('data/project_memory.db')
c = conn.cursor()

# Note entity for local config guidance
c.execute("INSERT OR REPLACE INTO entities (id, type, name, description, status) VALUES (?, ?, ?, ?, ?)", (
    'note.install-workspace-scoped-mcp-config', 'note', 'Project-scoped MCP config', 'Ensure each workspace uses its own .vscode/mcp.json with relative data path to avoid cross-project DB sharing.', 'active'
))

# Task entity for phase 9
c.execute("INSERT OR REPLACE INTO entities (id, type, name, description, status) VALUES (?, ?, ?, ?, ?)", (
    'task.phase9.ensure-project-scoped-mcp-config', 'task', 'Ensure project-scoped .vscode/mcp.json with relative DB path', 'Install script and docs must create project-local MCP config and not rely on absolute global project paths.', 'planned'
))

# Content entry associated with the note
c.execute("INSERT OR REPLACE INTO content (id, entity_id, content_type, body) VALUES (?, ?, ?, ?)", (
    'content.install-workspace-scoped-mcp-config.1', 'note.install-workspace-scoped-mcp-config', 'analysis',
    'To avoid accidentally using another project''s database, prefer per-workspace config at .vscode/mcp.json with paths relative to the repo. The install script writes this file and the .venv path, and sets the project database path to data/project_memory.db for current repository. The global user mcp.json entry is a convenience fallback and is not the authoritative project view.'
))

# Link new task and note into phase 9
for child in ['task.phase9.ensure-project-scoped-mcp-config', 'note.install-workspace-scoped-mcp-config']:
    c.execute("INSERT OR IGNORE INTO relationships (id, from_entity, to_entity, type) VALUES (?, ?, ?, ?)", (
        f"rel.phase9.{child}", 'phase.9.human-visibility-and-review-surfaces', child, 'contains'
    ))

conn.commit()
conn.close()
