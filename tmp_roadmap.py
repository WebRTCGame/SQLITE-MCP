import sqlite3, json
conn = sqlite3.connect('data/project_memory.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT e.id,e.name FROM entities e JOIN relationships r ON e.id=r.to_entity WHERE r.from_entity='project.sqlite-mcp.roadmap' AND r.type='contains'").fetchall()
print(json.dumps([dict(r) for r in rows], indent=2))
conn.close()
