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
- If asked to read current project state, query the DB via MCP tools (`get_project_state`, `list_entities`, `get_recent_activity`, etc.) rather than reading `*.md` files.

## Scope
- Allowed markdown operations:
  - `README.md` edits are fine for guidance or documentation.
  - Render/export from DB through tools is permitted (and should still not directly persist into source without explicit command).
- Disallowed markdown operations:
  - `todo.md`, `roadmap.md`, `plan.md`, `architecture.md`, `decisions.md`, `notes.md`, and all similarly named files.
  - Any direct file IO for `.md` in repository root or subfolders outside database-controlled export workflow.

## Validation
- Before code suggestions, check if the request is about markdown; if yes ensure the answer explains DB-first flow and warns against direct markdown file edits (except README).