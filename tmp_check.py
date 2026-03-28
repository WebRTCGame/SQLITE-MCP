import sqlite3, json
conn = sqlite3.connect('data/project_memory.db')
conn.row_factory = sqlite3.Row
qlist = [
    "SELECT id,name,status FROM entities WHERE id LIKE 'note.install%';",
    "SELECT id,name,status FROM entities WHERE id LIKE 'task.%install%';",
    "SELECT id,name,status FROM entities WHERE id LIKE 'phase.%';"
]
for q in qlist:
    print('---', q)
    rows = conn.execute(q).fetchall()
    print(json.dumps([dict(r) for r in rows], indent=2))
conn.close()
