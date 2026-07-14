import asyncio
from src.clients import get_neo4j_client

async def main():
    neo4j = get_neo4j_client()
    
    print("Dropping old vector indexes...")
    await neo4j.execute_query("DROP INDEX entity_embeddings IF EXISTS")
    await neo4j.execute_query("DROP INDEX alias_embeddings IF EXISTS")
    await neo4j.execute_query("DROP INDEX claim_embeddings IF EXISTS")
    
    print("Deleting all nodes...")
    await neo4j.execute_query("MATCH (n) DETACH DELETE n")
    
    print("Recreating vector indexes with 1024 dimensions...")
    await neo4j.execute_query("""
    CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS FOR (e:Entity) ON (e.embedding)
    OPTIONS {indexConfig: { `vector.dimensions`: 1024, `vector.similarity_function`: 'cosine' }}
    """)
    await neo4j.execute_query("""
    CREATE VECTOR INDEX alias_embeddings IF NOT EXISTS FOR (a:Alias) ON (a.embedding)
    OPTIONS {indexConfig: { `vector.dimensions`: 1024, `vector.similarity_function`: 'cosine' }}
    """)
    await neo4j.execute_query("""
    CREATE VECTOR INDEX claim_embeddings IF NOT EXISTS FOR (c:Claim) ON (c.embedding)
    OPTIONS {indexConfig: { `vector.dimensions`: 1024, `vector.similarity_function`: 'cosine' }}
    """)
    
    print("Database is clean and ready.")
    await neo4j.close()

if __name__ == "__main__":
    asyncio.run(main())
