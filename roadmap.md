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
- Higher-level AI read models for project state, open tasks, decision logs, architecture summaries, recent reasoning, and dependency views.
- Compact response envelopes for high-frequency summary tools.
- Admin CLI support for bootstrap, health checks, markdown export, JSON backup, and JSON restore.
- Repo-local sample MCP client configuration.
- Generated markdown headers with description and generation timestamp.
- Tests covering the DB layer, CLI layer, MCP integration, lifecycle behavior, and generated markdown behavior.

This means the core MCP is finished and usable. The remaining work is now operational polish, content migration, and optional enhancement rather than core functionality.

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

## Completed AI Read Models

Already implemented:

- `get_project_state` for compact project resumption.
- `get_open_tasks` for actionable task summaries.
- `get_decision_log` for decision state plus recent supporting excerpts.
- `get_architecture_summary` for compact architecture node and edge inspection.
- `get_recent_reasoning` for reasoning recovery without broad content scans.
- `get_dependency_view` for dependency-oriented graph inspection.
- Explicit limits and deterministic field shapes across these summary reads.

## Completed Compact Contracts

Already implemented:

- Stable compact response envelopes for high-frequency summary tools.
- Compact-mode support exposed through the MCP server.
- Response metadata suitable for repeated machine consumption.

## Completed Testing And Operator Basics

Already implemented:

- MCP stdio integration testing.
- JSON backup and restore workflows.
- Sample MCP client configuration in the repo.
- Admin CLI commands for bootstrap, export, health, roadmap sync, and snapshot operations.

## Phase 4: Operational Polish

Objective: make the finished core easier to operate, observe, and trust over long-running use.

Tasks:

- Add response-size safeguards and pagination limits where they are still missing.
- Decide whether high-frequency read tools should default to compact mode.

Acceptance criteria:

- Operators can diagnose requests and runtime behavior without instrumenting the code manually.
- Remaining large responses fail predictably or paginate cleanly.
- Runtime behavior is documented well enough for day-to-day use.

## Phase 5: Content Migration

Objective: finish moving remaining hand-maintained project documents into DB-backed authoritative state.

Tasks:

- Decide when `roadmap.md` stops being a maintained source file and becomes generated-only.
- Define the cutoff for removing non-README markdown files from the repo workflow.

Acceptance criteria:

- Remaining human-facing documents are reproducible from SQLite with acceptable quality.
- The repo can move toward `README.md` as the only hand-maintained markdown source.

## Phase 6: Broader Acceptance Coverage

Objective: add a small number of realistic end-to-end scenarios beyond the current focused integration coverage.

Tasks:

- Add acceptance tests that bootstrap a project and walk through a realistic AI workflow.
- Add large-content and pagination tests where relevant.
- Add one regression path that verifies backup, restore, and regenerated document output together.

Acceptance criteria:

- Storage-layer behavior is covered by tests.
- A realistic end-to-end project-memory scenario passes reliably.
- Common failure modes are protected by regression tests.

## Phase 7: Policy Decisions

Objective: resolve the remaining modeling and workflow choices that affect long-term consistency.

Tasks:

- Decide canonical entity id rules.
- Decide relationship vocabulary and whether a registry table is worth the complexity.
- Decide attribute namespace rules.
- Decide retention policy details for `reasoning` and `log` content.
- Decide whether markdown views are generated on demand only or also auto-synced.

Acceptance criteria:

- The remaining modeling choices are explicit instead of implicit.
- Long-running use follows stable conventions rather than ad hoc habits.

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

1. Operational polish.
2. Content migration for remaining markdown-backed areas.
3. Broader acceptance coverage.
4. Resolve remaining policy decisions.
5. Optional semantic retrieval only if real usage justifies it.

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

For the current repository, the core of this definition is already satisfied. The remaining work is about migration completeness, operational polish, and optional future capabilities rather than unfinished core behavior.
