from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,127}$")
ATTRIBUTE_KEY_RE = re.compile(r"^[a-z][a-z0-9._:-]{1,63}$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")


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


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _generated_id(prefix: str) -> str:
    return f"{prefix}.{uuid4().hex[:12]}"


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
    def _transaction(self) -> sqlite3.Connection:
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

        self._initialize_fts()

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
            },
        }

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
        relationship_type = _validate_identifier(relationship_type, "relationship type")

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
        relationship_type = _validate_identifier(relationship_type, "relationship type")

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
            parameters.append(_validate_identifier(relationship_type, "relationship type"))

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

    def get_recent_activity(self, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(limit, 100))
        return {
            "recent_events": self._fetch_all(
                """
                SELECT id, entity_id, event_type, data, created_at
                FROM events
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ),
            "recent_entities": self._fetch_all(
                """
                SELECT id, type, name, status, updated_at
                FROM entities
                ORDER BY updated_at DESC, id ASC
                LIMIT ?
                """,
                (limit,),
            ),
            "recent_content": self._fetch_all(
                """
                SELECT id, entity_id, content_type, created_at
                FROM content
                ORDER BY created_at DESC, id ASC
                LIMIT ?
                """,
                (limit,),
            ),
        }

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

    def render_markdown_views(self, view_names: list[str] | None = None) -> dict[str, str]:
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

        return {f"{view_name}.md": renderers[view_name]() for view_name in unique_requested}

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
                MAX(CASE WHEN a.key = 'priority' THEN a.value END) AS priority,
                MAX(CASE WHEN a.key = 'owner' THEN a.value END) AS owner
            FROM entities e
            LEFT JOIN attributes a ON a.entity_id = e.id
            WHERE e.type IN ('task', 'todo', 'bug')
            GROUP BY e.id, e.name, e.status, e.updated_at
            ORDER BY
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
        for task in tasks:
            title = task["name"] or task["id"]
            meta = [f"status={task['status'] or 'unknown'}"]
            if task.get("priority"):
                meta.append(f"priority={task['priority']}")
            if task.get("owner"):
                meta.append(f"owner={task['owner']}")
            lines.append(f"- {title} ({', '.join(meta)})")
        lines.append("")
        return "\n".join(lines)

    def _render_roadmap_view(self) -> str:
        items = self._fetch_all(
            """
            SELECT e.id, e.type, e.name, e.status, e.description, e.updated_at
            FROM entities e
            WHERE e.type IN ('roadmap', 'milestone', 'feature', 'epic', 'release')
               OR EXISTS (SELECT 1 FROM tags t WHERE t.entity_id = e.id AND t.tag = 'roadmap')
            ORDER BY e.updated_at DESC, e.id ASC
            """
        )
        lines = ["# Roadmap", ""]
        if not items:
            lines.append("- No roadmap-style entities recorded.")
            lines.append("")
            return "\n".join(lines)
        for item in items:
            title = item["name"] or item["id"]
            description = f": {item['description']}" if item.get("description") else ""
            lines.append(f"- [{item['type']}] {title} ({item['status'] or 'unknown'}){description}")
        lines.append("")
        return "\n".join(lines)

    def _render_architecture_view(self) -> str:
        nodes = self._fetch_all(
            """
            SELECT id, type, name, description, status
            FROM entities
            WHERE type IN ('architecture', 'module', 'component', 'service', 'file')
            ORDER BY type ASC, id ASC
            LIMIT 200
            """
        )
        edges = self._fetch_all(
            """
            SELECT from_entity, to_entity, type
            FROM relationships
            WHERE type IN ('depends_on', 'implements', 'calls', 'owns', 'contains')
            ORDER BY type ASC, from_entity ASC, to_entity ASC
            LIMIT 300
            """
        )
        lines = ["# Architecture", ""]
        lines.append("## Nodes")
        lines.append("")
        if not nodes:
            lines.append("- No architecture-like entities recorded.")
        for node in nodes:
            title = node["name"] or node["id"]
            lines.append(f"- [{node['type']}] {title} ({node['status'] or 'unknown'})")
        lines.append("")
        lines.append("## Relationships")
        lines.append("")
        if not edges:
            lines.append("- No architecture-like relationships recorded.")
        for edge in edges:
            lines.append(f"- {edge['from_entity']} -[{edge['type']}]-> {edge['to_entity']}")
        lines.append("")
        return "\n".join(lines)

    def _render_decisions_view(self) -> str:
        decisions = self._fetch_all(
            """
            SELECT e.id, e.name, e.status, e.updated_at, e.description
            FROM entities e
            WHERE e.type IN ('decision', 'decision_log')
            ORDER BY e.updated_at DESC, e.id ASC
            """
        )
        lines = ["# Decisions", ""]
        if not decisions:
            lines.append("- No decision entities recorded.")
            lines.append("")
            return "\n".join(lines)
        for decision in decisions:
            title = decision["name"] or decision["id"]
            lines.append(f"## {title}")
            lines.append("")
            lines.append(f"- Status: {decision['status'] or 'unknown'}")
            if decision.get("description"):
                lines.append(f"- Summary: {decision['description']}")
            supporting_content = self._fetch_all(
                """
                SELECT content_type, body, created_at
                FROM content
                WHERE entity_id = ? AND content_type IN ('reasoning', 'analysis', 'spec', 'note')
                ORDER BY created_at DESC
                LIMIT 3
                """,
                (decision["id"],),
            )
            for item in supporting_content:
                lines.append(f"- {item['content_type']}: {item['body'][:200]}")
            lines.append("")
        return "\n".join(lines)

    def _render_plan_view(self) -> str:
        plans = self._fetch_all(
            """
            SELECT id, type, name, status, description, updated_at
            FROM entities
            WHERE type IN ('plan', 'task')
            ORDER BY updated_at DESC, id ASC
            LIMIT 200
            """
        )
        lines = ["# Plan", ""]
        if not plans:
            lines.append("- No plan-like entities recorded.")
            lines.append("")
            return "\n".join(lines)
        for plan in plans:
            title = plan["name"] or plan["id"]
            suffix = f": {plan['description']}" if plan.get("description") else ""
            lines.append(f"- [{plan['type']}] {title} ({plan['status'] or 'unknown'}){suffix}")
        lines.append("")
        return "\n".join(lines)

    def _render_notes_view(self) -> str:
        notes = self._fetch_all(
            """
            SELECT c.id, c.entity_id, c.content_type, c.body, c.created_at, e.name AS entity_name
            FROM content c
            JOIN entities e ON e.id = c.entity_id
            WHERE c.content_type IN ('note', 'analysis', 'reasoning', 'log', 'spec')
            ORDER BY c.created_at DESC, c.id ASC
            LIMIT 50
            """
        )
        lines = ["# Notes", ""]
        if not notes:
            lines.append("- No note-like content recorded.")
            lines.append("")
            return "\n".join(lines)
        for note in notes:
            label = note["entity_name"] or note["entity_id"]
            lines.append(f"## {label} [{note['content_type']}]")
            lines.append("")
            lines.append(note["body"])
            lines.append("")
        return "\n".join(lines)

    def get_entity_graph(
        self,
        entity_id: str,
        max_depth: int = 2,
        relationship_type: str | None = None,
    ) -> dict[str, Any]:
        entity_id = _validate_identifier(entity_id, "entity id")
        max_depth = max(1, min(max_depth, 8))

        if relationship_type:
            relationship_type = _validate_identifier(relationship_type, "relationship type")
            type_clause = "AND r.type = ?"
            parameters: tuple[Any, ...] = (entity_id, relationship_type, max_depth)
        else:
            type_clause = ""
            parameters = (entity_id, max_depth)

        edges = self._fetch_all(
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
            """,
            parameters if relationship_type is None else (entity_id, relationship_type, max_depth, relationship_type),
        )

        node_ids = {entity_id}
        for edge in edges:
            node_ids.add(edge["from_entity"])
            node_ids.add(edge["to_entity"])

        placeholders = ", ".join("?" for _ in node_ids)
        nodes = self._fetch_all(
            f"SELECT * FROM entities WHERE id IN ({placeholders}) ORDER BY type, id",
            tuple(sorted(node_ids)),
        )

        return {
            "root": self.get_entity(entity_id, include_related=False),
            "depth": max_depth,
            "relationship_type": relationship_type,
            "nodes": nodes,
            "relationships": edges,
        }
