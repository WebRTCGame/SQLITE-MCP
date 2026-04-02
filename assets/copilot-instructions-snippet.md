## SQLite Project Memory

This project uses the **`sqlite-project-memory` MCP server** as the single source of truth for all project state.

### Mandatory rules

- **NEVER** create, modify, or delete `.md` files for notes, tasks, decisions, roadmaps, or architecture.
- **ALWAYS** use `sqlite-project-memory` MCP tools to store and retrieve project knowledge.
- `README.md` is the **only** markdown file you may edit directly.
- Files in `Project Memory/pm_exports/` are read-only derived artifacts — never edit them directly.

### Tool usage guide

| Intent | Tool to use |
|--------|-------------|
| Add a task / todo | `create_entity` (entity_type: `task`) |
| Record a decision | `create_entity` (entity_type: `decision`) |
| Document a component | `create_entity` (entity_type: `component`) + `write_content` |
| Add a note to an item | `write_content` or `append_content` |
| Query project state | `query_view`, `list_entities`, `get_entity` |
| Search knowledge | `search_content` |
| Link two items | `add_relationship` or `connect_entities` |
| Export to markdown | `export_markdown_views` with `user_requested: true` — only when explicitly asked |

### First action each session

Before making changes, call `get_project_context` to confirm the database path and project root, then call `get_recent_activity` or `query_view` to orient yourself.
