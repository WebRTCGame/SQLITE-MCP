<!-- Generated file: do not edit manually. -->
<!-- Description: Generated note and narrative summary derived from SQLite project memory. -->
<!-- Generated at: 2026-03-28 13:44:47 UTC -->
# Notes

Source of truth: SQLite project memory.

## Current Notes Document

- No notes document content has been synced yet.

## Recent Narrative Entries

### Phase 4: Operational Polish [spec]

- Operators can diagnose requests and runtime behavior without instrumenting the code manually.
- Remaining large responses fail predictably or paginate cleanly.
- Runtime behavior is documented well enough for day-to-day use.

### Phase 5: Content Migration [spec]

- Remaining human-facing documents are reproducible from SQLite with acceptable quality.
- The repo can move toward `README.md` as the only hand-maintained markdown source.

### Phase 6: Broader Acceptance Coverage [spec]

- Storage-layer behavior is covered by tests.
- A realistic end-to-end project-memory scenario passes reliably.
- Common failure modes are protected by regression tests.

### Phase 7: Policy Decisions [spec]

- The remaining modeling choices are explicit instead of implicit.
- Long-running use follows stable conventions rather than ad hoc habits.

### Active Plan [note]

Prioritized top 10 remaining tasks based on current roadmap and implementation state. Focus is on MCP contract quality, integration validation, and operational readiness.

### Roadmap [spec]

The recent design discussion changes the priority order slightly:

- The main optimization target is the MCP interface, because the AI reads tool outputs rather than raw SQLite pages.
- Token efficiency should come primarily from compact response shapes, summary-first tools, and fewer unnecessary round trips.
- The relational graph schema remains the correct authority layer.
- A custom symbolic...

### Roadmap [spec]

Already implemented:

- `get_project_state` for compact project resumption.
- `get_open_tasks` for actionable task summaries.
- `get_decision_log` for decision state plus recent supporting excerpts.
- `get_architecture_summary` for compact architecture node and edge inspection.
- `get_recent_reasoning` for reasoning recovery without broad content scans.
- `get_dependency_view` for dependency-or...

### Roadmap [spec]

Already implemented:

- Lifecycle tools for archive, delete, merge, schema version tracking, and relationship-type guardrails.
- AI-hygiene tools for duplicate detection, name resolution, get-or-create flows, health reporting, and retention pruning.
- DB-layer tests covering storage behavior, lifecycle behavior, and generated markdown behavior.

These are no longer the primary remaining gaps. T...

### Roadmap [spec]

Already implemented:

- Generic graph-friendly schema built around `entities`, `attributes`, `relationships`, `content`, `events`, `snapshots`, `snapshot_entities`, and `tags`.
- AI-oriented MCP tools for idempotent entity writes, relationship creation, narrative content, project bootstrap, read-only SQL, recent activity, and markdown view generation/export.
- Basic validation for ids, types, k...

### Roadmap [spec]

This MCP should be considered finished when all of the following are true:

- The AI can create, update, connect, summarize, archive, merge, and inspect project memory without relying on generic write SQL.
- The schema can evolve safely through versioned migrations.
- Long-term AI usage does not rapidly corrupt memory quality through duplicate or low-value records.
- High-frequency MCP response...

### Roadmap [spec]

These constraints should continue to guide every change:

- Everything is an entity.
- Everything can relate to everything.
- State must be authoritative.
- Narrative is separate from structure.
- Generated documents are outputs, not storage.
- The AI should not depend on generic write SQL for normal operation.
- Optimize the MCP tool contract before inventing a new storage language.
- Prefer c...

### Roadmap [spec]

Finish the SQLite-backed project memory MCP so it is reliable for frequent AI use, not just technically functional.

The target state is:

- SQLite is the authoritative source of truth.
- Markdown files are generated views, not primary storage.
- The AI uses explicit MCP verbs for most writes.
- Raw SQL is limited to read-only inspection and reporting.
- The MCP contract is optimized before the...

### Roadmap [spec]

If the goal is to finish this efficiently, do the work in this order:

1. Operational polish.
2. Content migration for remaining markdown-backed areas.
3. Broader acceptance coverage.
4. Resolve remaining policy decisions.
5. Optional semantic retrieval only if real usage justifies it.

### Phase 4: Compact Contracts And Controlled Vocabularies [spec]

- The AI can complete common workflows with fewer tool calls and fewer tokens.
- Tool outputs remain easy to validate programmatically.
- No custom symbolic storage language is required to achieve practical efficiency gains.

### Phase 5: Document View System [spec]

- Generated markdown files are readable and useful to humans.
- View generation is deterministic.
- Regenerating views does not mutate authoritative project state.
- The current roadmap file can eventually be generated from DB state instead of maintained manually.

### Phase 6: Testing And Validation [spec]

- Storage-layer behavior is covered by tests.
- MCP tool-layer behavior is covered by tests.
- A realistic end-to-end project-memory scenario passes reliably.
- Common failure modes are protected by regression tests.

### Phase 7: Client And Operator Experience [spec]

- A user can configure the MCP in a client without reverse-engineering the repo.
- Operators can inspect and validate the database without writing code.
- The system provides enough telemetry to debug frequent AI usage.
- Project memory can be backed up and restored cleanly.

### Phase 8: Optional Semantic Retrieval [spec]

- Semantic retrieval improves recall for ambiguous or fuzzy queries.
- Core project state remains queryable without any vector dependency.
- The system remains debuggable when embeddings are absent or stale.

### roadmap.md [note]

Current focus: compact AI-facing MCP contracts, controlled vocabularies, and integration-level validation.

### SQLite MCP [note]

This repository is using its own SQLite MCP server as a live test of project-memory workflows.
