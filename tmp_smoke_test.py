from pathlib import Path
from sqlite_mcp_server.cli import _sync_document
from sqlite_mcp_server.db import DatabaseManager

p = Path('test-mem.db')
if p.exists():
    p.unlink()

manager = DatabaseManager(p)
manager.connect()
try:
    manager.bootstrap_project_memory('project.sqlite-mcp', 'SQLite MCP')
    road = Path('roadmap.md')
    road.write_text('# Roadmap Narrative\n\nTrack migration completion and strategic direction.\n', encoding='utf-8')

    r = _sync_document(manager, 'roadmap', road)
    print('sync result', r)

    anchor = manager.get_entity('project.sqlite-mcp.roadmap', include_related=True)
    print('anchor source_path', anchor['attributes']['source_path'])

    assert r['entity_id'] == 'project.sqlite-mcp.roadmap'
    assert any(x['id'] == 'document.roadmap.current' for x in anchor['content'])

    rendered = manager.render_markdown_views(['roadmap'], user_requested=True, request_reason='testing roadmap')
    print('roadmap output snippet', rendered['roadmap.md'][:300])

    assert '## Current Roadmap Document' in rendered['roadmap.md']
    assert 'Track migration completion and strategic direction.' in rendered['roadmap.md']
    print('manual smoke test passed')
finally:
    manager.close()
    if road.exists():
        road.unlink()
    if p.exists():
        p.unlink()
