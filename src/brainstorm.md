Core Design Philosophy

This schema is built around 4 truths:

Everything is an entity
Everything can relate to everything
State must be authoritative
Narrative is separate from structure

So instead of rigid “task system” thinking, we build a graph-backed relational core.

🧱 Core Tables (Generic + Extensible)
1. entities (THE foundation)

Everything lives here.

CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,           -- 'task', 'file', 'module', 'decision', etc.
    name TEXT,
    description TEXT,
    status TEXT,                  -- 'active', 'done', 'deprecated', etc.
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

👉 This replaces:

tasks
modules
components
features
bugs
docs

Everything.

2. attributes (Flexible metadata)

Instead of schema rigidity:

CREATE TABLE attributes (
    entity_id TEXT,
    key TEXT,
    value TEXT,
    PRIMARY KEY (entity_id, key),
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

Examples:

(task-1, priority, high)
(file-3, language, csharp)
(module-2, layer, backend)

👉 Infinite flexibility without migrations.

3. relationships (Graph layer 🔥)
CREATE TABLE relationships (
    id TEXT PRIMARY KEY,
    from_entity TEXT,
    to_entity TEXT,
    type TEXT,  -- 'depends_on', 'implements', 'calls', 'blocks', etc.
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_entity) REFERENCES entities(id),
    FOREIGN KEY (to_entity) REFERENCES entities(id)
);

This is where things get dangerous (in a good way).

You can model:

task dependencies
file imports
module ownership
feature relationships
4. content (Unstructured knowledge)
CREATE TABLE content (
    id TEXT PRIMARY KEY,
    entity_id TEXT,
    content_type TEXT, -- 'note', 'spec', 'log', 'analysis'
    body TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

👉 This replaces:

notes.md
analysis.md
random AI thoughts
5. events (Audit + timeline)
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    entity_id TEXT,
    event_type TEXT, -- 'created', 'updated', 'status_changed'
    data TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

Now your AI can answer:

“Why did we change this?”

6. snapshots (State freezing)
CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

Optional mapping:

CREATE TABLE snapshot_entities (
    snapshot_id TEXT,
    entity_id TEXT
);

👉 Enables:

rollback
milestone tracking
versioned reasoning
🧠 Derived “Concepts” (No new tables needed)

This is where it gets elegant.

You don’t create separate tables for:

tasks
files
bugs
features

Instead:

Example: Task
INSERT INTO entities (id, type, name, status)
VALUES ('task-1', 'task', 'Implement auth', 'pending');
Example: File
INSERT INTO entities (id, type, name)
VALUES ('file-1', 'file', 'authController.cs');
Example: Dependency
INSERT INTO relationships (id, from_entity, to_entity, type)
VALUES ('rel-1', 'task-1', 'task-2', 'depends_on');
🔍 Query Power (This is why this wins)
Get all pending high-priority tasks:
SELECT e.*
FROM entities e
JOIN attributes a ON e.id = a.entity_id
WHERE e.type = 'task'
  AND e.status = 'pending'
  AND a.key = 'priority'
  AND a.value = 'high';
Find impact of a file:
SELECT r.to_entity
FROM relationships r
WHERE r.from_entity = 'file-1'
  AND r.type = 'depends_on';
Build a task graph:

Recursive queries → full dependency trees.

🧩 Optional Enhancements (Highly Recommended)
1. Full-Text Search (FTS5)

For content + descriptions:

CREATE VIRTUAL TABLE content_fts USING fts5(body);
2. Embeddings Table (for AI retrieval)
CREATE TABLE embeddings (
    entity_id TEXT,
    vector BLOB
);

Now you get:

semantic search
memory recall
3. Tags (faster filtering than attributes)
CREATE TABLE tags (
    entity_id TEXT,
    tag TEXT
);
⚖️ Why This Schema is Dangerous (In a Good Way)

Because it lets an AI:

Think in graphs
Store structured + unstructured memory
Adapt to any project instantly
Avoid schema migrations 90% of the time
⚠️ What You MUST Not Do

Don’t let the AI:

spam attributes with garbage keys
create meaningless relationships
duplicate entities

👉 You need:

validation rules
naming conventions
🧬 Final Architecture (What You Actually Build)
Layer 1: SQLite (this schema)
source of truth
Layer 2: MCP Interface
controlled queries
validation
helper functions
Layer 3: Generated Files
todo.md
roadmap.md

👉 These are views, not storage

💡 Next Level (You’re going to want this)

You can add:

“Reasoning Cache”

Store AI decisions like:

content_type = 'reasoning'

Now your AI can:

remember why it did something
avoid rethinking the same problem

If you want, I’ll take this further and design:

MCP API endpoints (exact function signatures)
Auto-sync system (DB ↔ markdown)
Copilot-style agent loop (but actually good)

AI-First MCP Tool Surface

If the MCP will be used constantly by an AI, the interface should not be centered on a generic `run sql` write tool.

What the AI actually needs most of the time:

- `bootstrap_project_memory(project_id, project_name, ...)`
    Creates the project root plus standard anchor entities like roadmap, architecture, plan, todo, notes, and decisions.

- `upsert_entity(...)`
    Idempotent write path so the AI can safely say what state should exist instead of branching between create vs update logic.

- `connect_entities(from_entity, to_entity, relationship_type, ...)`
    Idempotent edge creation. This matters because relationship duplication is one of the fastest ways to poison graph memory.

- `append_content(entity_id, content_type, body, ...)`
    Lets the AI store reasoning, notes, or analysis without having to generate unique content ids manually.

- `get_recent_activity(limit)`
    Lets the AI recover context fast when a new chat/session starts.

- `run_read_query(sql, parameters, limit)`
    Read-only escape hatch for inspection, diagnostics, custom reports, and one-off retrieval patterns. Good tool. Dangerous if it becomes the default interface.

- `render_markdown_views(view_names)` and `export_markdown_views(...)`
    Makes `todo.md`, `roadmap.md`, `plan.md`, `architecture.md`, `decisions.md`, and `notes.md` outputs from the DB instead of primary storage.

Conclusion

Yes, the MCP needs more than `RUN SQL`, but not more raw SQL. It needs higher-level verbs that match the AI’s real work:

- store or merge authoritative state
- connect concepts
- append narrative memory
- inspect state safely
- regenerate human-readable documents

That is a better interface than asking the AI to author SQL for every operation.
