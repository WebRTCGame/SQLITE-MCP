<!-- Generated file: do not edit manually. -->
<!-- Description: Generated architecture summary derived from structured SQLite project memory. -->
<!-- Generated at: 2026-03-28 13:44:47 UTC -->
# Architecture

Source of truth: SQLite project memory.

## Current Architecture Document

- No architecture document content has been synced yet.

## Summary

- Nodes: 9
- Relationships: 59
- file: 7
- architecture: 1
- module: 1

## Key Nodes

- [architecture] Architecture (active)
- [file] src/sqlite_mcp_server/cli.py (active)
- [file] src/sqlite_mcp_server/db.py (active)
- [file] pyproject.toml (active)
- [file] README.md (active)
- [file] roadmap.md (active)
- [file] src/sqlite_mcp_server/server.py (active)
- [file] tests/test_db.py (active)
- [module] sqlite_mcp_server (active)

## Key Relationships

- phase.7.policy-decisions -[contains]-> task.phase7.decide-relationship-vocabulary-and-whether-a-registry-table-is-w
- phase.4.operational-polish -[contains]-> task.phase4.decide-whether-high-frequency-read-tools-should-default-to-compa
- phase.6.broader-acceptance-coverage -[contains]-> task.phase6.add-one-regression-path-that-verifies-backup-restore-and-regener
- phase.5.content-migration -[contains]-> task.phase5.decide-when-roadmap-md-stops-being-a-maintained-source-file-and-
- phase.5.content-migration -[contains]-> task.phase5.add-structured-migration-paths-for-architecture-decisions-notes-
- phase.5.content-migration -[contains]-> task.phase5.define-the-cutoff-for-removing-non-readme-markdown-files-from-th
- phase.6.broader-acceptance-coverage -[contains]-> task.phase6.add-large-content-and-pagination-tests-where-relevant
- phase.4.operational-polish -[contains]-> task.phase4.add-response-size-safeguards-and-pagination-limits-where-they-ar
- phase.6.broader-acceptance-coverage -[contains]-> task.phase6.add-acceptance-tests-that-bootstrap-a-project-and-walk-through-a
- project.sqlite-mcp.roadmap -[contains]-> phase.5.content-migration
- phase.4.operational-polish -[contains]-> task.phase4.add-clearer-operational-docs-for-environment-variables-database-
- phase.7.policy-decisions -[contains]-> task.phase7.decide-canonical-entity-id-rules
- phase.4.operational-polish -[contains]-> task.phase4.add-structured-logging-and-basic-request-timing
- phase.5.content-migration -[contains]-> task.phase5.improve-generated-architecture-decisions-notes-and-plan-views-to
- phase.7.policy-decisions -[contains]-> task.phase7.decide-whether-markdown-views-are-generated-on-demand-only-or-al
- project.sqlite-mcp.roadmap -[contains]-> phase.7.policy-decisions
- phase.7.policy-decisions -[contains]-> task.phase7.decide-retention-policy-details-for-reasoning-and-log-content
- phase.7.policy-decisions -[contains]-> task.phase7.decide-attribute-namespace-rules
- project.sqlite-mcp.roadmap -[contains]-> phase.6.broader-acceptance-coverage
- project.sqlite-mcp.roadmap -[contains]-> phase.4.operational-polish
- phase.6.testing-and-validation -[contains]-> task.phase6.add-integration-tests-against-the-actual-fastmcp-tool-layer
- phase.7.client-and-operator-experience -[contains]-> task.phase7.add-cli-admin-commands-for-bootstrap-export-and-health-validatio
- phase.7.client-and-operator-experience -[contains]-> task.phase7.add-clearer-operational-docs-for-environment-variables-database-
- phase.4.compact-contracts-and-controlled-vocabularies -[contains]-> task.phase4.define-stable-response-schemas-for-all-high-frequency-mcp-tools
- project.sqlite-mcp.roadmap -[contains]-> phase.6.testing-and-validation
- project.sqlite-mcp.roadmap -[contains]-> phase.4.compact-contracts-and-controlled-vocabularies
- phase.8.optional-semantic-retrieval -[contains]-> task.phase8.define-clear-rules-for-which-entity-or-content-types-should-be-e
- project.sqlite-mcp.roadmap -[contains]-> phase.7.client-and-operator-experience
- phase.7.client-and-operator-experience -[contains]-> task.phase7.add-structured-logging-and-basic-request-timing
- phase.5.document-view-system -[contains]-> task.phase5.decide-whether-views-are-regenerated-on-demand-only-or-can-also-
- phase.4.compact-contracts-and-controlled-vocabularies -[contains]-> task.phase4.add-compact-response-modes-where-large-or-repetitive-payloads-ar
- phase.8.optional-semantic-retrieval -[contains]-> task.phase8.evaluate-whether-embeddings-materially-improve-retrieval-quality
- project.sqlite-mcp.roadmap -[contains]-> phase.8.optional-semantic-retrieval
- project.sqlite-mcp.roadmap -[contains]-> phase.5.document-view-system
- phase.5.document-view-system -[contains]-> task.phase5.define-required-views-todo-md-roadmap-md-plan-md-architecture-md
- phase.5.document-view-system -[contains]-> task.phase5.add-overwrite-and-output-directory-safety-rules
- phase.7.client-and-operator-experience -[contains]-> task.phase7.add-json-import-export-for-backup-and-restore
- phase.7.client-and-operator-experience -[contains]-> task.phase7.add-pagination-and-size-limits-to-protect-against-large-response
- phase.8.optional-semantic-retrieval -[contains]-> task.phase8.if-they-do-add-an-optional-embeddings-or-vector-search-layer-tha
- phase.4.compact-contracts-and-controlled-vocabularies -[contains]-> task.phase4.introduce-controlled-vocabularies-or-short-stable-codes-for-rela
- phase.4.compact-contracts-and-controlled-vocabularies -[contains]-> task.phase4.keep-prose-fields-optional-in-machine-facing-reads-unless-explic
- phase.8.optional-semantic-retrieval -[contains]-> task.phase8.add-tooling-to-rebuild-embeddings-after-significant-content-chan
- phase.6.testing-and-validation -[contains]-> task.phase6.add-regression-tests-for-compact-response-contracts-duplicate-ed
- phase.4.compact-contracts-and-controlled-vocabularies -[contains]-> task.phase4.add-response-size-safeguards-so-large-queries-fail-predictably-o
- phase.5.document-view-system -[contains]-> task.phase5.improve-markdown-rendering-templates-for-each-view
- phase.7.client-and-operator-experience -[contains]-> task.phase7.add-a-sample-mcp-client-configuration
- phase.4.compact-contracts-and-controlled-vocabularies -[contains]-> task.phase4.decide-whether-relationship-types-should-be-backed-by-a-registry
- phase.5.document-view-system -[contains]-> task.phase5.add-regeneration-timestamps-or-provenance-markers-where-appropri
- phase.6.testing-and-validation -[contains]-> task.phase6.add-large-content-and-pagination-tests-where-relevant
- phase.5.document-view-system -[contains]-> task.phase5.support-selective-export-by-view-name
- phase.6.testing-and-validation -[contains]-> task.phase6.add-acceptance-tests-that-bootstrap-a-project-and-walk-through-a
- file.cli -[depends_on]-> file.db
- module.sqlite-mcp-server -[contains]-> file.cli
- project.sqlite-mcp -[contains]-> module.sqlite-mcp-server
- file.server -[depends_on]-> file.db
- file.tests-db -[depends_on]-> file.db
- project.sqlite-mcp -[contains]-> file.tests-db
- module.sqlite-mcp-server -[contains]-> file.db
- module.sqlite-mcp-server -[contains]-> file.server
