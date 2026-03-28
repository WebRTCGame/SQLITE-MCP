# SQLite MCP Roadmap

## Goal

Finish the SQLite-backed project memory MCP so it is reliable for frequent AI use, not just technically functional.

The target state is:

- SQLite is the authoritative source of truth.
- Markdown files are generated views, not primary storage.
- The AI uses explicit MCP verbs for most writes.
- Raw SQL is limited to read-only inspection and reporting.
- The MCP contract is optimized before the storage encoding is optimized.
- Tool outputs are compact, structured, and predictable for machine consumption.
- The database remains clean enough to be useful over long periods of repeated AI interaction.

## Current State

Already implemented:

- Generic graph-friendly schema built around `entities`, `attributes`, `relationships`, `content`, `events`, `snapshots`, `snapshot_entities`, and `tags`.
- AI-oriented MCP tools for idempotent entity writes, relationship creation, narrative content, project bootstrap, read-only SQL, recent activity, and markdown view generation/export.
- Basic validation for ids, types, keys, and duplicate relationships.
- Lifecycle tools for archive, delete, merge, schema version tracking, and relationship-type guardrails.
- AI-hygiene tools for duplicate detection, name resolution, get-or-create flows, health reporting, and retention pruning.
- Tests covering the DB layer, lifecycle behavior, and generated markdown behavior.

This means the project is already usable as a prototype. The remaining work is to make it durable, safe, testable, and operationally practical.

## Design Constraints

These constraints should continue to guide every change:

- Everything is an entity.
- Everything can relate to everything.
- State must be authoritative.
- Narrative is separate from structure.
- Generated documents are outputs, not storage.
- The AI should not depend on generic write SQL for normal operation.
- Optimize the MCP tool contract before inventing a new storage language.
- Prefer compact structured JSON over prose when returning machine-facing state.
- Keep prose only where narrative memory is actually needed.
- Treat embeddings or vector search as optional augmentation, not the source of truth.

## Architectural Direction

The recent design discussion changes the priority order slightly:

- The main optimization target is the MCP interface, because the AI reads tool outputs rather than raw SQLite pages.
- Token efficiency should come primarily from compact response shapes, summary-first tools, and fewer unnecessary round trips.
- The relational graph schema remains the correct authority layer.
- A custom symbolic language or alternate storage notation is not currently justified.
- If further optimization is needed later, start with controlled vocabularies, short stable codes, and response compaction before redesigning storage.

## Completed Foundations

Already implemented:

- Lifecycle tools for archive, delete, merge, schema version tracking, and relationship-type guardrails.
- AI-hygiene tools for duplicate detection, name resolution, get-or-create flows, health reporting, and retention pruning.
- DB-layer tests covering storage behavior, lifecycle behavior, and generated markdown behavior.

These are no longer the primary remaining gaps. The remaining roadmap starts from the next unfinished layers.

## Phase 3: Higher-Level AI Read Models

Objective: reduce tool chatter by giving the AI direct summary tools for common project-memory tasks.

Tasks:

- Add `get_project_state` summary.
- Add `get_open_tasks` summary.
- Add `get_decision_log` summary.
- Add `get_architecture_summary` summary.
- Add `get_recent_reasoning` summary.
- Add `get_dependency_view` summary for graph-oriented inspection.
- Make these responses compact and deterministic, with stable field names and minimal narrative filler.
- Add pagination and explicit limits where any summary can grow large.

Acceptance criteria:

- A fresh AI session can recover meaningful project context with a small number of tool calls.
- The most common planning and status questions can be answered without custom SQL.
- Summaries return stable, predictable shapes suitable for repeated machine consumption.
- High-frequency queries avoid verbose prose and unnecessary repeated fields.

## Phase 4: Compact Contracts And Controlled Vocabularies

Objective: improve AI efficiency without redesigning the storage model.

Tasks:

- Define stable response schemas for all high-frequency MCP tools.
- Add compact response modes where large or repetitive payloads are expected.
- Introduce controlled vocabularies or short stable codes for relationship types, statuses, and common entity classifications.
- Decide whether relationship types should be backed by a registry table rather than hard-coded conventions alone.
- Add response-size safeguards so large queries fail predictably or paginate instead of returning oversized payloads.
- Keep prose fields optional in machine-facing reads unless explicitly requested.

Acceptance criteria:

- The AI can complete common workflows with fewer tool calls and fewer tokens.
- Tool outputs remain easy to validate programmatically.
- No custom symbolic storage language is required to achieve practical efficiency gains.

## Phase 5: Document View System

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

## Phase 6: Testing And Validation

Objective: move from basic validation to confidence that the MCP surface itself is safe to rely on.

Tasks:

- Add integration tests against the actual FastMCP tool layer.
- Add acceptance tests that bootstrap a project and walk through a realistic AI workflow.
- Add regression tests for compact response contracts, duplicate edges, invalid ids, invalid relationship types, and markdown export behavior.
- Add large-content and pagination tests where relevant.

Acceptance criteria:

- Storage-layer behavior is covered by tests.
- MCP tool-layer behavior is covered by tests.
- A realistic end-to-end project-memory scenario passes reliably.
- Common failure modes are protected by regression tests.

## Phase 7: Client And Operator Experience

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

## Phase 8: Optional Semantic Retrieval

Objective: add fuzzy recall only after the core relational and MCP contract layers are stable.

Tasks:

- Evaluate whether embeddings materially improve retrieval quality for real project-memory workloads.
- If they do, add an optional embeddings or vector-search layer that augments, but does not replace, the relational source of truth.
- Define clear rules for which entity or content types should be embedded.
- Add tooling to rebuild embeddings after significant content changes.

Acceptance criteria:

- Semantic retrieval improves recall for ambiguous or fuzzy queries.
- Core project state remains queryable without any vector dependency.
- The system remains debuggable when embeddings are absent or stale.

## Recommended Build Order

If the goal is to finish this efficiently, do the work in this order:

1. Higher-level summary tools with compact, stable response shapes.
2. Controlled vocabularies and compact contract work.
3. MCP-layer integration tests.
4. Better markdown views and export workflow.
5. Client configuration, CLI/admin tooling, backup/restore, and observability.
6. Optional semantic retrieval only if real usage justifies it.

## Open Decisions

These need to be settled before the MCP can be considered complete:

- Canonical entity id format.
- Allowed relationship types and their semantics.
- Whether relationship types should have a registry table and short stable codes.
- Attribute namespace rules.
- Status vocabulary for common entity types.
- Whether high-frequency read tools should expose a compact mode by default.
- Retention policy for `reasoning` and `log` content.
- Whether markdown views are generated on demand only or also auto-synced.
- Whether embeddings are worth the added operational complexity for this project.

## Definition Of Done

This MCP should be considered finished when all of the following are true:

- The AI can create, update, connect, summarize, archive, merge, and inspect project memory without relying on generic write SQL.
- The schema can evolve safely through versioned migrations.
- Long-term AI usage does not rapidly corrupt memory quality through duplicate or low-value records.
- High-frequency MCP responses are compact, structured, and stable enough for repeated machine consumption.
- Generated markdown views are useful outputs but clearly secondary to the database.
- The MCP layer is covered by tests and can be configured in a real client with documented steps.
- Operators can back up, restore, inspect, and validate the system without custom scripts.
