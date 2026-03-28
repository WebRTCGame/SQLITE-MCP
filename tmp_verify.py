import sqlite3, json
conn = sqlite3.connect('data/project_memory.db')
conn.row_factory = sqlite3.Row
queries = [
    "SELECT id,type,name,status FROM entities WHERE id IN ('note.install-workspace-scoped-mcp-config','task.phase9.ensure-project-scoped-mcp-config')",
    "SELECT id,entity_id,content_type FROM content WHERE id='content.install-workspace-scoped-mcp-config.1'",
    "SELECT from_entity,to_entity,type FROM relationships WHERE from_entity='phase.9.human-visibility-and-review-surfaces' AND to_entity IN ('note.install-workspace-scoped-mcp-config','task.phase9.ensure-project-scoped-mcp-config')"
]
for q in queries:
    print('---', q)
    rows = conn.execute(q).fetchall()
    print(json.dumps([dict(r) for r in rows], indent=2))
conn.close()
