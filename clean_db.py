import asyncio
from src.clients import get_neo4j_client

async def main():
    neo4j = get_neo4j_client()
    await neo4j.execute_query("MATCH (n) DETACH DELETE n")
    print("Database wiped!")
    await neo4j.close()

if __name__ == "__main__":
    asyncio.run(main())
