from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlite_mcp_server.db import DOCUMENT_TARGETS, DatabaseManager, ValidationError


def _default_db_path() -> Path:
    configured = os.getenv("SQLITE_MCP_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / "data" / "project_memory.db").resolve()


def _default_export_dir() -> Path:
    configured = os.getenv("SQLITE_MCP_EXPORT_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / "exports").resolve()


def _default_backup_path() -> Path:
    return (Path.cwd() / "exports" / "project_memory.snapshot.json").resolve()


def _connect_db(db_path: Path) -> DatabaseManager:
    manager = DatabaseManager(db_path)
    manager.connect()
    return manager


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _slugify_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")[:64] or "item"


def _ensure_content(
    manager: DatabaseManager,
    entity_id: str,
    content_type: str,
    body: str,
    content_id: str,
) -> None:
    existing = manager._fetch_one(
        "SELECT id FROM content WHERE id = ?",
        (content_id,),
    )
    if existing is None:
        manager.append_content(
            entity_id,
            content_type,
            body,
            content_id=content_id,
        )


def _upsert_content(
    manager: DatabaseManager,
    entity_id: str,
    content_type: str,
    body: str,
    content_id: str,
) -> None:
    normalized_body = body.strip()
    if not normalized_body:
        return
    existing = manager._fetch_one(
        "SELECT id, body FROM content WHERE id = ?",
        (content_id,),
    )
    if existing is None:
        manager.append_content(
            entity_id,
            content_type,
            normalized_body,
            content_id=content_id,
        )
        return
    if existing["body"] == normalized_body:
        return
    with manager._transaction() as connection:
        connection.execute(
            "UPDATE content SET entity_id = ?, content_type = ?, body = ? WHERE id = ?",
            (entity_id, content_type, normalized_body, content_id),
        )
        manager._touch_entity(connection, entity_id)
        manager._record_event(
            connection,
            entity_id,
            "content.updated",
            {"content_id": content_id, "content_type": content_type},
        )


def _resolve_memory_area(manager: DatabaseManager, target: str) -> dict[str, Any]:
    if target not in DOCUMENT_TARGETS:
        raise ValidationError(f"unsupported document target: {target!r}")
    entity_type = DOCUMENT_TARGETS[target]["entity_type"]
    entity = manager._fetch_one(
        """
        SELECT DISTINCT e.id, e.type, e.name, e.status
        FROM entities e
        LEFT JOIN relationships r ON r.to_entity = e.id AND r.type = 'has_memory_area'
        LEFT JOIN entities p ON p.id = r.from_entity AND p.type = 'project'
        WHERE e.type = ?
        ORDER BY CASE WHEN p.id IS NOT NULL THEN 0 ELSE 1 END, e.updated_at DESC, e.id ASC
        LIMIT 1
        """,
        (entity_type,),
    )
    if entity is None:
        raise ValidationError(
            f"no memory-area entity exists for target {target!r}; bootstrap project memory first"
        )
    return entity


def _sync_document(manager: DatabaseManager, target: str, input_path: Path) -> dict[str, Any]:
    resolved_path = input_path.resolve()
    body = resolved_path.read_text(encoding="utf-8").strip()
    if not body:
        raise ValidationError(f"input document {str(resolved_path)!r} is empty")

    config = DOCUMENT_TARGETS[target]
    entity = _resolve_memory_area(manager, target)
    _upsert_content(
        manager,
        entity["id"],
        config["content_type"],
        body,
        config["content_id"],
    )
    manager.upsert_attributes(
        entity["id"],
        {
            "source_path": str(resolved_path),
            "source_sync_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "source_kind": "markdown",
        },
    )
    return {
        "target": target,
        "entity_id": entity["id"],
        "input_path": str(resolved_path),
        "content_id": config["content_id"],
        "content_type": config["content_type"],
    }


def _bootstrap_self(manager: DatabaseManager, repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    result = manager.bootstrap_project_memory(
        project_id="project.sqlite-mcp",
        project_name="SQLite MCP",
        description="SQLite-backed MCP server that stores project memory for AI agents.",
        tags=["mcp", "project-memory", "sqlite"],
    )

    tracked_files = [
        ("file.pyproject", "pyproject.toml", "Project packaging and dependency configuration.", ["config"]),
        ("file.readme", "README.md", "Project overview, run instructions, and tool guidance.", ["docs"]),
        ("file.db", "src/sqlite_mcp_server/db.py", "Database schema, validation, lifecycle, hygiene, and summary query logic.", ["database", "source"]),
        ("file.server", "src/sqlite_mcp_server/server.py", "FastMCP server tools, resources, prompts, and entrypoint.", ["mcp", "source"]),
        ("file.cli", "src/sqlite_mcp_server/cli.py", "Admin CLI for bootstrapping, inspecting, and exporting project memory.", ["cli", "source"]),
        ("file.tests-db", "tests/test_db.py", "Database-layer regression tests for lifecycle, hygiene, summaries, and exports.", ["tests"]),
    ]

    created_files: list[str] = []
    for entity_id, relative_path, description, tags in tracked_files:
        target = repo_root / relative_path
        if not target.exists():
            continue
        manager.upsert_entity(
            entity_id=entity_id,
            entity_type="file",
            name=relative_path,
            description=description,
            status="active",
            attributes={"language": target.suffix.lstrip(".") or "text", "path": relative_path},
            tags=tags,
        )
        manager.connect_entities("project.sqlite-mcp", entity_id, "documents")
        created_files.append(relative_path)

    manager.upsert_entity(
        "module.sqlite-mcp-server",
        "module",
        name="sqlite_mcp_server",
        description="Primary Python package for the SQLite project memory MCP server.",
        status="active",
        tags=["backend", "mcp", "python"],
    )
    manager.connect_entities("project.sqlite-mcp", "module.sqlite-mcp-server", "contains")
    for entity_id in ["file.db", "file.server", "file.cli"]:
        if manager._entity_exists(entity_id):
            manager.connect_entities("module.sqlite-mcp-server", entity_id, "contains")

    if manager._entity_exists("file.server") and manager._entity_exists("file.db"):
        manager.connect_entities("file.server", "file.db", "depends_on")
    if manager._entity_exists("file.tests-db") and manager._entity_exists("file.db"):
        manager.connect_entities("file.tests-db", "file.db", "depends_on")
    if manager._entity_exists("file.cli") and manager._entity_exists("file.db"):
        manager.connect_entities("file.cli", "file.db", "depends_on")

    _ensure_content(
        manager,
        "project.sqlite-mcp",
        "note",
        "This repository is using its own SQLite MCP server as a live test of project-memory workflows.",
        "note.self-hosting",
    )
    _ensure_content(
        manager,
        "project.sqlite-mcp.roadmap",
        "note",
        "Current focus: keep roadmap state authoritative in SQLite and only generate roadmap markdown on explicit request.",
        "note.roadmap-focus",
    )

    state = manager.get_project_state(limit=10)
    return {
        "bootstrap": result,
        "tracked_files": created_files,
        "project_state": state,
    }

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sqlite-project-memory-admin")
    parser.add_argument("--db-path", type=Path, default=_default_db_path())

    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_self = subparsers.add_parser(
        "bootstrap-self",
        help="Seed this repository into its own project-memory database.",
    )
    bootstrap_self.add_argument("--repo-root", type=Path, default=Path.cwd())

    project_state = subparsers.add_parser(
        "project-state",
        help="Print a compact project-state summary from the database.",
    )
    project_state.add_argument("--limit", type=int, default=10)

    health = subparsers.add_parser(
        "health",
        help="Print the current database health report.",
    )
    health.add_argument("--limit", type=int, default=25)

    export_views = subparsers.add_parser(
        "export-views",
        help="Write generated markdown views from the database.",
    )
    export_views.add_argument("--output-dir", type=Path, default=_default_export_dir())
    export_views.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting existing generated view files.",
    )
    export_views.add_argument(
        "--require-existing-dir",
        action="store_true",
        help="Fail instead of creating the output directory when it does not already exist.",
    )
    export_views.add_argument(
        "--user-requested",
        action="store_true",
        help="Confirm that a human explicitly requested these generated markdown views.",
    )
    export_views.add_argument(
        "--request-reason",
        type=str,
        default=None,
        help="Short description of the user's explicit request for generated markdown views.",
    )
    export_views.add_argument("views", nargs="*", default=None)

    export_json = subparsers.add_parser(
        "export-json",
        help="Write a full JSON snapshot of the SQLite project-memory database.",
    )
    export_json.add_argument("--output-path", type=Path, default=_default_backup_path())

    import_json = subparsers.add_parser(
        "import-json",
        help="Import a full JSON snapshot into the SQLite project-memory database.",
    )
    import_json.add_argument("--input-path", type=Path, required=True)
    import_json.add_argument("--merge", action="store_true", help="Merge into existing records instead of replacing them.")

    sync_document = subparsers.add_parser(
        "sync-document",
        help="Synchronize a hand-maintained markdown document into a project memory area anchor.",
    )
    sync_document.add_argument("target", choices=sorted(DOCUMENT_TARGETS.keys()))
    sync_document.add_argument("--input-path", type=Path, required=True)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    manager = _connect_db(args.db_path.resolve())
    try:
        if args.command == "bootstrap-self":
            _print_json(_bootstrap_self(manager, args.repo_root))
            return

        if args.command == "project-state":
            _print_json(manager.get_project_state(limit=args.limit))
            return

        if args.command == "health":
            _print_json(manager.get_database_health(limit=args.limit))
            return

        if args.command == "export-views":
            _print_json(
                manager.export_markdown_views(
                    output_dir=args.output_dir.resolve(),
                    view_names=args.views,
                    overwrite=args.force,
                    require_existing_dir=args.require_existing_dir,
                    user_requested=args.user_requested,
                    request_reason=args.request_reason,
                )
            )
            return

        if args.command == "export-json":
            output_path = args.output_path.resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(manager.export_json_snapshot(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            _print_json({"output_path": str(output_path)})
            return

        if args.command == "import-json":
            input_path = args.input_path.resolve()
            snapshot = json.loads(input_path.read_text(encoding="utf-8"))
            _print_json(manager.import_json_snapshot(snapshot, replace=not args.merge))
            return

        if args.command == "sync-document":
            _print_json(_sync_document(manager, args.target, args.input_path))
            return

        parser.error(f"unknown command: {args.command}")
    finally:
        manager.close()