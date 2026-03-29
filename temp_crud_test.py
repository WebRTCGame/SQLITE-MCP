import os, sys
from pathlib import Path
import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

repo_root = Path.cwd()

def run_workflow():
    db_path = repo_root / 'data' / 'project_memory_crud.db'
    if db_path.exists():
        db_path.unlink()

    server = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'sqlite_mcp_server'],
        cwd=str(repo_root),
        env={
            'SQLITE_MCP_TRANSPORT': 'stdio',
            'SQLITE_MCP_DB_PATH': str(db_path),
            'SQLITE_MCP_EXPORT_DIR': str(repo_root / 'exports'),
        },
    )

    async def work():
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as sess:
                await sess.initialize()
                print('initialized')

                bootstrap = await sess.call_tool('bootstrap_project_memory', {
                    'project_id': 'project.sqlite-mcp',
                    'project_name': 'SQLite MCP',
                    'description': 'CRUD test'
                })
                print('bootstrap', bootstrap.content[0].text[:70])

                created = await sess.call_tool('upsert_entity', {
                    'entity_id': 'task.crud-test',
                    'entity_type': 'task',
                    'name': 'CRUD test task',
                    'status': 'active',
                })
                print('created', created.content[0].text)

                updated = await sess.call_tool('update_entity', {
                    'entity_id': 'task.crud-test',
                    'name': 'CRUD test task updated',
                    'status': 'in_progress',
                })
                print('updated', updated.content[0].text)

                got = await sess.call_tool('get_entity', {'entity_id': 'task.crud-test'})
                print('got', got.content[0].text)

                deleted = await sess.call_tool('delete_entity', {'entity_id': 'task.crud-test', 'force': True})
                print('deleted', deleted.content[0].text)

    anyio.run(work)

if __name__ == '__main__':
    run_workflow()
