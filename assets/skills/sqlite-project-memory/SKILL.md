---
name: sqlite-project-memory
description: >
  Use this skill to store, retrieve, or query project knowledge via the
  sqlite-project-memory MCP server. Apply it for tasks like adding todos,
  recording decisions, documenting architecture, searching project history,
  linking related items, or exporting generated documentation.
  This skill replaces all markdown file creation — project memory lives
  exclusively in the SQLite database accessed through MCP tools.
---

# SQLite Project Memory Skill

## When to use this skill

Use `sqlite-project-memory` MCP tools whenever you need to:

- Add, update, or complete a task or todo
- Record a decision and its rationale
- Document a component, module, or architectural pattern
- Search previous decisions or notes
- Link related entities (e.g., a task implements a decision)
- Export readable documentation that the user explicitly requested

## Rules

1. **Never create markdown files** for notes, tasks, decisions, architecture, or roadmaps.
2. **README.md** is the only file you may edit directly.
3. All project knowledge must be persisted through `sqlite-project-memory` MCP tools.
4. Only export markdown when the user explicitly asks — use `export_markdown_views` with `user_requested: true`.

## Session start

Before making changes:

1. Call `get_project_context` to confirm the database path and project root.
2. Call `get_recent_activity` or `query_view` to orient yourself on current state.

## Common operations

### Add a task

```json
get_or_create_entity({
  "entity_type": "task",
  "name": "Short task title",
  "description": "What needs to be done and why",
  "status": "open"
})
```

### Record a decision

```json
get_or_create_entity({
  "entity_type": "decision",
  "name": "Decision title",
  "description": "What was decided",
  "attributes": {
    "rationale": "Why this was chosen",
    "alternatives": "What else was considered"
  }
})
```

### Document a component

```json
get_or_create_entity({
  "entity_type": "component",
  "name": "Component name",
  "description": "What this component does"
})
```

Then attach detailed content:

```json
write_content({
  "entity_id": "<id from previous call>",
  "mode": "append",
  "content_type": "markdown",
  "content": "# Component Details\n\nMarkdown content goes here..."
})
```

### Query current project state

```json
query_view({ "view_name": "open_tasks" })
list_entities({ "entity_type": "task", "status": "open" })
```

### Search for past decisions or notes

```json
search_content({ "query": "authentication approach" })
```

### Link two entities

```json
connect_entities({
  "from_entity": "task-abc123",
  "to_entity": "decision-def456",
  "relationship_type": "implements"
})
```

### Update an existing entity

```json
update_entity({
  "entity_id": "<id>",
  "status": "done",
  "description": "Updated description"
})
```

### Export documentation (only when user explicitly requests)

```json
export_markdown_views({
  "user_requested": true,
  "request_reason": "User requested export for review",
  "view_names": ["open_tasks", "decision_log", "architecture_summary"]
})
```
