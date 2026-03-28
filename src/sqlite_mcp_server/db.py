from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from threading import RLock
from typing import Any, Iterator
from uuid import uuid4


IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,127}$")
ATTRIBUTE_KEY_RE = re.compile(r"^[a-z][a-z0-9._:-]{1,63}$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")
SCHEMA_VERSION = 1
ALLOWED_RELATIONSHIP_TYPES = {
    "blocks",
    "calls",
    "contains",
    "depends_on",
    "documents",
    "has_memory_area",
    "implements",
    "owned_by",
    "owns",
    "references",
    "relates_to",
    "tracks",
}
COMMON_STATUS_VOCABULARY = {
    "*": {"active", "archived", "deprecated", "done", "draft", "pending"},
    "task": {"active", "blocked", "done", "in_progress", "pending", "planned"},
    "bug": {"active", "done", "investigating", "pending"},
    "feature": {"active", "done", "planned", "proposed"},
    "phase": {"active", "done", "planned"},
    "decision": {"accepted", "draft", "rejected", "superseded"},
    "roadmap": {"active", "done", "planned"},
}
LOW_SIGNAL_ATTRIBUTE_VALUES = {"?", "n/a", "none", "temp", "tbd", "todo", "unknown"}
RETENTION_CONTENT_TYPES = {"log", "reasoning"}
RETAIN_LATEST_CONTENT_COUNT = 20
COMMON_ATTRIBUTE_KEYS = {
    "language",
    "memory_model",
    "owner",
    "path",
    "phase_number",
    "priority",
    "rank",
    "source",
    "source_kind",
    "source_of_truth",
    "source_path",
    "source_sync_at",
    "task_order",
}
RECOMMENDED_ATTRIBUTE_NAMESPACES = ["client.", "meta.", "source.", "trace.", "ui."]
DOCUMENT_TARGETS = {
    "architecture": {
        "entity_type": "architecture",
        "content_id": "document.architecture.current",
        "content_type": "spec",
    },
    "decisions": {
        "entity_type": "decision_log",
        "content_id": "document.decisions.current",
        "content_type": "analysis",
    },
    "plan": {
        "entity_type": "plan",
        "content_id": "document.plan.current",
        "content_type": "spec",
    },
    "notes": {
        "entity_type": "notes",
        "content_id": "document.notes.current",
        "content_type": "note",
    },
}


class ValidationError(ValueError):
    """Raised when input violates server validation rules."""


def _validate_identifier(value: str, label: str) -> str:
    if not value or not IDENTIFIER_RE.fullmatch(value):
        raise ValidationError(
            f"{label} must match {IDENTIFIER_RE.pattern!r}; got {value!r}."
        )
    return value


def _validate_attribute_key(value: str) -> str:
    if not ATTRIBUTE_KEY_RE.fullmatch(value):
        raise ValidationError(
            f"attribute key must match {ATTRIBUTE_KEY_RE.pattern!r}; got {value!r}."
        )
    return value


def _validate_tag(value: str) -> str:
    if not TAG_RE.fullmatch(value):
        raise ValidationError(f"tag must match {TAG_RE.pattern!r}; got {value!r}.")
    return value


def _validate_relationship_type(value: str) -> str:
    normalized = _validate_identifier(value, "relationship type")
    if normalized in ALLOWED_RELATIONSHIP_TYPES or normalized.startswith("custom."):
        return normalized
    allowed = ", ".join(sorted(ALLOWED_RELATIONSHIP_TYPES))
    raise ValidationError(
        "relationship type must be one of the known types "
        f"({allowed}) or use the 'custom.' namespace; got {value!r}."
    )


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _generated_id(prefix: str) -> str:
    return f"{prefix}.{uuid4().hex[:12]}"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized[:64] or "item"


def _normalized_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _bounded_limit(limit: int, *, minimum: int = 1, maximum: int = 100) -> int:
    return max(minimum, min(limit, maximum))


def _bounded_offset(offset: int) -> int:
    return max(0, offset)


def _summary_envelope(schema_name: str, data: dict[str, Any], *, compact: bool) -> dict[str, Any]:
    if not compact:
        return data
    return {
        "schema": schema_name,
        "schema_version": 1,
        "compact": True,
        "data": data,
    }


