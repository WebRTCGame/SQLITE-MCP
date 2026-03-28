<!-- Generated file: do not edit manually. -->
<!-- Description: Generated implementation plan derived from structured SQLite project memory. -->
<!-- Generated at: 2026-03-28 13:44:47 UTC -->
# Plan

Source of truth: SQLite project memory.

## Current Plan Document

Prioritized top 10 remaining tasks based on current roadmap and implementation state. Focus is on MCP contract quality, integration validation, and operational readiness.

## Prioritized Open Work

### Phase 4

- Add response-size safeguards and pagination limits where they are still missing. (status=planned)
- Decide whether high-frequency read tools should default to compact mode. (status=planned)

### Phase 5

- Decide when `roadmap.md` stops being a maintained source file and becomes generated-only. (status=planned)
- Define the cutoff for removing non-README markdown files from the repo workflow. (status=planned)

### Phase 6

- Add one regression path that verifies backup, restore, and regenerated document output together. (status=planned)
- Add acceptance tests that bootstrap a project and walk through a realistic AI workflow. (status=planned)
- Add large-content and pagination tests where relevant. (status=planned)

### Phase 7

- Decide attribute namespace rules. (status=planned)
- Decide canonical entity id rules. (status=planned)
- Decide relationship vocabulary and whether a registry table is worth the complexity. (status=planned)
- Decide retention policy details for `reasoning` and `log` content. (status=planned)
- Decide whether markdown views are generated on demand only or also auto-synced. (status=planned)

### Phase 8

- Add tooling to rebuild embeddings after significant content changes. (status=planned)
- Define clear rules for which entity or content types should be embedded. (status=planned)
- Evaluate whether embeddings materially improve retrieval quality for real project-memory workloads. (status=planned)
- If they do, add an optional embeddings or vector-search layer that augments, but does not replace, the relational source of truth. (status=planned)
