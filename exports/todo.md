<!-- Generated file: do not edit manually. -->
<!-- Description: Generated task backlog grouped from the SQLite source of truth. -->
<!-- Generated at: 2026-03-28 13:37:15 UTC -->
# Todo

Source of truth: SQLite project memory.

## Phase 4

- Add clearer operational docs for environment variables, database location, and transport choice. (status=planned)
- Add response-size safeguards and pagination limits where they are still missing. (status=planned)
- Add structured logging and basic request timing. (status=planned)
- Decide whether high-frequency read tools should default to compact mode. (status=planned)

## Phase 5

- Add structured migration paths for architecture, decisions, notes, and plan content. (status=planned)
- Decide when `roadmap.md` stops being a maintained source file and becomes generated-only. (status=planned)
- Define the cutoff for removing non-README markdown files from the repo workflow. (status=planned)
- Improve generated `architecture`, `decisions`, `notes`, and `plan` views to the same level now reached by `roadmap` and `todo`. (status=planned)

## Phase 6

- Add acceptance tests that bootstrap a project and walk through a realistic AI workflow. (status=planned)
- Add large-content and pagination tests where relevant. (status=planned)
- Add one regression path that verifies backup, restore, and regenerated document output together. (status=planned)

## Phase 7

- Decide attribute namespace rules. (status=planned)
- Decide canonical entity id rules. (status=planned)
- Decide relationship vocabulary and whether a registry table is worth the complexity. (status=planned)
- Decide retention policy details for `reasoning` and `log` content. (status=planned)
- Decide whether markdown views are generated on demand only or also auto-synced. (status=planned)

## Phase 8

- Add tooling to rebuild embeddings after significant content changes. (status=planned)
- Define clear rules for which entity or content types should be embedded. (status=planned)
- Evaluate whether embeddings materially improve retrieval quality for real project-memory workloads. (status=planned)
- If they do, add an optional embeddings or vector-search layer that augments, but does not replace, the relational source of truth. (status=planned)

