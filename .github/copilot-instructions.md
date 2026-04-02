# Copilot custom instructions for SQLite MCP

## Goal
Use the SQLite Project Memory database as the canonical source of truth for all project state and managed markdown content.

## Rule (mandatory)
- Do not create/modify/delete any markdown files in repository except `README.md`.
- All generated markdown outputs (todo, roadmap, notes, architecture, decisions, etc.) must be produced via the MCP database tool path (e.g., `render_markdown_views`, `export_markdown_views`) and not from direct filesystem writes in the workspace.
- For content ingestion: use `create_entity`, `upsert_entity`, `append_content`, etc. on the DB.

## Why
This enforces a single-write architecture:
- Database is authoritative for entities, relationships, content.
- Markdown is derived and treated as generated views.
- README.md is the only exception for human-facing project documentation updates.

## Behavior expectations
- If asked to add a note/task/decision, respond with instructions or code that uses SQLite MCP tools, not `Path(...).write_text(...)` to generate md.
- If asked to export or render documentation, use `sqlite-project-memory-admin export-views --user-requested --request-reason ...` or MCP RPC equivalent.
- If asked to read current project state, query the DB via MCP tools (`query_view` for summaries, `list_entities`, `get_recent_activity`, etc.) rather than reading `*.md` files.

## Scope
- Allowed markdown operations:
  - `README.md` edits are fine for guidance or documentation.
  - Render/export from DB through tools is permitted (and should still not directly persist into source without explicit command).
- Disallowed markdown operations:
  - `todo.md`, `roadmap.md`, `plan.md`, `architecture.md`, `decisions.md`, `notes.md`, and all similarly named files.
  - Any direct file IO for `.md` in repository root or subfolders outside database-controlled export workflow.

## Validation
- Before code suggestions, check if the request is about markdown; if yes ensure the answer explains DB-first flow and warns against direct markdown file edits (except README).

---

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