class DatabaseManager:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()
        self._fts_enabled = False

    def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        self._connection = connection
        self.initialize_schema()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self._connection is None:
            raise RuntimeError("database connection has not been initialized")

        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def initialize_schema(self) -> None:
        base_schema = """
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT,
            description TEXT,
            status TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS attributes (
            entity_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (entity_id, key),
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS relationships (
            id TEXT PRIMARY KEY,
            from_entity TEXT NOT NULL,
            to_entity TEXT NOT NULL,
            type TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_entity) REFERENCES entities(id) ON DELETE CASCADE,
            FOREIGN KEY (to_entity) REFERENCES entities(id) ON DELETE CASCADE,
            CONSTRAINT unique_edge UNIQUE (from_entity, to_entity, type)
        );

        CREATE TABLE IF NOT EXISTS content (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            content_type TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT,
            event_type TEXT NOT NULL,
            data TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS snapshot_entities (
            snapshot_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, entity_id),
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tags (
            entity_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY (entity_id, tag),
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_entities_type_status ON entities(type, status);
        CREATE INDEX IF NOT EXISTS idx_entities_updated_at ON entities(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_attributes_lookup ON attributes(key, value);
        CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_entity, type);
        CREATE INDEX IF NOT EXISTS idx_relationships_to ON relationships(to_entity, type);
        CREATE INDEX IF NOT EXISTS idx_content_entity_type ON content(entity_id, content_type, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_events_entity_created ON events(entity_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag, entity_id);
        """

        with self._transaction() as connection:
            connection.executescript(base_schema)
            self._initialize_schema_meta(connection)

        self._initialize_fts()

    def _initialize_schema_meta(self, connection: sqlite3.Connection) -> None:
        current_version = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        if current_version is None:
            connection.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('schema_initialized_at', CURRENT_TIMESTAMP)"
            )
            return

        stored_version = int(current_version[0])
        if stored_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"database schema version {stored_version} is newer than supported version {SCHEMA_VERSION}"
            )
        if stored_version < SCHEMA_VERSION:
            self._apply_migrations(connection, stored_version, SCHEMA_VERSION)

    def _apply_migrations(
        self,
        connection: sqlite3.Connection,
        from_version: int,
        to_version: int,
    ) -> None:
        migration_steps = {
            1: [],
        }

        for target_version in range(from_version + 1, to_version + 1):
            statements = migration_steps.get(target_version)
            if statements is None:
                raise RuntimeError(f"no migration path registered for schema version {target_version}")
            for statement in statements:
                connection.executescript(statement)
            connection.execute(
                "UPDATE schema_meta SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = 'schema_version'",
                (str(target_version),),
            )

    def _initialize_fts(self) -> None:
        fts_schema = """
        CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
            content_id UNINDEXED,
            entity_id UNINDEXED,
            body,
            content='content',
            content_rowid='rowid'
        );

        CREATE TRIGGER IF NOT EXISTS content_ai AFTER INSERT ON content BEGIN
            INSERT INTO content_fts(rowid, content_id, entity_id, body)
            VALUES (new.rowid, new.id, new.entity_id, new.body);
        END;

        CREATE TRIGGER IF NOT EXISTS content_ad AFTER DELETE ON content BEGIN
            INSERT INTO content_fts(content_fts, rowid, content_id, entity_id, body)
            VALUES ('delete', old.rowid, old.id, old.entity_id, old.body);
        END;

        CREATE TRIGGER IF NOT EXISTS content_au AFTER UPDATE ON content BEGIN
            INSERT INTO content_fts(content_fts, rowid, content_id, entity_id, body)
            VALUES ('delete', old.rowid, old.id, old.entity_id, old.body);
            INSERT INTO content_fts(rowid, content_id, entity_id, body)
            VALUES (new.rowid, new.id, new.entity_id, new.body);
        END;

        INSERT INTO content_fts(rowid, content_id, entity_id, body)
        SELECT rowid, id, entity_id, body FROM content
        WHERE NOT EXISTS (SELECT 1 FROM content_fts LIMIT 1);
        """

        try:
            with self._transaction() as connection:
                connection.executescript(fts_schema)
            self._fts_enabled = True
        except sqlite3.OperationalError:
            self._fts_enabled = False

    def schema_overview(self) -> dict[str, Any]:
        return {
            "database_path": str(self.db_path),
            "fts_enabled": self._fts_enabled,
            "schema_version": self.get_schema_version(),
            "tables": {
                "entities": "authoritative project objects such as tasks, files, modules, decisions, roadmap items",
                "attributes": "flexible key/value metadata for entities",
                "relationships": "typed graph edges between any two entities",
                "content": "unstructured narrative such as notes, specs, analysis, reasoning, logs",
                "events": "audit timeline for mutations and notable state changes",
                "snapshots": "named checkpoints of project state",
                "snapshot_entities": "membership of entities captured in a snapshot",
                "tags": "fast filter labels for entities",
            },
            "validation": {
                "id_pattern": IDENTIFIER_RE.pattern,
                "attribute_key_pattern": ATTRIBUTE_KEY_RE.pattern,
                "tag_pattern": TAG_RE.pattern,
                "allowed_relationship_types": sorted(ALLOWED_RELATIONSHIP_TYPES),
                "custom_relationship_namespace": "custom.",
            },
            "policy": {
                "entity_id": {
                    "generated_format": "<entity_type>.<slug>[.<n>]",
                    "generated_example": "task.add-health-checks",
                    "guidance": "Prefer stable ids that start with the owning entity type. Project memory-area anchors may also use project-scoped ids such as project.sqlite-mcp.roadmap.",
                },
                "relationships": {
                    "registry_table": False,
                    "built_in_types": sorted(ALLOWED_RELATIONSHIP_TYPES),
                    "extension_policy": "Use built-in relationship types when possible; use the custom. namespace for project-specific edges instead of maintaining a registry table.",
                },
                "attributes": {
                    "common_keys": sorted(COMMON_ATTRIBUTE_KEYS),
                    "custom_key_policy": "Use lowercase dotted namespaces for non-common keys.",
                    "recommended_namespaces": RECOMMENDED_ATTRIBUTE_NAMESPACES,
                },
                "statuses": {
                    "common_vocabulary": {key: list(values) for key, values in COMMON_STATUS_VOCABULARY.items()},
                    "fallback_policy": "Other entity types may use stable identifier-style statuses.",
                },
                "retention": {
                    "content_types": sorted(RETENTION_CONTENT_TYPES),
                    "keep_latest": RETAIN_LATEST_CONTENT_COUNT,
                    "prune_default": "manual_dry_run",
                },
                "markdown_views": {
                    "generation_policy": "on_demand_only",
                    "authoritative_source": "sqlite",
                },
                "mcp_read_defaults": {
                    "compact": True,
                    "tools": [
                        "get_project_state",
                        "get_open_tasks",
                        "get_decision_log",
                        "get_architecture_summary",
                        "get_recent_reasoning",
                        "get_dependency_view",
                        "get_recent_activity",
                        "get_entity_graph",
                    ],
                    "opt_out": "Pass compact=false when a fuller response is needed.",
                },
                "semantic_retrieval": {
                    "default_strategy": "fts5_plus_structured_reads",
                    "embeddings_enabled": False,
                    "adoption_threshold": "Only add embeddings after a concrete retrieval gap is observed that FTS5 and existing summary/read models cannot cover.",
                },
            },
        }

    def get_schema_version(self) -> int:
        row = self._fetch_one(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        )
        return int(row["value"]) if row else SCHEMA_VERSION

    def _fetch_one(self, query: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self._lock:
            if self._connection is None:
                raise RuntimeError("database connection has not been initialized")
            row = self._connection.execute(query, parameters).fetchone()
        return dict(row) if row else None

    def _fetch_all(self, query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            if self._connection is None:
                raise RuntimeError("database connection has not been initialized")
            rows = self._connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def _touch_entity(self, connection: sqlite3.Connection, entity_id: str) -> None:
        connection.execute(
            "UPDATE entities SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (entity_id,),
        )

    def _record_event(
        self,
        connection: sqlite3.Connection,
        entity_id: str | None,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        payload = json.dumps(data or {}, sort_keys=True)
        connection.execute(
            "INSERT INTO events (entity_id, event_type, data) VALUES (?, ?, ?)",
            (entity_id, event_type, payload),
        )

    def _entity_exists(self, entity_id: str) -> bool:
        entity = self._fetch_one("SELECT id FROM entities WHERE id = ?", (entity_id,))
        return entity is not None

    def _ensure_entity_exists(self, entity_id: str) -> None:
        if not self._entity_exists(entity_id):
            raise ValidationError(f"entity {entity_id!r} does not exist")

    def _get_relationship_by_edge(
        self,
        from_entity: str,
        to_entity: str,
        relationship_type: str,
    ) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT
                r.*,
                ef.name AS from_name,
                ef.type AS from_type,
                et.name AS to_name,
                et.type AS to_type
            FROM relationships r
            JOIN entities ef ON ef.id = r.from_entity
            JOIN entities et ON et.id = r.to_entity
            WHERE r.from_entity = ? AND r.to_entity = ? AND r.type = ?
            """,
            (from_entity, to_entity, relationship_type),
        )

    def create_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = "active",
        attributes: dict[str, str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        entity_type = _validate_identifier(entity_type, "entity type")
        normalized_status = _validate_identifier(status, "status") if status else None
        normalized_name = _normalize_text(name)
        normalized_description = _normalize_text(description)
        cleaned_attributes = { _validate_attribute_key(key): str(value) for key, value in (attributes or {}).items() }
        cleaned_tags = sorted({_validate_tag(tag) for tag in (tags or [])})

        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO entities (id, type, name, description, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        entity_id,
                        entity_type,
                        normalized_name,
                        normalized_description,
                        normalized_status,
                    ),
                )

                if cleaned_attributes:
                    connection.executemany(
                        "INSERT INTO attributes (entity_id, key, value) VALUES (?, ?, ?)",
                        [(entity_id, key, value) for key, value in cleaned_attributes.items()],
                    )

                if cleaned_tags:
                    connection.executemany(
                        "INSERT INTO tags (entity_id, tag) VALUES (?, ?)",
                        [(entity_id, tag) for tag in cleaned_tags],
                    )

                self._record_event(
                    connection,
                    entity_id,
                    "entity.created",
                    {"type": entity_type, "status": normalized_status},
                )
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"could not create entity {entity_id!r}: {exc}") from exc

        return self.get_entity(entity_id, include_related=True)

    def update_entity(
        self,
        entity_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        updates: list[str] = []
        parameters: list[Any] = []

        if name is not None:
            updates.append("name = ?")
            parameters.append(_normalize_text(name))
        if description is not None:
            updates.append("description = ?")
            parameters.append(_normalize_text(description))
        if status is not None:
            updates.append("status = ?")
            parameters.append(_validate_identifier(status, "status"))

        if not updates:
            raise ValidationError("at least one field must be provided for update")

        parameters.append(entity_id)

        with self._transaction() as connection:
            cursor = connection.execute(
                f"UPDATE entities SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                tuple(parameters),
            )
            if cursor.rowcount == 0:
                raise ValidationError(f"entity {entity_id!r} does not exist")
            self._record_event(connection, entity_id, "entity.updated", {"fields": updates})

        return self.get_entity(entity_id, include_related=True)

    def upsert_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        attributes: dict[str, str] | None = None,
        tags: list[str] | None = None,
        replace_attributes: bool = False,
        replace_tags: bool = False,
    ) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        entity_type = _validate_identifier(entity_type, "entity type")
        exists = self._entity_exists(entity_id)

        if not exists:
            return self.create_entity(
                entity_id=entity_id,
                entity_type=entity_type,
                name=name,
                description=description,
                status=status or "active",
                attributes=attributes,
                tags=tags,
            )

        current = self.get_entity(entity_id, include_related=False)
        if current["type"] != entity_type:
            raise ValidationError(
                f"entity {entity_id!r} already exists with type {current['type']!r}, not {entity_type!r}"
            )

        if any(value is not None for value in (name, description, status)):
            self.update_entity(
                entity_id=entity_id,
                name=name,
                description=description,
                status=status,
            )

        if attributes:
            self.upsert_attributes(entity_id=entity_id, attributes=attributes, replace=replace_attributes)

        if tags is not None:
            self.set_tags(entity_id=entity_id, tags=tags, replace=replace_tags)

        return self.get_entity(entity_id, include_related=True)

    def get_entity(self, entity_id: str, include_related: bool = False) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        entity = self._fetch_one("SELECT * FROM entities WHERE id = ?", (entity_id,))
        if entity is None:
            raise ValidationError(f"entity {entity_id!r} does not exist")

        if include_related:
            entity["attributes"] = {
                row["key"]: row["value"]
                for row in self._fetch_all(
                    "SELECT key, value FROM attributes WHERE entity_id = ? ORDER BY key",
                    (entity_id,),
                )
            }
            entity["tags"] = [
                row["tag"]
                for row in self._fetch_all(
                    "SELECT tag FROM tags WHERE entity_id = ? ORDER BY tag",
                    (entity_id,),
                )
            ]
            entity["relationships"] = self.list_relationships(entity_id=entity_id, direction="both")
            entity["content"] = self._fetch_all(
                "SELECT id, content_type, body, created_at FROM content WHERE entity_id = ? ORDER BY created_at DESC",
                (entity_id,),
            )
            entity["events"] = self._fetch_all(
                "SELECT id, event_type, data, created_at FROM events WHERE entity_id = ? ORDER BY created_at DESC LIMIT 25",
                (entity_id,),
            )

        return entity

    def list_entities(
        self,
        entity_type: str | None = None,
        status: str | None = None,
        attribute_key: str | None = None,
        attribute_value: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        joins: list[str] = []
        conditions: list[str] = ["1 = 1"]
        parameters: list[Any] = []

        if entity_type:
            conditions.append("e.type = ?")
            parameters.append(_validate_identifier(entity_type, "entity type"))

        if status:
            conditions.append("e.status = ?")
            parameters.append(_validate_identifier(status, "status"))

        if attribute_key:
            joins.append("JOIN attributes a ON a.entity_id = e.id")
            conditions.append("a.key = ?")
            parameters.append(_validate_attribute_key(attribute_key))
            if attribute_value is not None:
                conditions.append("a.value = ?")
                parameters.append(str(attribute_value))

        if tag:
            joins.append("JOIN tags t ON t.entity_id = e.id")
            conditions.append("t.tag = ?")
            parameters.append(_validate_tag(tag))

        if search:
            conditions.append(
                "(" 
                "COALESCE(e.name, '') LIKE ? OR "
                "COALESCE(e.description, '') LIKE ? OR "
                "EXISTS (SELECT 1 FROM content c WHERE c.entity_id = e.id AND c.body LIKE ?)"
                ")"
            )
            like = f"%{search.strip()}%"
            parameters.extend([like, like, like])

        parameters.append(limit)

        query = f"""
        SELECT DISTINCT e.*
        FROM entities e
        {' '.join(joins)}
        WHERE {' AND '.join(conditions)}
        ORDER BY e.updated_at DESC, e.id ASC
        LIMIT ?
        """
        return self._fetch_all(query, tuple(parameters))

    def upsert_attributes(
        self,
        entity_id: str,
        attributes: dict[str, str],
        replace: bool = False,
    ) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        if not attributes:
            raise ValidationError("attributes must not be empty")

        cleaned_attributes = {
            _validate_attribute_key(key): str(value)
            for key, value in attributes.items()
        }

        with self._transaction() as connection:
            if replace:
                connection.execute("DELETE FROM attributes WHERE entity_id = ?", (entity_id,))

            connection.executemany(
                """
                INSERT INTO attributes (entity_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(entity_id, key) DO UPDATE SET value = excluded.value
                """,
                [(entity_id, key, value) for key, value in cleaned_attributes.items()],
            )
            self._touch_entity(connection, entity_id)
            self._record_event(
                connection,
                entity_id,
                "attributes.upserted",
                {"keys": sorted(cleaned_attributes.keys()), "replace": replace},
            )

        return self.get_entity(entity_id, include_related=True)

    def set_tags(self, entity_id: str, tags: list[str], replace: bool = False) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        cleaned_tags = sorted({_validate_tag(tag) for tag in tags})

        with self._transaction() as connection:
            if replace:
                connection.execute("DELETE FROM tags WHERE entity_id = ?", (entity_id,))

            if cleaned_tags:
                connection.executemany(
                    "INSERT OR IGNORE INTO tags (entity_id, tag) VALUES (?, ?)",
                    [(entity_id, tag) for tag in cleaned_tags],
                )

            self._touch_entity(connection, entity_id)
            self._record_event(
                connection,
                entity_id,
                "tags.updated",
                {"tags": cleaned_tags, "replace": replace},
            )

        return self.get_entity(entity_id, include_related=True)

    def add_relationship(
        self,
        relationship_id: str,
        from_entity: str,
        to_entity: str,
        relationship_type: str,
    ) -> dict[str, Any]:
        relationship_id = _validate_identifier(relationship_id, "relationship id")
        from_entity = _validate_identifier(from_entity, "from_entity")
        to_entity = _validate_identifier(to_entity, "to_entity")
        relationship_type = _validate_relationship_type(relationship_type)

        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO relationships (id, from_entity, to_entity, type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (relationship_id, from_entity, to_entity, relationship_type),
                )
                self._touch_entity(connection, from_entity)
                self._touch_entity(connection, to_entity)
                self._record_event(
                    connection,
                    from_entity,
                    "relationship.created",
                    {"relationship_id": relationship_id, "to": to_entity, "type": relationship_type},
                )
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"could not create relationship {relationship_id!r}: {exc}") from exc

        relationship = self._fetch_one(
            """
            SELECT r.*, ef.name AS from_name, et.name AS to_name
            FROM relationships r
            JOIN entities ef ON ef.id = r.from_entity
            JOIN entities et ON et.id = r.to_entity
            WHERE r.id = ?
            """,
            (relationship_id,),
        )
        if relationship is None:
            raise ValidationError(f"relationship {relationship_id!r} was not persisted")
        return relationship

    def connect_entities(
        self,
        from_entity: str,
        to_entity: str,
        relationship_type: str,
        relationship_id: str | None = None,
    ) -> dict[str, Any]:
        from_entity = _validate_identifier(from_entity, "from_entity")
        to_entity = _validate_identifier(to_entity, "to_entity")
        relationship_type = _validate_relationship_type(relationship_type)

        existing = self._get_relationship_by_edge(from_entity, to_entity, relationship_type)
        if existing is not None:
            return existing

        return self.add_relationship(
            relationship_id=relationship_id or _generated_id("rel"),
            from_entity=from_entity,
            to_entity=to_entity,
            relationship_type=relationship_type,
        )

    def list_relationships(
        self,
        entity_id: str | None = None,
        relationship_type: str | None = None,
        direction: str = "both",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if direction not in {"in", "out", "both"}:
            raise ValidationError("direction must be one of: in, out, both")

        conditions: list[str] = ["1 = 1"]
        parameters: list[Any] = []

        if entity_id:
            normalized_entity_id = _validate_identifier(entity_id, "entity id")
            if direction == "out":
                conditions.append("r.from_entity = ?")
                parameters.append(normalized_entity_id)
            elif direction == "in":
                conditions.append("r.to_entity = ?")
                parameters.append(normalized_entity_id)
            else:
                conditions.append("(r.from_entity = ? OR r.to_entity = ?)")
                parameters.extend([normalized_entity_id, normalized_entity_id])

        if relationship_type:
            conditions.append("r.type = ?")
            parameters.append(_validate_relationship_type(relationship_type))

        parameters.append(max(1, min(limit, 500)))

        query = f"""
        SELECT
            r.*, 
            ef.name AS from_name,
            ef.type AS from_type,
            et.name AS to_name,
            et.type AS to_type
        FROM relationships r
        JOIN entities ef ON ef.id = r.from_entity
        JOIN entities et ON et.id = r.to_entity
        WHERE {' AND '.join(conditions)}
        ORDER BY r.created_at DESC, r.id ASC
        LIMIT ?
        """
        return self._fetch_all(query, tuple(parameters))

    def add_content(
        self,
        content_id: str,
        entity_id: str,
        content_type: str,
        body: str,
    ) -> dict[str, Any]:
        content_id = _validate_identifier(content_id, "content id")
        entity_id = _validate_identifier(entity_id, "entity id")
        content_type = _validate_identifier(content_type, "content type")
        normalized_body = body.strip()
        if not normalized_body:
            raise ValidationError("content body must not be empty")

        try:
            with self._transaction() as connection:
                connection.execute(
                    "INSERT INTO content (id, entity_id, content_type, body) VALUES (?, ?, ?, ?)",
                    (content_id, entity_id, content_type, normalized_body),
                )
                self._touch_entity(connection, entity_id)
                self._record_event(
                    connection,
                    entity_id,
                    "content.added",
                    {"content_id": content_id, "content_type": content_type},
                )
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"could not add content {content_id!r}: {exc}") from exc

        content = self._fetch_one(
            "SELECT id, entity_id, content_type, body, created_at FROM content WHERE id = ?",
            (content_id,),
        )
        if content is None:
            raise ValidationError(f"content {content_id!r} was not persisted")
        return content

    def append_content(
        self,
        entity_id: str,
        content_type: str,
        body: str,
        content_id: str | None = None,
    ) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        content_type = _validate_identifier(content_type, "content type")
        return self.add_content(
            content_id=content_id or _generated_id(content_type),
            entity_id=entity_id,
            content_type=content_type,
            body=body,
        )

    def search_content(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValidationError("query must not be empty")

        limit = max(1, min(limit, 100))
        if self._fts_enabled:
            try:
                return self._fetch_all(
                    """
                    SELECT
                        c.id,
                        c.entity_id,
                        e.type AS entity_type,
                        e.name AS entity_name,
                        c.content_type,
                        snippet(content_fts, 2, '[', ']', '...', 16) AS snippet,
                        c.created_at
                    FROM content_fts
                    JOIN content c ON c.rowid = content_fts.rowid
                    JOIN entities e ON e.id = c.entity_id
                    WHERE content_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (normalized_query, limit),
                )
            except sqlite3.OperationalError:
                self._fts_enabled = False

        like = f"%{normalized_query}%"
        return self._fetch_all(
            """
            SELECT
                c.id,
                c.entity_id,
                e.type AS entity_type,
                e.name AS entity_name,
                c.content_type,
                substr(c.body, 1, 240) AS snippet,
                c.created_at
            FROM content c
            JOIN entities e ON e.id = c.entity_id
            WHERE c.body LIKE ?
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (like, limit),
        )

    def create_snapshot(
        self,
        snapshot_id: str,
        name: str,
        description: str | None = None,
        entity_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        snapshot_id = _validate_identifier(snapshot_id, "snapshot id")
        normalized_name = name.strip()
        if not normalized_name:
            raise ValidationError("snapshot name must not be empty")

        selected_entity_ids = entity_ids or [row["id"] for row in self._fetch_all("SELECT id FROM entities ORDER BY id")]
        normalized_entity_ids = [_validate_identifier(entity_id, "entity id") for entity_id in selected_entity_ids]

        try:
            with self._transaction() as connection:
                connection.execute(
                    "INSERT INTO snapshots (id, name, description) VALUES (?, ?, ?)",
                    (snapshot_id, normalized_name, _normalize_text(description)),
                )
                if normalized_entity_ids:
                    connection.executemany(
                        "INSERT INTO snapshot_entities (snapshot_id, entity_id) VALUES (?, ?)",
                        [(snapshot_id, entity_id) for entity_id in normalized_entity_ids],
                    )
                self._record_event(
                    connection,
                    None,
                    "snapshot.created",
                    {"snapshot_id": snapshot_id, "entity_count": len(normalized_entity_ids)},
                )
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"could not create snapshot {snapshot_id!r}: {exc}") from exc

        return self.get_snapshot(snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        snapshot_id = _validate_identifier(snapshot_id, "snapshot id")
        snapshot = self._fetch_one("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,))
        if snapshot is None:
            raise ValidationError(f"snapshot {snapshot_id!r} does not exist")

        snapshot["entities"] = self._fetch_all(
            """
            SELECT e.*
            FROM snapshot_entities se
            JOIN entities e ON e.id = se.entity_id
            WHERE se.snapshot_id = ?
            ORDER BY e.type, e.id
            """,
            (snapshot_id,),
        )
        return snapshot

    def get_project_overview(self) -> dict[str, Any]:
        return {
            "database_path": str(self.db_path),
            "fts_enabled": self._fts_enabled,
            "schema_version": self.get_schema_version(),
            "entity_counts_by_type": self._fetch_all(
                "SELECT type, COUNT(*) AS count FROM entities GROUP BY type ORDER BY count DESC, type ASC"
            ),
            "entity_counts_by_status": self._fetch_all(
                "SELECT status, COUNT(*) AS count FROM entities GROUP BY status ORDER BY count DESC, status ASC"
            ),
            "top_tags": self._fetch_all(
                "SELECT tag, COUNT(*) AS count FROM tags GROUP BY tag ORDER BY count DESC, tag ASC LIMIT 20"
            ),
            "recent_events": self._fetch_all(
                "SELECT id, entity_id, event_type, data, created_at FROM events ORDER BY created_at DESC, id DESC LIMIT 20"
            ),
            "snapshot_count": self._fetch_one("SELECT COUNT(*) AS count FROM snapshots") or {"count": 0},
        }

    def get_project_state(self, limit: int = 10, compact: bool = False) -> dict[str, Any]:
        limit = _bounded_limit(limit, maximum=50)
        project = self._fetch_one(
            """
            SELECT id, type, name, status, updated_at
            FROM entities
            WHERE type = 'project'
            ORDER BY updated_at DESC, id ASC
            LIMIT 1
            """
        )
        project_id = project["id"] if project else None

        memory_areas: list[dict[str, Any]] = []
        if project_id is not None:
            memory_areas = self._fetch_all(
                """
                SELECT e.id, e.type, e.name, e.status, e.updated_at
                FROM relationships r
                JOIN entities e ON e.id = r.to_entity
                WHERE r.from_entity = ? AND r.type = 'has_memory_area'
                ORDER BY e.type ASC, e.id ASC
                """,
                (project_id,),
            )

        counts = {
            "entities": (self._fetch_one("SELECT COUNT(*) AS count FROM entities") or {"count": 0})["count"],
            "relationships": (self._fetch_one("SELECT COUNT(*) AS count FROM relationships") or {"count": 0})["count"],
            "content": (self._fetch_one("SELECT COUNT(*) AS count FROM content") or {"count": 0})["count"],
            "events": (self._fetch_one("SELECT COUNT(*) AS count FROM events") or {"count": 0})["count"],
            "snapshots": (self._fetch_one("SELECT COUNT(*) AS count FROM snapshots") or {"count": 0})["count"],
        }
        open_task_count = (
            self._fetch_one(
                """
                SELECT COUNT(*) AS count
                FROM entities
                WHERE type IN ('task', 'todo', 'bug')
                  AND COALESCE(status, 'active') NOT IN ('done', 'archived', 'deprecated')
                  AND NOT EXISTS (
                      SELECT 1 FROM relationships mr
                      WHERE mr.to_entity = entities.id AND mr.type = 'has_memory_area'
                  )
                """
            )
            or {"count": 0}
        )["count"]

        return _summary_envelope(
            "project_state.v1",
            {
            "project": project,
            "schema_version": self.get_schema_version(),
            "fts_enabled": self._fts_enabled,
            "counts": counts,
            "open_task_count": open_task_count,
            "entity_counts_by_type": self._fetch_all(
                "SELECT type, COUNT(*) AS count FROM entities GROUP BY type ORDER BY count DESC, type ASC LIMIT ?",
                (limit,),
            ),
            "memory_areas": memory_areas,
            "recent_events": self._fetch_all(
                "SELECT entity_id, event_type, created_at FROM events ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ),
            },
            compact=compact,
        )

    def get_open_tasks(self, limit: int = 25, offset: int = 0, compact: bool = False) -> dict[str, Any]:
        limit = _bounded_limit(limit, maximum=100)
        offset = _bounded_offset(offset)
        total_count = (
            self._fetch_one(
                """
                SELECT COUNT(*) AS count
                FROM entities
                WHERE type IN ('task', 'todo', 'bug')
                  AND COALESCE(status, 'active') NOT IN ('done', 'archived', 'deprecated')
                  AND NOT EXISTS (
                      SELECT 1 FROM relationships mr
                      WHERE mr.to_entity = entities.id AND mr.type = 'has_memory_area'
                  )
                """
            )
            or {"count": 0}
        )["count"]

        items = self._fetch_all(
            """
            SELECT
                e.id,
                e.type,
                e.name,
                e.status,
                e.updated_at,
                MAX(CASE WHEN a.key = 'rank' THEN a.value END) AS rank,
                MAX(CASE WHEN a.key = 'priority' THEN a.value END) AS priority,
                MAX(CASE WHEN a.key = 'owner' THEN a.value END) AS owner,
                MAX(CASE WHEN a.key = 'phase_number' THEN a.value END) AS phase_number,
                SUM(CASE WHEN r.type = 'depends_on' AND r.from_entity = e.id THEN 1 ELSE 0 END) AS dependency_count,
                SUM(CASE WHEN r.type = 'blocks' AND r.to_entity = e.id THEN 1 ELSE 0 END) AS blocker_count
            FROM entities e
            LEFT JOIN attributes a ON a.entity_id = e.id
            LEFT JOIN relationships r ON r.from_entity = e.id OR r.to_entity = e.id
            WHERE e.type IN ('task', 'todo', 'bug')
              AND COALESCE(e.status, 'active') NOT IN ('done', 'archived', 'deprecated')
                            AND NOT EXISTS (
                                    SELECT 1 FROM relationships mr
                                    WHERE mr.to_entity = e.id AND mr.type = 'has_memory_area'
                            )
            GROUP BY e.id, e.type, e.name, e.status, e.updated_at
            ORDER BY
                CASE
                    WHEN MAX(CASE WHEN a.key = 'rank' THEN a.value END) GLOB '[0-9]*'
                    THEN CAST(MAX(CASE WHEN a.key = 'rank' THEN a.value END) AS INTEGER)
                    ELSE 9999
                END,
                CASE COALESCE(MAX(CASE WHEN a.key = 'priority' THEN a.value END), '')
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                    ELSE 5
                END,
                e.updated_at DESC,
                e.id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return _summary_envelope(
            "open_tasks.v1",
            {
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total_count,
            "items": items,
            },
            compact=compact,
        )

    def get_decision_log(self, limit: int = 25, offset: int = 0, compact: bool = False) -> dict[str, Any]:
        limit = _bounded_limit(limit, maximum=100)
        offset = _bounded_offset(offset)
        total_count = (
            self._fetch_one(
                "SELECT COUNT(*) AS count FROM entities WHERE type IN ('decision', 'decision_log')"
            )
            or {"count": 0}
        )["count"]
        items = self._fetch_all(
            """
            SELECT
                e.id,
                e.type,
                e.name,
                e.status,
                e.description,
                e.updated_at,
                (
                    SELECT substr(c.body, 1, 240)
                    FROM content c
                    WHERE c.entity_id = e.id
                      AND c.content_type IN ('reasoning', 'analysis', 'spec', 'note')
                    ORDER BY c.created_at DESC, c.id DESC
                    LIMIT 1
                ) AS latest_note,
                (
                    SELECT c.created_at
                    FROM content c
                    WHERE c.entity_id = e.id
                      AND c.content_type IN ('reasoning', 'analysis', 'spec', 'note')
                    ORDER BY c.created_at DESC, c.id DESC
                    LIMIT 1
                ) AS latest_note_at
            FROM entities e
            WHERE e.type IN ('decision', 'decision_log')
            ORDER BY e.updated_at DESC, e.id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return _summary_envelope(
            "decision_log.v1",
            {
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total_count,
            "items": items,
            },
            compact=compact,
        )

    def get_architecture_summary(
        self,
        node_limit: int = 100,
        relationship_limit: int = 150,
        compact: bool = False,
    ) -> dict[str, Any]:
        node_limit = _bounded_limit(node_limit, maximum=250)
        relationship_limit = _bounded_limit(relationship_limit, maximum=400)
        nodes = self._fetch_all(
            """
            SELECT id, type, name, status, updated_at
            FROM entities
            WHERE type IN ('architecture', 'module', 'component', 'service', 'file')
            ORDER BY type ASC, updated_at DESC, id ASC
            LIMIT ?
            """,
            (node_limit,),
        )
        relationships = self._fetch_all(
            """
            SELECT from_entity, to_entity, type, created_at
            FROM relationships
            WHERE type IN ('depends_on', 'implements', 'calls', 'owns', 'contains')
            ORDER BY created_at DESC, id ASC
            LIMIT ?
            """,
            (relationship_limit,),
        )
        return _summary_envelope(
            "architecture_summary.v1",
            {
            "node_count": (
                self._fetch_one(
                    "SELECT COUNT(*) AS count FROM entities WHERE type IN ('architecture', 'module', 'component', 'service', 'file')"
                )
                or {"count": 0}
            )["count"],
            "relationship_count": (
                self._fetch_one(
                    "SELECT COUNT(*) AS count FROM relationships WHERE type IN ('depends_on', 'implements', 'calls', 'owns', 'contains')"
                )
                or {"count": 0}
            )["count"],
            "node_types": self._fetch_all(
                """
                SELECT type, COUNT(*) AS count
                FROM entities
                WHERE type IN ('architecture', 'module', 'component', 'service', 'file')
                GROUP BY type
                ORDER BY count DESC, type ASC
                """
            ),
            "relationship_types": self._fetch_all(
                """
                SELECT type, COUNT(*) AS count
                FROM relationships
                WHERE type IN ('depends_on', 'implements', 'calls', 'owns', 'contains')
                GROUP BY type
                ORDER BY count DESC, type ASC
                """
            ),
            "nodes": nodes,
            "relationships": relationships,
            },
            compact=compact,
        )

    def get_recent_reasoning(self, limit: int = 20, offset: int = 0, compact: bool = False) -> dict[str, Any]:
        limit = _bounded_limit(limit, maximum=100)
        offset = _bounded_offset(offset)
        total_count = (
            self._fetch_one("SELECT COUNT(*) AS count FROM content WHERE content_type = 'reasoning'")
            or {"count": 0}
        )["count"]
        items = self._fetch_all(
            """
            SELECT
                c.id,
                c.entity_id,
                e.type AS entity_type,
                e.name AS entity_name,
                substr(c.body, 1, 280) AS excerpt,
                c.created_at
            FROM content c
            JOIN entities e ON e.id = c.entity_id
            WHERE c.content_type = 'reasoning'
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return _summary_envelope(
            "recent_reasoning.v1",
            {
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total_count,
            "items": items,
            },
            compact=compact,
        )

    def get_dependency_view(
        self,
        root_entity_id: str | None = None,
        max_depth: int = 2,
        relationship_types: list[str] | None = None,
        limit: int = 200,
        compact: bool = False,
    ) -> dict[str, Any]:
        selected_types = relationship_types or ["depends_on", "blocks"]
        normalized_types = sorted({_validate_relationship_type(value) for value in selected_types})
        max_depth = _bounded_limit(max_depth, maximum=8)
        limit = _bounded_limit(limit, maximum=500)
        placeholders = ", ".join("?" for _ in normalized_types)

        if root_entity_id is None:
            relationships = self._fetch_all(
                f"""
                SELECT r.id, r.from_entity, r.to_entity, r.type, r.created_at
                FROM relationships r
                WHERE r.type IN ({placeholders})
                ORDER BY r.created_at DESC, r.id ASC
                LIMIT ?
                """,
                tuple([*normalized_types, limit]),
            )
            node_ids = sorted(
                {
                    edge_id
                    for relationship in relationships
                    for edge_id in (relationship["from_entity"], relationship["to_entity"])
                }
            )
            nodes = []
            if node_ids:
                node_placeholders = ", ".join("?" for _ in node_ids)
                nodes = self._fetch_all(
                    f"SELECT id, type, name, status FROM entities WHERE id IN ({node_placeholders}) ORDER BY type ASC, id ASC",
                    tuple(node_ids),
                )
            return _summary_envelope(
                "dependency_view.v1",
                {
                "root": None,
                "depth": 1,
                "relationship_types": normalized_types,
                "node_count": len(nodes),
                "relationship_count": len(relationships),
                "nodes": nodes,
                "relationships": relationships,
                },
                compact=compact,
            )

        root_entity_id = _validate_identifier(root_entity_id, "root entity id")
        relationships = self._fetch_all(
            f"""
            WITH RECURSIVE graph(depth, id, from_entity, to_entity, type, created_at) AS (
                SELECT 1, r.id, r.from_entity, r.to_entity, r.type, r.created_at
                FROM relationships r
                WHERE r.from_entity = ? AND r.type IN ({placeholders})

                UNION ALL

                SELECT graph.depth + 1, r.id, r.from_entity, r.to_entity, r.type, r.created_at
                FROM relationships r
                JOIN graph ON r.from_entity = graph.to_entity
                WHERE graph.depth < ? AND r.type IN ({placeholders})
            )
            SELECT DISTINCT depth, id, from_entity, to_entity, type, created_at
            FROM graph
            ORDER BY depth ASC, created_at DESC, id ASC
            LIMIT ?
            """,
            tuple([root_entity_id, *normalized_types, max_depth, *normalized_types, limit]),
        )
        node_ids = {root_entity_id}
        for relationship in relationships:
            node_ids.add(relationship["from_entity"])
            node_ids.add(relationship["to_entity"])
        node_placeholders = ", ".join("?" for _ in node_ids)
        nodes = self._fetch_all(
            f"SELECT id, type, name, status FROM entities WHERE id IN ({node_placeholders}) ORDER BY type ASC, id ASC",
            tuple(sorted(node_ids)),
        )
        return _summary_envelope(
            "dependency_view.v1",
            {
            "root": self.get_entity(root_entity_id, include_related=False),
            "depth": max_depth,
            "relationship_types": normalized_types,
            "node_count": len(nodes),
            "relationship_count": len(relationships),
            "nodes": nodes,
            "relationships": relationships,
            },
            compact=compact,
        )

    def export_json_snapshot(self) -> dict[str, Any]:
        return {
            "schema": "sqlite_project_memory_snapshot.v1",
            "schema_version": self.get_schema_version(),
            "tables": {
                "entities": self._fetch_all("SELECT * FROM entities ORDER BY id"),
                "attributes": self._fetch_all("SELECT * FROM attributes ORDER BY entity_id, key"),
                "relationships": self._fetch_all("SELECT * FROM relationships ORDER BY id"),
                "content": self._fetch_all("SELECT * FROM content ORDER BY id"),
                "events": self._fetch_all("SELECT * FROM events ORDER BY id"),
                "snapshots": self._fetch_all("SELECT * FROM snapshots ORDER BY id"),
                "snapshot_entities": self._fetch_all(
                    "SELECT * FROM snapshot_entities ORDER BY snapshot_id, entity_id"
                ),
                "tags": self._fetch_all("SELECT * FROM tags ORDER BY entity_id, tag"),
                "schema_meta": self._fetch_all("SELECT * FROM schema_meta ORDER BY key"),
            },
        }

    def import_json_snapshot(self, snapshot: dict[str, Any], replace: bool = True) -> dict[str, Any]:
        if snapshot.get("schema") != "sqlite_project_memory_snapshot.v1":
            raise ValidationError("snapshot schema must be 'sqlite_project_memory_snapshot.v1'")
        tables = snapshot.get("tables")
        if not isinstance(tables, dict):
            raise ValidationError("snapshot.tables must be an object")

        ordered_tables = [
            "entities",
            "attributes",
            "relationships",
            "content",
            "events",
            "snapshots",
            "snapshot_entities",
            "tags",
            "schema_meta",
        ]
        for table_name in ordered_tables:
            if table_name not in tables or not isinstance(tables[table_name], list):
                raise ValidationError(f"snapshot.tables[{table_name!r}] must be a list")

        with self._transaction() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            try:
                if replace:
                    for table_name in [
                        "snapshot_entities",
                        "tags",
                        "events",
                        "content",
                        "relationships",
                        "attributes",
                        "snapshots",
                        "entities",
                        "schema_meta",
                    ]:
                        connection.execute(f"DELETE FROM {table_name}")

                for row in tables["entities"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO entities (id, type, name, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            row["id"],
                            row["type"],
                            row.get("name"),
                            row.get("description"),
                            row.get("status"),
                            row.get("created_at"),
                            row.get("updated_at"),
                        ),
                    )
                for row in tables["attributes"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO attributes (entity_id, key, value) VALUES (?, ?, ?)",
                        (row["entity_id"], row["key"], row["value"]),
                    )
                for row in tables["relationships"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO relationships (id, from_entity, to_entity, type, created_at) VALUES (?, ?, ?, ?, ?)",
                        (row["id"], row["from_entity"], row["to_entity"], row["type"], row.get("created_at")),
                    )
                for row in tables["content"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO content (id, entity_id, content_type, body, created_at) VALUES (?, ?, ?, ?, ?)",
                        (row["id"], row["entity_id"], row["content_type"], row["body"], row.get("created_at")),
                    )
                for row in tables["events"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO events (id, entity_id, event_type, data, created_at) VALUES (?, ?, ?, ?, ?)",
                        (row["id"], row.get("entity_id"), row["event_type"], row.get("data"), row.get("created_at")),
                    )
                for row in tables["snapshots"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO snapshots (id, name, description, created_at) VALUES (?, ?, ?, ?)",
                        (row["id"], row["name"], row.get("description"), row.get("created_at")),
                    )
                for row in tables["snapshot_entities"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO snapshot_entities (snapshot_id, entity_id) VALUES (?, ?)",
                        (row["snapshot_id"], row["entity_id"]),
                    )
                for row in tables["tags"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO tags (entity_id, tag) VALUES (?, ?)",
                        (row["entity_id"], row["tag"]),
                    )
                for row in tables["schema_meta"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
                        (row["key"], row["value"], row.get("updated_at")),
                    )
            finally:
                connection.execute("PRAGMA foreign_keys = ON")

        return {
            "schema": snapshot["schema"],
            "replace": replace,
            "imported_counts": {table_name: len(tables[table_name]) for table_name in ordered_tables},
        }

    def archive_entity(
        self,
        entity_id: str,
        reason: str | None = None,
        archived_status: str = "archived",
    ) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        archived_status = _validate_identifier(archived_status, "archived status")
        self._ensure_entity_exists(entity_id)

        with self._transaction() as connection:
            cursor = connection.execute(
                "UPDATE entities SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (archived_status, entity_id),
            )
            if cursor.rowcount == 0:
                raise ValidationError(f"entity {entity_id!r} does not exist")
            self._record_event(
                connection,
                entity_id,
                "entity.archived",
                {"reason": _normalize_text(reason), "status": archived_status},
            )

        return self.get_entity(entity_id, include_related=True)

    def delete_relationship(self, relationship_id: str) -> dict[str, Any]:
        relationship_id = _validate_identifier(relationship_id, "relationship id")
        relationship = self._fetch_one(
            "SELECT * FROM relationships WHERE id = ?",
            (relationship_id,),
        )
        if relationship is None:
            raise ValidationError(f"relationship {relationship_id!r} does not exist")

        with self._transaction() as connection:
            connection.execute("DELETE FROM relationships WHERE id = ?", (relationship_id,))
            self._touch_entity(connection, relationship["from_entity"])
            self._touch_entity(connection, relationship["to_entity"])
            self._record_event(
                connection,
                relationship["from_entity"],
                "relationship.deleted",
                {
                    "relationship_id": relationship_id,
                    "to": relationship["to_entity"],
                    "type": relationship["type"],
                },
            )

        return relationship

    def _entity_dependency_counts(self, entity_id: str) -> dict[str, int]:
        return {
            "attributes": self._fetch_one(
                "SELECT COUNT(*) AS count FROM attributes WHERE entity_id = ?",
                (entity_id,),
            )["count"],
            "tags": self._fetch_one(
                "SELECT COUNT(*) AS count FROM tags WHERE entity_id = ?",
                (entity_id,),
            )["count"],
            "content": self._fetch_one(
                "SELECT COUNT(*) AS count FROM content WHERE entity_id = ?",
                (entity_id,),
            )["count"],
            "events": self._fetch_one(
                "SELECT COUNT(*) AS count FROM events WHERE entity_id = ?",
                (entity_id,),
            )["count"],
            "relationships_out": self._fetch_one(
                "SELECT COUNT(*) AS count FROM relationships WHERE from_entity = ?",
                (entity_id,),
            )["count"],
            "relationships_in": self._fetch_one(
                "SELECT COUNT(*) AS count FROM relationships WHERE to_entity = ?",
                (entity_id,),
            )["count"],
            "snapshots": self._fetch_one(
                "SELECT COUNT(*) AS count FROM snapshot_entities WHERE entity_id = ?",
                (entity_id,),
            )["count"],
        }

    def delete_entity(self, entity_id: str, force: bool = False) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        entity = self.get_entity(entity_id, include_related=False)
        dependency_counts = self._entity_dependency_counts(entity_id)

        blockers = {
            key: value
            for key, value in dependency_counts.items()
            if key in {"content", "relationships_out", "relationships_in", "snapshots"} and value > 0
        }

        if entity.get("status") != "archived" and not force:
            raise ValidationError(
                f"entity {entity_id!r} must be archived before deletion or deleted with force=True"
            )
        if blockers and not force:
            raise ValidationError(
                f"entity {entity_id!r} still has dependent records and cannot be deleted safely: {blockers}"
            )

        with self._transaction() as connection:
            connection.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            self._record_event(
                connection,
                None,
                "entity.deleted",
                {
                    "deleted_entity_id": entity_id,
                    "deleted_entity_type": entity["type"],
                    "force": force,
                    "dependency_counts": dependency_counts,
                },
            )

        return {
            "deleted_entity": entity,
            "dependency_counts": dependency_counts,
            "force": force,
        }

    def merge_entities(
        self,
        source_entity_id: str,
        target_entity_id: str,
        attribute_conflict: str = "target_wins",
    ) -> dict[str, Any]:
        source_entity_id = _validate_identifier(source_entity_id, "source entity id")
        target_entity_id = _validate_identifier(target_entity_id, "target entity id")
        if source_entity_id == target_entity_id:
            raise ValidationError("source and target entity ids must be different")
        if attribute_conflict not in {"target_wins", "source_wins"}:
            raise ValidationError("attribute_conflict must be one of: target_wins, source_wins")

        source = self.get_entity(source_entity_id, include_related=False)
        target = self.get_entity(target_entity_id, include_related=False)
        if source["type"] != target["type"]:
            raise ValidationError(
                "merge requires matching entity types; "
                f"got {source['type']!r} and {target['type']!r}"
            )

        merged_name = target.get("name") or source.get("name")
        merged_description = target.get("description") or source.get("description")
        merged_status = target.get("status") or source.get("status")

        source_attributes = self._fetch_all(
            "SELECT key, value FROM attributes WHERE entity_id = ?",
            (source_entity_id,),
        )
        source_tags = self._fetch_all(
            "SELECT tag FROM tags WHERE entity_id = ?",
            (source_entity_id,),
        )
        outgoing = self._fetch_all(
            "SELECT to_entity, type FROM relationships WHERE from_entity = ?",
            (source_entity_id,),
        )
        incoming = self._fetch_all(
            "SELECT from_entity, type FROM relationships WHERE to_entity = ?",
            (source_entity_id,),
        )

        with self._transaction() as connection:
            connection.execute(
                "UPDATE entities SET name = ?, description = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (merged_name, merged_description, merged_status, target_entity_id),
            )

            if attribute_conflict == "target_wins":
                connection.executemany(
                    """
                    INSERT INTO attributes (entity_id, key, value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(entity_id, key) DO NOTHING
                    """,
                    [(target_entity_id, row["key"], row["value"]) for row in source_attributes],
                )
            else:
                connection.executemany(
                    """
                    INSERT INTO attributes (entity_id, key, value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(entity_id, key) DO UPDATE SET value = excluded.value
                    """,
                    [(target_entity_id, row["key"], row["value"]) for row in source_attributes],
                )

            if source_tags:
                connection.executemany(
                    "INSERT OR IGNORE INTO tags (entity_id, tag) VALUES (?, ?)",
                    [(target_entity_id, row["tag"]) for row in source_tags],
                )

            connection.execute(
                "UPDATE content SET entity_id = ? WHERE entity_id = ?",
                (target_entity_id, source_entity_id),
            )
            connection.execute(
                "INSERT OR IGNORE INTO snapshot_entities (snapshot_id, entity_id) "
                "SELECT snapshot_id, ? FROM snapshot_entities WHERE entity_id = ?",
                (target_entity_id, source_entity_id),
            )
            connection.execute(
                "DELETE FROM snapshot_entities WHERE entity_id = ?",
                (source_entity_id,),
            )
            connection.execute(
                "UPDATE events SET entity_id = ? WHERE entity_id = ?",
                (target_entity_id, source_entity_id),
            )

            rewired_outgoing = 0
            for row in outgoing:
                if row["to_entity"] == target_entity_id:
                    continue
                connection.execute(
                    "INSERT OR IGNORE INTO relationships (id, from_entity, to_entity, type) VALUES (?, ?, ?, ?)",
                    (_generated_id("rel"), target_entity_id, row["to_entity"], row["type"]),
                )
                rewired_outgoing += 1

            rewired_incoming = 0
            for row in incoming:
                if row["from_entity"] == target_entity_id:
                    continue
                connection.execute(
                    "INSERT OR IGNORE INTO relationships (id, from_entity, to_entity, type) VALUES (?, ?, ?, ?)",
                    (_generated_id("rel"), row["from_entity"], target_entity_id, row["type"]),
                )
                rewired_incoming += 1

            connection.execute(
                "DELETE FROM relationships WHERE from_entity = ? OR to_entity = ?",
                (source_entity_id, source_entity_id),
            )
            connection.execute("DELETE FROM entities WHERE id = ?", (source_entity_id,))
            self._touch_entity(connection, target_entity_id)
            self._record_event(
                connection,
                target_entity_id,
                "entity.merged",
                {
                    "source_entity_id": source_entity_id,
                    "target_entity_id": target_entity_id,
                    "attribute_conflict": attribute_conflict,
                    "rewired_outgoing": rewired_outgoing,
                    "rewired_incoming": rewired_incoming,
                },
            )

        return self.get_entity(target_entity_id, include_related=True)

    def find_similar_entities(
        self,
        name: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        normalized_name = _normalized_name(name)
        if not normalized_name:
            raise ValidationError("name must not be empty")

        limit = max(1, min(limit, 25))
        parameters: list[Any] = [f"%{normalized_name}%", f"%{normalized_name}%", f"%{normalized_name}%"]
        type_clause = ""
        if entity_type:
            type_clause = "AND e.type = ?"
            parameters.append(_validate_identifier(entity_type, "entity type"))

        candidates = self._fetch_all(
            f"""
            SELECT
                e.id,
                e.type,
                e.name,
                e.description,
                e.status,
                e.updated_at
            FROM entities e
            WHERE (
                LOWER(COALESCE(e.name, '')) LIKE ?
                OR LOWER(e.id) LIKE ?
                OR LOWER(COALESCE(e.description, '')) LIKE ?
            )
            {type_clause}
            ORDER BY e.updated_at DESC, e.id ASC
            LIMIT 100
            """,
            tuple(parameters),
        )

        scored: list[dict[str, Any]] = []
        for candidate in candidates:
            score = 0
            candidate_name = _normalized_name(candidate.get("name"))
            candidate_id = candidate["id"].lower()
            if candidate_name == normalized_name:
                score = 100
            elif candidate_id == normalized_name:
                score = 95
            elif normalized_name in candidate_name:
                score = 85
            elif normalized_name.replace(" ", "-") in candidate_id:
                score = 80
            elif normalized_name in _normalized_name(candidate.get("description")):
                score = 60

            if score > 0:
                enriched = dict(candidate)
                enriched["match_score"] = score
                scored.append(enriched)

        scored.sort(key=lambda item: (-item["match_score"], item.get("name") or item["id"], item["id"]))
        return scored[:limit]

    def resolve_entity_by_name(
        self,
        name: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        candidates = self.find_similar_entities(name=name, entity_type=entity_type, limit=limit)
        normalized_name = _normalized_name(name)
        exact_matches = [
            candidate
            for candidate in candidates
            if _normalized_name(candidate.get("name")) == normalized_name
        ]

        if len(exact_matches) == 1:
            entity_id = exact_matches[0]["id"]
            return {
                "match_type": "exact",
                "entity": self.get_entity(entity_id, include_related=True),
                "candidates": candidates,
            }

        if len(exact_matches) > 1:
            return {
                "match_type": "ambiguous",
                "entity": None,
                "candidates": exact_matches,
            }

        if candidates:
            return {
                "match_type": "candidate",
                "entity": None,
                "candidates": candidates,
            }

        return {
            "match_type": "none",
            "entity": None,
            "candidates": [],
        }

    def _generate_entity_id(self, entity_type: str, name: str) -> str:
        base = f"{entity_type}.{_slugify(name)}"
        candidate = base
        suffix = 2
        while self._entity_exists(candidate):
            candidate = f"{base}.{suffix}"
            suffix += 1
        return candidate

    def get_or_create_entity(
        self,
        entity_type: str,
        name: str,
        entity_id: str | None = None,
        description: str | None = None,
        status: str = "active",
        attributes: dict[str, str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        entity_type = _validate_identifier(entity_type, "entity type")
        normalized_name = _normalize_text(name)
        if normalized_name is None:
            raise ValidationError("name must not be empty")

        resolution = self.resolve_entity_by_name(normalized_name, entity_type=entity_type)
        if resolution["match_type"] == "exact":
            return {
                "created": False,
                "match_type": "exact",
                "entity": resolution["entity"],
            }
        if resolution["match_type"] == "ambiguous" and entity_id is None:
            raise ValidationError(
                "multiple exact-name entities already exist; provide an entity_id or merge duplicates before using get_or_create"
            )

        final_entity_id = _validate_identifier(entity_id, "entity id") if entity_id else self._generate_entity_id(entity_type, normalized_name)
        entity = self.upsert_entity(
            entity_id=final_entity_id,
            entity_type=entity_type,
            name=normalized_name,
            description=description,
            status=status,
            attributes=attributes,
            tags=tags,
        )
        return {
            "created": True,
            "match_type": resolution["match_type"],
            "entity": entity,
            "candidates": resolution["candidates"],
        }

    def get_database_health(self, limit: int = 25) -> dict[str, Any]:
        limit = max(1, min(limit, 100))

        duplicate_groups = self._fetch_all(
            """
            SELECT type, LOWER(TRIM(name)) AS normalized_name, COUNT(*) AS count
            FROM entities
            WHERE name IS NOT NULL AND TRIM(name) <> ''
            GROUP BY type, LOWER(TRIM(name))
            HAVING COUNT(*) > 1
            ORDER BY count DESC, type ASC, normalized_name ASC
            LIMIT ?
            """,
            (limit,),
        )
        duplicate_candidates = []
        for group in duplicate_groups:
            members = self._fetch_all(
                """
                SELECT id, type, name, status, updated_at
                FROM entities
                WHERE type = ? AND LOWER(TRIM(COALESCE(name, ''))) = ?
                ORDER BY updated_at DESC, id ASC
                """,
                (group["type"], group["normalized_name"]),
            )
            duplicate_candidates.append(
                {
                    "type": group["type"],
                    "normalized_name": group["normalized_name"],
                    "count": group["count"],
                    "entities": members,
                }
            )

        invalid_statuses = []
        for entity in self._fetch_all(
            "SELECT id, type, name, status FROM entities WHERE status IS NOT NULL ORDER BY updated_at DESC, id ASC"
        ):
            allowed_statuses = COMMON_STATUS_VOCABULARY["*"] | COMMON_STATUS_VOCABULARY.get(entity["type"], set())
            if entity["status"] not in allowed_statuses:
                invalid_statuses.append(
                    {
                        "id": entity["id"],
                        "type": entity["type"],
                        "name": entity["name"],
                        "status": entity["status"],
                        "allowed_statuses": sorted(allowed_statuses),
                    }
                )
                if len(invalid_statuses) >= limit:
                    break

        malformed_entities = []
        for entity in self._fetch_all("SELECT id, type, status FROM entities ORDER BY updated_at DESC, id ASC"):
            issues = []
            if not IDENTIFIER_RE.fullmatch(entity["id"]):
                issues.append("invalid_entity_id")
            if not IDENTIFIER_RE.fullmatch(entity["type"]):
                issues.append("invalid_entity_type")
            if entity["status"] and not IDENTIFIER_RE.fullmatch(entity["status"]):
                issues.append("invalid_status")
            if issues:
                malformed_entities.append({"id": entity["id"], "issues": issues})
                if len(malformed_entities) >= limit:
                    break

        low_quality_attributes = self._fetch_all(
            """
            SELECT entity_id, key, value
            FROM attributes
            WHERE LOWER(TRIM(value)) IN ('?', 'n/a', 'none', 'temp', 'tbd', 'todo', 'unknown')
            ORDER BY entity_id ASC, key ASC
            LIMIT ?
            """,
            (limit,),
        )

        attribute_namespace_issues = self._fetch_all(
            f"""
            SELECT entity_id, key, value
            FROM attributes
            WHERE instr(key, '.') = 0
              AND key NOT IN ({", ".join('?' for _ in sorted(COMMON_ATTRIBUTE_KEYS))})
            ORDER BY entity_id ASC, key ASC
            LIMIT ?
            """,
            (*sorted(COMMON_ATTRIBUTE_KEYS), limit),
        )

        broken_references = {
            "content": self._fetch_all(
                """
                SELECT c.id, c.entity_id
                FROM content c
                LEFT JOIN entities e ON e.id = c.entity_id
                WHERE e.id IS NULL
                LIMIT ?
                """,
                (limit,),
            ),
            "tags": self._fetch_all(
                """
                SELECT t.entity_id, t.tag
                FROM tags t
                LEFT JOIN entities e ON e.id = t.entity_id
                WHERE e.id IS NULL
                LIMIT ?
                """,
                (limit,),
            ),
            "relationships": self._fetch_all(
                """
                SELECT r.id, r.from_entity, r.to_entity, r.type
                FROM relationships r
                LEFT JOIN entities ef ON ef.id = r.from_entity
                LEFT JOIN entities et ON et.id = r.to_entity
                WHERE ef.id IS NULL OR et.id IS NULL
                LIMIT ?
                """,
                (limit,),
            ),
        }

        high_volume_content = self._fetch_all(
            """
            SELECT entity_id, content_type, COUNT(*) AS count
            FROM content
            WHERE content_type IN ('log', 'reasoning')
            GROUP BY entity_id, content_type
            HAVING COUNT(*) > 20
            ORDER BY count DESC, entity_id ASC
            LIMIT ?
            """,
            (limit,),
        )

        issue_counts = {
            "duplicate_candidates": len(duplicate_candidates),
            "invalid_statuses": len(invalid_statuses),
            "malformed_entities": len(malformed_entities),
            "low_quality_attributes": len(low_quality_attributes),
            "attribute_namespace_issues": len(attribute_namespace_issues),
            "broken_content_references": len(broken_references["content"]),
            "broken_tag_references": len(broken_references["tags"]),
            "broken_relationship_references": len(broken_references["relationships"]),
            "high_volume_content": len(high_volume_content),
        }

        return {
            "healthy": all(count == 0 for count in issue_counts.values()),
            "issue_counts": issue_counts,
            "duplicate_candidates": duplicate_candidates,
            "invalid_statuses": invalid_statuses,
            "malformed_entities": malformed_entities,
            "low_quality_attributes": low_quality_attributes,
            "attribute_namespace_issues": attribute_namespace_issues,
            "broken_references": broken_references,
            "high_volume_content": high_volume_content,
            "retention_policy": {
                "content_types": sorted(RETENTION_CONTENT_TYPES),
                "recommended_keep_latest": RETAIN_LATEST_CONTENT_COUNT,
            },
        }

    def prune_content_retention(
        self,
        content_types: list[str] | None = None,
        keep_latest: int = 20,
        entity_id: str | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        keep_latest = max(1, min(keep_latest, 500))
        selected_types = sorted(
            {
                _validate_identifier(content_type, "content type")
                for content_type in (content_types or sorted(RETENTION_CONTENT_TYPES))
            }
        )
        if not selected_types:
            raise ValidationError("at least one content type must be provided")

        entity_clause = ""
        parameters: list[Any] = [*selected_types, keep_latest]
        if entity_id is not None:
            normalized_entity_id = _validate_identifier(entity_id, "entity id")
            entity_clause = "AND entity_id = ?"
            parameters.append(normalized_entity_id)

        placeholders = ", ".join("?" for _ in selected_types)
        candidates = self._fetch_all(
            f"""
            SELECT id, entity_id, content_type, created_at
            FROM (
                SELECT
                    id,
                    entity_id,
                    content_type,
                    created_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY entity_id, content_type
                        ORDER BY created_at DESC, id DESC
                    ) AS row_number
                FROM content
                WHERE content_type IN ({placeholders})
                {entity_clause}
            ) ranked
            WHERE row_number > ?
            ORDER BY entity_id ASC, content_type ASC, created_at DESC, id DESC
            """,
            tuple(parameters),
        )

        if dry_run or not candidates:
            return {
                "dry_run": dry_run,
                "keep_latest": keep_latest,
                "content_types": selected_types,
                "entity_id": entity_id,
                "delete_count": len(candidates),
                "candidates": candidates,
            }

        deleted_ids = [candidate["id"] for candidate in candidates]
        entities_touched = sorted({candidate["entity_id"] for candidate in candidates})
        with self._transaction() as connection:
            connection.executemany(
                "DELETE FROM content WHERE id = ?",
                [(content_id,) for content_id in deleted_ids],
            )
            for touched_entity_id in entities_touched:
                self._touch_entity(connection, touched_entity_id)
                self._record_event(
                    connection,
                    touched_entity_id,
                    "content.pruned",
                    {
                        "content_types": selected_types,
                        "keep_latest": keep_latest,
                    },
                )

        return {
            "dry_run": False,
            "keep_latest": keep_latest,
            "content_types": selected_types,
            "entity_id": entity_id,
            "delete_count": len(candidates),
            "deleted_content_ids": deleted_ids,
            "entities_touched": entities_touched,
        }

    def get_recent_activity(self, limit: int = 20, offset: int = 0, compact: bool = False) -> dict[str, Any]:
        limit = _bounded_limit(limit, maximum=100)
        offset = _bounded_offset(offset)

        total_events = (self._fetch_one("SELECT COUNT(*) AS count FROM events") or {"count": 0})["count"]
        total_entities = (self._fetch_one("SELECT COUNT(*) AS count FROM entities") or {"count": 0})["count"]
        total_content = (self._fetch_one("SELECT COUNT(*) AS count FROM content") or {"count": 0})["count"]

        recent_events = self._fetch_all(
            """
            SELECT id, entity_id, event_type, data, created_at
            FROM events
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        recent_entities = self._fetch_all(
            """
            SELECT id, type, name, status, updated_at
            FROM entities
            ORDER BY updated_at DESC, id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        recent_content = self._fetch_all(
            """
            SELECT id, entity_id, content_type, created_at
            FROM content
            ORDER BY created_at DESC, id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )

        return _summary_envelope(
            "recent_activity.v1",
            {
                "limit": limit,
                "offset": offset,
                "recent_events": recent_events,
                "recent_entities": recent_entities,
                "recent_content": recent_content,
                "event_total_count": total_events,
                "entity_total_count": total_entities,
                "content_total_count": total_content,
                "has_more_events": offset + len(recent_events) < total_events,
                "has_more_entities": offset + len(recent_entities) < total_entities,
                "has_more_content": offset + len(recent_content) < total_content,
            },
            compact=compact,
        )

    def execute_read_query(
        self,
        sql: str,
        parameters: list[Any] | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        normalized_sql = sql.strip()
        if not normalized_sql:
            raise ValidationError("sql must not be empty")

        lowered = normalized_sql.lower()
        first_keyword = lowered.split(None, 1)[0]
        allowed_keywords = {"select", "with", "pragma", "explain"}
        if first_keyword not in allowed_keywords:
            raise ValidationError("only read-only SELECT, WITH, PRAGMA, and EXPLAIN queries are allowed")

        forbidden_tokens = {
            "insert ",
            "update ",
            "delete ",
            "drop ",
            "alter ",
            "create ",
            "replace ",
            "attach ",
            "detach ",
            "vacuum",
            "reindex",
            "pragma writable_schema",
        }
        if any(token in lowered for token in forbidden_tokens):
            raise ValidationError("query contains a forbidden token for the read-only SQL tool")

        if ";" in normalized_sql.rstrip(";"):
            raise ValidationError("multiple SQL statements are not allowed")

        query_limit = max(1, min(limit, 1000))
        query_parameters = tuple(parameters or [])

        with self._lock:
            if self._connection is None:
                raise RuntimeError("database connection has not been initialized")
            cursor = self._connection.execute(normalized_sql, query_parameters)
            columns = [description[0] for description in cursor.description or []]
            rows = cursor.fetchmany(query_limit)

        serialized_rows = [dict(row) if isinstance(row, sqlite3.Row) else row for row in rows]
        return {
            "sql": normalized_sql,
            "parameters": list(query_parameters),
            "columns": columns,
            "rows": serialized_rows,
            "row_count": len(serialized_rows),
            "limit": query_limit,
        }

    def bootstrap_project_memory(
        self,
        project_id: str,
        project_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        project_id = _validate_identifier(project_id, "project id")
        normalized_name = _normalize_text(project_name)
        if normalized_name is None:
            raise ValidationError("project name must not be empty")

        anchors = [
            (f"{project_id}.roadmap", "roadmap", "Roadmap", "active"),
            (f"{project_id}.architecture", "architecture", "Architecture", "active"),
            (f"{project_id}.plan", "plan", "Active Plan", "active"),
            (f"{project_id}.todo", "todo", "Todo", "active"),
            (f"{project_id}.notes", "notes", "Notes", "active"),
            (f"{project_id}.decisions", "decision_log", "Decision Log", "active"),
        ]

        project = self.upsert_entity(
            entity_id=project_id,
            entity_type="project",
            name=normalized_name,
            description=description,
            status="active",
            attributes={"memory_model": "graph_relational", "source_of_truth": "sqlite"},
            tags=sorted({*(tags or []), "project-memory"}),
        )

        created_anchors: list[dict[str, Any]] = []
        for entity_id, entity_type, name, status in anchors:
            anchor = self.upsert_entity(
                entity_id=entity_id,
                entity_type=entity_type,
                name=name,
                status=status,
            )
            created_anchors.append(anchor)
            self.connect_entities(
                from_entity=project_id,
                to_entity=entity_id,
                relationship_type="has_memory_area",
            )

        return {
            "project": project,
            "memory_areas": created_anchors,
        }

    def _validate_view_generation_request(self, user_requested: bool, request_reason: str | None) -> str:
        if not user_requested:
            raise ValidationError(
                "markdown view generation is locked; only generate views after an explicit user request and pass user_requested=True"
            )
        normalized_reason = _normalize_text(request_reason)
        if normalized_reason is None or len(normalized_reason) < 12:
            raise ValidationError(
                "request_reason must describe the user's explicit request and be at least 12 characters long"
            )
        return normalized_reason

    def _render_markdown_views_internal(self, view_names: list[str] | None = None) -> dict[str, str]:
        requested = view_names or [
            "overview",
            "todo",
            "roadmap",
            "architecture",
            "decisions",
            "plan",
            "notes",
        ]
        unique_requested = []
        for view_name in requested:
            normalized = view_name.strip().lower()
            if normalized and normalized not in unique_requested:
                unique_requested.append(normalized)

        renderers = {
            "overview": self._render_overview_view,
            "todo": self._render_todo_view,
            "roadmap": self._render_roadmap_view,
            "architecture": self._render_architecture_view,
            "decisions": self._render_decisions_view,
            "plan": self._render_plan_view,
            "notes": self._render_notes_view,
        }

        unsupported = [view_name for view_name in unique_requested if view_name not in renderers]
        if unsupported:
            raise ValidationError(f"unsupported view names: {', '.join(sorted(unsupported))}")

        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        return {
            f"{view_name}.md": self._wrap_markdown_view(
                view_name=view_name,
                generated_at=generated_at,
                body=renderers[view_name](),
            )
            for view_name in unique_requested
        }

    def render_markdown_views(
        self,
        view_names: list[str] | None = None,
        *,
        user_requested: bool = False,
        request_reason: str | None = None,
    ) -> dict[str, str]:
        self._validate_view_generation_request(
            user_requested=user_requested,
            request_reason=request_reason,
        )
        return self._render_markdown_views_internal(view_names=view_names)

    def export_markdown_views(
        self,
        output_dir: Path | str,
        view_names: list[str] | None = None,
        overwrite: bool = False,
        require_existing_dir: bool = False,
        user_requested: bool = False,
        request_reason: str | None = None,
    ) -> dict[str, Any]:
        export_dir = Path(output_dir).expanduser().resolve()
        if export_dir.exists() and not export_dir.is_dir():
            raise ValidationError(f"output_dir must be a directory; got file path {str(export_dir)!r}")
        if require_existing_dir and not export_dir.exists():
            raise ValidationError(
                f"output_dir must already exist when require_existing_dir=True; got {str(export_dir)!r}"
            )

        normalized_reason = self._validate_view_generation_request(
            user_requested=user_requested,
            request_reason=request_reason,
        )
        rendered = self._render_markdown_views_internal(view_names=view_names)
        targets = {file_name: export_dir / file_name for file_name in rendered}
        existing_files = [str(target) for target in targets.values() if target.exists()]
        if existing_files and not overwrite:
            raise ValidationError(
                "refusing to overwrite existing exported view files without overwrite=True: "
                + ", ".join(sorted(existing_files))
            )

        export_dir.mkdir(parents=True, exist_ok=True)
        written_files: list[str] = []
        for file_name, body in rendered.items():
            target = targets[file_name]
            target.write_text(body + ("\n" if not body.endswith("\n") else ""), encoding="utf-8")
            written_files.append(str(target))

        return {
            "output_dir": str(export_dir),
            "view_count": len(written_files),
            "written_files": written_files,
            "overwritten_files": sorted(existing_files),
            "overwrite": overwrite,
            "request_reason": normalized_reason,
        }

    def _wrap_markdown_view(self, view_name: str, generated_at: str, body: str) -> str:
        descriptions = {
            "overview": "Generated project memory overview from the SQLite source of truth.",
            "todo": "Generated task backlog grouped from the SQLite source of truth.",
            "roadmap": "Generated roadmap summary derived from structured SQLite project memory.",
            "architecture": "Generated architecture summary derived from structured SQLite project memory.",
            "decisions": "Generated decision log derived from structured SQLite project memory.",
            "plan": "Generated implementation plan derived from structured SQLite project memory.",
            "notes": "Generated note and narrative summary derived from SQLite project memory.",
        }
        header_lines = [
            "<!-- Generated file: do not edit manually. -->",
            "<!-- Non-authoritative generated view: use SQLite/MCP reads for current project state. -->",
            "<!-- Generate only after an explicit user request; do not use this file in place of the database. -->",
            f"<!-- Description: {descriptions[view_name]} -->",
            f"<!-- Generated at: {generated_at} -->",
            "",
        ]
        return "\n".join(header_lines) + body.lstrip()

    def _memory_area(self, target: str) -> dict[str, Any] | None:
        config = DOCUMENT_TARGETS[target]
        return self._fetch_one(
            """
            SELECT DISTINCT e.id, e.type, e.name, e.description, e.status, e.updated_at
            FROM entities e
            LEFT JOIN relationships r ON r.to_entity = e.id AND r.type = 'has_memory_area'
            LEFT JOIN entities p ON p.id = r.from_entity AND p.type = 'project'
            WHERE e.type = ?
            ORDER BY CASE WHEN p.id IS NOT NULL THEN 0 ELSE 1 END, e.updated_at DESC, e.id ASC
            LIMIT 1
            """,
            (config["entity_type"],),
        )

    def _memory_area_document(self, target: str) -> dict[str, Any] | None:
        anchor = self._memory_area(target)
        if anchor is None:
            return None
        config = DOCUMENT_TARGETS[target]
        document = self._fetch_one(
            "SELECT id, content_type, body, created_at FROM content WHERE id = ? AND entity_id = ?",
            (config["content_id"], anchor["id"]),
        )
        if document is not None:
            return document
        return self._fetch_one(
            """
            SELECT id, content_type, body, created_at
            FROM content
            WHERE entity_id = ? AND content_type IN ('spec', 'analysis', 'note')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (anchor["id"],),
        )

    def _append_document_section(
        self,
        lines: list[str],
        heading: str,
        document: dict[str, Any] | None,
        empty_message: str,
    ) -> None:
        lines.append(f"## {heading}")
        lines.append("")
        if document is None or not document.get("body"):
            lines.append(f"- {empty_message}")
            lines.append("")
            return
        lines.extend(document["body"].strip().splitlines())
        lines.append("")

    def _render_overview_view(self) -> str:
        overview = self.get_project_overview()
        lines = ["# Project Memory Overview", ""]
        lines.append(f"- Database: {overview['database_path']}")
        lines.append(f"- FTS enabled: {'yes' if overview['fts_enabled'] else 'no'}")
        lines.append(f"- Snapshots: {overview['snapshot_count']['count']}")
        lines.append("")
        lines.append("## Entity Counts By Type")
        lines.append("")
        for row in overview["entity_counts_by_type"]:
            lines.append(f"- {row['type']}: {row['count']}")
        if not overview["entity_counts_by_type"]:
            lines.append("- No entities recorded.")
        lines.append("")
        lines.append("## Top Tags")
        lines.append("")
        for row in overview["top_tags"]:
            lines.append(f"- {row['tag']}: {row['count']}")
        if not overview["top_tags"]:
            lines.append("- No tags recorded.")
        lines.append("")
        lines.append("## Recent Events")
        lines.append("")
        for event in overview["recent_events"][:10]:
            lines.append(f"- {event['created_at']} {event['event_type']} {event['entity_id'] or 'global'}")
        if not overview["recent_events"]:
            lines.append("- No events recorded.")
        lines.append("")
        return "\n".join(lines)

    def _render_todo_view(self) -> str:
        tasks = self._fetch_all(
            """
            SELECT
                e.id,
                e.name,
                e.status,
                e.updated_at,
                MAX(CASE WHEN a.key = 'phase_number' THEN a.value END) AS phase_number,
                MAX(CASE WHEN a.key = 'priority' THEN a.value END) AS priority,
                MAX(CASE WHEN a.key = 'owner' THEN a.value END) AS owner
            FROM entities e
            LEFT JOIN attributes a ON a.entity_id = e.id
            WHERE e.type IN ('task', 'todo', 'bug')
                            AND COALESCE(e.status, '') != 'archived'
              AND NOT EXISTS (
                  SELECT 1 FROM relationships mr
                  WHERE mr.to_entity = e.id AND mr.type = 'has_memory_area'
              )
            GROUP BY e.id, e.name, e.status, e.updated_at
            ORDER BY
                CASE
                    WHEN MAX(CASE WHEN a.key = 'phase_number' THEN a.value END) GLOB '[0-9]*'
                    THEN CAST(MAX(CASE WHEN a.key = 'phase_number' THEN a.value END) AS INTEGER)
                    ELSE 9999
                END,
                CASE COALESCE(MAX(CASE WHEN a.key = 'priority' THEN a.value END), '')
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                    ELSE 5
                END,
                e.updated_at DESC,
                e.id ASC
            """
        )
        lines = ["# Todo", "", "Source of truth: SQLite project memory.", ""]
        if not tasks:
            lines.append("- No task-like entities recorded.")
            lines.append("")
            return "\n".join(lines)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for task in tasks:
            phase_number = task.get("phase_number") or "unassigned"
            grouped.setdefault(phase_number, []).append(task)

        sorted_phase_keys = sorted(
            grouped,
            key=lambda value: (9999 if not str(value).isdigit() else int(value), str(value)),
        )
        for phase_key in sorted_phase_keys:
            if phase_key == "unassigned":
                lines.append("## Unassigned")
            else:
                lines.append(f"## Phase {phase_key}")
            lines.append("")
            for task in grouped[phase_key]:
                title = task["name"] or task["id"]
                meta = [f"status={task['status'] or 'unknown'}"]
                if task.get("priority"):
                    meta.append(f"priority={task['priority']}")
                if task.get("owner"):
                    meta.append(f"owner={task['owner']}")
                lines.append(f"- {title} ({', '.join(meta)})")
            lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _render_roadmap_view(self) -> str:
        roadmap_sections = [
            ("Goal", "roadmap-section.goal"),
            ("Current State", "roadmap-section.current-state"),
            ("Design Constraints", "roadmap-section.design-constraints"),
            ("Architectural Direction", "roadmap-section.architectural-direction"),
            ("Completed Foundations", "roadmap-section.completed-foundations"),
            ("Completed AI Read Models", "roadmap-section.completed-ai-read-models"),
            ("Recommended Build Order", "roadmap-section.recommended-build-order"),
            ("Definition Of Done", "roadmap-section.definition-of-done"),
        ]
        decisions = self._fetch_all(
            """
            SELECT e.id, e.name, e.status, e.description
            FROM entities e
            WHERE e.type = 'decision'
                            AND COALESCE(e.status, '') != 'archived'
              AND EXISTS (SELECT 1 FROM tags t WHERE t.entity_id = e.id AND t.tag = 'open-decision')
            ORDER BY e.name ASC, e.id ASC
            """
        )
        phases = self._fetch_all(
            """
            SELECT
                e.id,
                e.type,
                e.name,
                e.status,
                e.description,
                e.updated_at,
                MAX(CASE WHEN a.key = 'phase_number' THEN a.value END) AS phase_number
            FROM entities e
            LEFT JOIN attributes a ON a.entity_id = e.id
            WHERE e.type = 'phase'
                            AND COALESCE(e.status, '') != 'archived'
            GROUP BY e.id, e.type, e.name, e.status, e.description, e.updated_at
            ORDER BY
                CASE
                    WHEN MAX(CASE WHEN a.key = 'phase_number' THEN a.value END) GLOB '[0-9]*'
                    THEN CAST(MAX(CASE WHEN a.key = 'phase_number' THEN a.value END) AS INTEGER)
                    ELSE 9999
                END,
                e.id ASC
            """
        )
        lines = ["# Roadmap", ""]
        if not phases and not decisions:
            lines.append("- No roadmap-style entities recorded.")
            lines.append("")
            return "\n".join(lines)

        for heading, content_id in roadmap_sections:
            content = self._fetch_one(
                "SELECT body FROM content WHERE id = ?",
                (content_id,),
            )
            if not content or not content.get("body"):
                continue
            lines.append(f"## {heading}")
            lines.append("")
            lines.extend(content["body"].splitlines())
            lines.append("")

        if decisions:
            lines.append("## Open Decisions")
            lines.append("")
            for decision in decisions:
                title = decision["name"] or decision["id"]
                description = f": {decision['description']}" if decision.get("description") else ""
                lines.append(f"- {title} ({decision['status'] or 'unknown'}){description}")
            lines.append("")

        for phase in phases:
            phase_number = phase.get("phase_number") or "?"
            title = phase["name"] or phase["id"]
            lines.append(f"## Phase {phase_number}: {title.split(': ', 1)[-1]}")
            lines.append("")
            lines.append(f"- Status: {phase['status'] or 'unknown'}")
            if phase.get("description"):
                lines.append(f"- Objective: {phase['description']}")

            spec = self._fetch_one(
                """
                SELECT body
                FROM content
                WHERE entity_id = ? AND content_type = 'spec'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (phase["id"],),
            )
            if spec and spec.get("body"):
                lines.append("- Acceptance Criteria:")
                for item in spec["body"].splitlines():
                    if item.strip():
                        lines.append(f"  {item}")

            tasks = self._fetch_all(
                """
                SELECT e.id, e.name, e.status, e.description
                FROM relationships r
                JOIN entities e ON e.id = r.to_entity
                WHERE r.from_entity = ? AND r.type = 'contains' AND e.type = 'task'
                ORDER BY e.name ASC, e.id ASC
                """,
                (phase["id"],),
            )
            lines.append("")
            lines.append("### Tasks")
            lines.append("")
            if not tasks:
                lines.append("- No tasks recorded.")
            else:
                for task in tasks:
                    description = f": {task['description']}" if task.get("description") else ""
                    lines.append(f"- {task['name'] or task['id']} ({task['status'] or 'unknown'}){description}")
            lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _render_architecture_view(self) -> str:
        summary = self.get_architecture_summary(node_limit=40, relationship_limit=60)
        document = self._memory_area_document("architecture")
        lines = ["# Architecture", "", "Source of truth: SQLite project memory.", ""]
        self._append_document_section(
            lines,
            "Current Architecture Document",
            document,
            "No architecture document content has been synced yet.",
        )
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Nodes: {summary['node_count']}")
        lines.append(f"- Relationships: {summary['relationship_count']}")
        for node_type in summary["node_types"]:
            lines.append(f"- {node_type['type']}: {node_type['count']}")
        lines.append("")
        lines.append("## Key Nodes")
        lines.append("")
        if not summary["nodes"]:
            lines.append("- No architecture-like entities recorded.")
        for node in summary["nodes"]:
            title = node["name"] or node["id"]
            lines.append(f"- [{node['type']}] {title} ({node['status'] or 'unknown'})")
        lines.append("")
        lines.append("## Key Relationships")
        lines.append("")
        if not summary["relationships"]:
            lines.append("- No architecture-like relationships recorded.")
        for edge in summary["relationships"]:
            lines.append(f"- {edge['from_entity']} -[{edge['type']}]-> {edge['to_entity']}")
        lines.append("")
        return "\n".join(lines)

    def _render_decisions_view(self) -> str:
        summary = self.get_decision_log(limit=50)
        document = self._memory_area_document("decisions")
        decisions = [item for item in summary["items"] if item["type"] == "decision" and item["status"] != "archived"]
        lines = ["# Decisions", "", "Source of truth: SQLite project memory.", ""]
        self._append_document_section(
            lines,
            "Current Decision Document",
            document,
            "No decision document content has been synced yet.",
        )
        if not decisions:
            lines.append("- No decision entities recorded.")
            lines.append("")
            return "\n".join(lines)
        by_status: dict[str, list[dict[str, Any]]] = {}
        for decision in decisions:
            by_status.setdefault(decision["status"] or "unknown", []).append(decision)
        for status in sorted(by_status):
            lines.append(f"## {status.title().replace('_', ' ')}")
            lines.append("")
            for decision in by_status[status]:
                title = decision["name"] or decision["id"]
                lines.append(f"### {title}")
                lines.append("")
                if decision.get("description"):
                    lines.append(decision["description"])
                    lines.append("")
                if decision.get("latest_note"):
                    lines.append(f"- Latest note: {decision['latest_note']}")
                if decision.get("latest_note_at"):
                    lines.append(f"- Latest note at: {decision['latest_note_at']}")
                lines.append("")
        return "\n".join(lines)

    def _render_plan_view(self) -> str:
        document = self._memory_area_document("plan")
        open_tasks = self.get_open_tasks(limit=50)["items"]
        lines = ["# Plan", "", "Source of truth: SQLite project memory.", ""]
        self._append_document_section(
            lines,
            "Current Plan Document",
            document,
            "No plan document content has been synced yet.",
        )
        lines.append("## Prioritized Open Work")
        lines.append("")
        if not open_tasks:
            lines.append("- No open task-like entities recorded.")
            lines.append("")
            return "\n".join(lines)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for task in open_tasks:
            phase_number = task.get("phase_number") or "unassigned"
            grouped.setdefault(phase_number, []).append(task)
        for phase_key in sorted(grouped, key=lambda value: (9999 if not str(value).isdigit() else int(value), str(value))):
            if phase_key == "unassigned":
                lines.append("### Unassigned")
            else:
                lines.append(f"### Phase {phase_key}")
            lines.append("")
            for task in grouped[phase_key]:
                title = task["name"] or task["id"]
                meta = [f"status={task['status'] or 'unknown'}"]
                if task.get("priority"):
                    meta.append(f"priority={task['priority']}")
                if task.get("owner"):
                    meta.append(f"owner={task['owner']}")
                if task.get("dependency_count"):
                    meta.append(f"dependencies={task['dependency_count']}")
                if task.get("blocker_count"):
                    meta.append(f"blocked_by={task['blocker_count']}")
                lines.append(f"- {title} ({', '.join(meta)})")
            lines.append("")
        return "\n".join(lines)

    def _render_notes_view(self) -> str:
        document = self._memory_area_document("notes")
        protected_ids = tuple(config["content_id"] for config in DOCUMENT_TARGETS.values())
        placeholders = ", ".join("?" for _ in protected_ids)
        notes = self._fetch_all(
            f"""
            SELECT c.id, c.entity_id, c.content_type, c.body, c.created_at, e.name AS entity_name
            FROM content c
            JOIN entities e ON e.id = c.entity_id
            WHERE c.content_type IN ('note', 'analysis', 'reasoning', 'log', 'spec')
              AND c.id NOT IN ({placeholders})
            ORDER BY c.created_at DESC, c.id ASC
            LIMIT 24
            """,
            protected_ids,
        )
        lines = ["# Notes", "", "Source of truth: SQLite project memory.", ""]
        self._append_document_section(
            lines,
            "Current Notes Document",
            document,
            "No notes document content has been synced yet.",
        )
        lines.append("## Recent Narrative Entries")
        lines.append("")
        if not notes:
            lines.append("- No note-like content recorded.")
            lines.append("")
            return "\n".join(lines)
        for note in notes:
            label = note["entity_name"] or note["entity_id"]
            lines.append(f"### {label} [{note['content_type']}]")
            lines.append("")
            body = note["body"].strip()
            if len(body) > 400:
                body = body[:397].rstrip() + "..."
            lines.append(body)
            lines.append("")
        return "\n".join(lines)

    def get_entity_graph(
        self,
        entity_id: str,
        max_depth: int = 2,
        relationship_type: str | None = None,
        edge_limit: int = 200,
        node_limit: int = 250,
        compact: bool = False,
    ) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        max_depth = _bounded_limit(max_depth, maximum=8)
        edge_limit = _bounded_limit(edge_limit, maximum=500)
        node_limit = _bounded_limit(node_limit, maximum=500)

        if relationship_type:
            relationship_type = _validate_relationship_type(relationship_type)
            type_clause = "AND r.type = ?"
            parameters: tuple[Any, ...] = (entity_id, relationship_type, max_depth)
        else:
            type_clause = ""
            parameters = (entity_id, max_depth)

        raw_edges = self._fetch_all(
            f"""
            WITH RECURSIVE graph(depth, id, from_entity, to_entity, type, created_at) AS (
                SELECT 1, r.id, r.from_entity, r.to_entity, r.type, r.created_at
                FROM relationships r
                WHERE r.from_entity = ? {type_clause}

                UNION ALL

                SELECT graph.depth + 1, r.id, r.from_entity, r.to_entity, r.type, r.created_at
                FROM relationships r
                JOIN graph ON r.from_entity = graph.to_entity
                WHERE graph.depth < ? {type_clause}
            )
            SELECT DISTINCT * FROM graph ORDER BY depth, id
            LIMIT ?
            """,
            (*parameters, edge_limit + 1)
            if relationship_type is None
            else (entity_id, relationship_type, max_depth, relationship_type, edge_limit + 1),
        )
        has_more_edges = len(raw_edges) > edge_limit
        edges = raw_edges[:edge_limit]

        node_ids = {entity_id}
        for edge in edges:
            node_ids.add(edge["from_entity"])
            node_ids.add(edge["to_entity"])

        placeholders = ", ".join("?" for _ in node_ids)
        raw_nodes = self._fetch_all(
            f"SELECT * FROM entities WHERE id IN ({placeholders}) ORDER BY type, id LIMIT ?",
            (*tuple(sorted(node_ids)), node_limit + 1),
        )
        has_more_nodes = len(raw_nodes) > node_limit
        nodes = raw_nodes[:node_limit]

        return _summary_envelope(
            "entity_graph.v1",
            {
                "root": self.get_entity(entity_id, include_related=False),
                "depth": max_depth,
                "relationship_type": relationship_type,
                "edge_limit": edge_limit,
                "node_limit": node_limit,
                "has_more_edges": has_more_edges,
                "has_more_nodes": has_more_nodes,
                "node_count": len(nodes),
                "relationship_count": len(edges),
                "nodes": nodes,
                "relationships": edges,
            },
            compact=compact,
        )
