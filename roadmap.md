# SQLite MCP Roadmap

## Goal

Finish the SQLite-backed project memory MCP so it is reliable for frequent AI use, not just technically functional.

The target state is:

- SQLite is the authoritative source of truth.
- Markdown files are generated views, not primary storage.
- The AI uses explicit MCP verbs for most writes.
- Raw SQL is limited to read-only inspection and reporting.
- The database remains clean enough to be useful over long periods of repeated AI interaction.

## Current State

Already implemented:

- Generic graph-friendly schema built around `entities`, `attributes`, `relationships`, `content`, `events`, `snapshots`, `snapshot_entities`, and `tags`.
- AI-oriented MCP tools for idempotent entity writes, relationship creation, narrative content, project bootstrap, read-only SQL, recent activity, and markdown view generation/export.
- Basic validation for ids, types, keys, and duplicate relationships.
- Basic tests covering the DB layer and generated markdown behavior.

This means the project is already usable as a prototype. The remaining work is to make it durable, safe, testable, and operationally practical.

## Design Constraints

These constraints should continue to guide every change:

- Everything is an entity.
- Everything can relate to everything.
- State must be authoritative.
- Narrative is separate from structure.
- Generated documents are outputs, not storage.
- The AI should not depend on generic write SQL for normal operation.

## Phase 1: Close Core Gaps

Objective: finish the missing lifecycle and schema-control pieces so the memory store does not only grow forever.

Tasks:

- Add `archive_entity` tool and supporting DB behavior.
- Add `delete_entity` tool with safety checks.
- Add `delete_relationship` tool.
- Add `merge_entities` tool for duplicate cleanup.
- Add explicit schema version tracking.
- Add migration handling for future schema changes.
- Add stronger validation for entity ids, attribute keys, and relationship types.

Acceptance criteria:

- Entities can be archived without being physically deleted.
- Dangerous deletes require strict validation and do not silently orphan data.
- Duplicate entities can be merged with deterministic behavior.
- The database exposes a schema version and can safely evolve.
- Relationship creation is restricted to known or validated relationship types.

## Phase 2: AI Hygiene And Memory Quality

Objective: make the system resilient to frequent AI usage patterns that would otherwise degrade memory quality.

Tasks:

- Add `find_similar_entities` to detect likely duplicates before creation.
- Add `resolve_entity_by_name` or `get_or_create_entity` helper flow.
- Add orphan detection for content, tags, and relationships.
- Add duplicate and low-quality attribute detection.
- Add retention or summarization rules for high-volume narrative types such as `reasoning` and `log`.
- Add consistency checks for malformed ids, invalid statuses, and broken references.

Acceptance criteria:

- The AI can resolve likely existing entities before creating new ones.
- The server can report duplicate candidates and orphans.
- Long-running usage does not create unbounded low-value reasoning noise without a cleanup path.
- A database health check can identify major hygiene issues.

## Phase 3: Higher-Level AI Read Models

Objective: reduce tool chatter by giving the AI direct summary tools for common project-memory tasks.

Tasks:

- Add `get_project_state` summary.
- Add `get_open_tasks` summary.
- Add `get_decision_log` summary.
- Add `get_architecture_summary` summary.
- Add `get_recent_reasoning` summary.
- Add `get_dependency_view` summary for graph-oriented inspection.

Acceptance criteria:

- A fresh AI session can recover meaningful project context with a small number of tool calls.
- The most common planning and status questions can be answered without custom SQL.
- Summaries return stable, predictable shapes suitable for repeated machine consumption.

## Phase 4: Document View System

Objective: make generated markdown views genuinely useful for humans while keeping the DB authoritative.

Tasks:

- Define required views: `todo.md`, `roadmap.md`, `plan.md`, `architecture.md`, `decisions.md`, `notes.md`.
- Improve markdown rendering templates for each view.
- Support selective export by view name.
- Add overwrite and output-directory safety rules.
- Add regeneration timestamps or provenance markers where appropriate.
- Decide whether views are regenerated on demand only or can also be refreshed by an external workflow.

Acceptance criteria:

- Generated markdown files are readable and useful to humans.
- View generation is deterministic.
- Regenerating views does not mutate authoritative project state.
- The current roadmap file can eventually be generated from DB state instead of maintained manually.

## Phase 5: Testing And Validation

Objective: move from basic validation to confidence that the MCP surface itself is safe to rely on.

Tasks:

- Expand unit tests for archive, delete, merge, migration, and validation rules.
- Add integration tests against the actual FastMCP tool layer.
- Add acceptance tests that bootstrap a project and walk through a realistic AI workflow.
- Add regression tests for duplicate edges, invalid ids, invalid relationship types, and markdown export behavior.
- Add large-content and pagination tests where relevant.

Acceptance criteria:

- Storage-layer behavior is covered by tests.
- MCP tool-layer behavior is covered by tests.
- A realistic end-to-end project-memory scenario passes reliably.
- Common failure modes are protected by regression tests.

## Phase 6: Client And Operator Experience

Objective: make the server easy to run, wire up, inspect, and maintain.

Tasks:

- Add a sample MCP client configuration.
- Add CLI/admin commands for bootstrap, export, and health validation.
- Add clearer operational docs for environment variables, database location, and transport choice.
- Add structured logging and basic request timing.
- Add pagination and size limits to protect against large responses.
- Add JSON import/export for backup and restore.

Acceptance criteria:

- A user can configure the MCP in a client without reverse-engineering the repo.
- Operators can inspect and validate the database without writing code.
- The system provides enough telemetry to debug frequent AI usage.
- Project memory can be backed up and restored cleanly.

## Recommended Build Order

If the goal is to finish this efficiently, do the work in this order:

1. Lifecycle tools: archive, delete, merge.
2. Schema versioning and migrations.
3. Stronger validation and relationship conventions.
4. AI hygiene and duplicate-detection helpers.
5. MCP-layer integration tests.
6. Higher-level summary tools.
7. Better markdown views and export workflow.
8. Client configuration, CLI/admin tooling, backup/restore, and observability.

## Open Decisions

These need to be settled before the MCP can be considered complete:

- Canonical entity id format.
- Allowed relationship types and their semantics.
- Attribute namespace rules.
- Status vocabulary for common entity types.
- Retention policy for `reasoning` and `log` content.
- Whether markdown views are generated on demand only or also auto-synced.

## Definition Of Done

This MCP should be considered finished when all of the following are true:

- The AI can create, update, connect, summarize, archive, merge, and inspect project memory without relying on generic write SQL.
- The schema can evolve safely through versioned migrations.
- Long-term AI usage does not rapidly corrupt memory quality through duplicate or low-value records.
- Generated markdown views are useful outputs but clearly secondary to the database.
- The MCP layer is covered by tests and can be configured in a real client with documented steps.
- Operators can back up, restore, inspect, and validate the system without custom scripts.
