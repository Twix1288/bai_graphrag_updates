import asyncio
from src.clients import get_neo4j_client
async def main():
    neo4j = get_neo4j_client()
    r = await neo4j.execute_query('MATCH (e:Entity) RETURN e.canonical_name LIMIT 10')
    print([rec['e.canonical_name'] for rec in r.records])
    await neo4j.close()
asyncio.run(main())
