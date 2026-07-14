import asyncio
import logging
from src.extraction import ContentExtractor
from src.geocoding import Geocoder
from src.ingestion import GraphIngestionPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===============================
# Mock Clients
# ===============================
class MockLLM:
    async def complete(self, prompt, **kwargs):
        return '{"extracted_topics": ["Luxury", "Pool"]}'

class MockGmaps:
    def geocode(self, query):
        if "Ambiguous" in query:
            return [{"id": 1}, {"id": 2}]
        if "Nowhere" in query:
            return []
        return [{
            "geometry": {"location": {"lat": -8.5069, "lng": 115.2625}},
            "address_components": [
                {"types": ["neighborhood"], "long_name": "Ubud"},
                {"types": ["locality"], "long_name": "Gianyar"},
                {"types": ["country"], "long_name": "Indonesia"}
            ]
        }]

class MockNeo4j:
    def __init__(self):
        self.cypher_calls = []
    
    async def execute_write(self, cypher, params):
        self.cypher_calls.append((cypher, params))
        await asyncio.sleep(0.05)
        
    async def execute_query(self, cypher, params):
        self.cypher_calls.append((cypher, params))
        await asyncio.sleep(0.05)

# Supabase removed

# ===============================
# Pipeline Tests
# ===============================
async def run_mock_pipeline():
    print("--- 1. Testing Phase 3: Topic Extraction ---")
    extractor = ContentExtractor(MockLLM())
    topics = await extractor.run_extraction_pipeline("We stayed at this beautiful luxury resort in Bali.")
    print(f"Extracted constrained topics: {topics}")
    
    print("\n--- 2. Testing Phase 4: Geocoding & Human Review Queue ---")
    geocoder = Geocoder(google_maps_client=MockGmaps())
    res1 = await geocoder.resolve_location("W Hotel", "Bali")
    print(f"Test A (Perfect Match) Result: {res1['hierarchy'] if res1 else None}")
    res2 = await geocoder.resolve_location("Ambiguous Hotel", "Bali")
    print(f"Test B (Ambiguous Route to queue) Result: {res2}")
    
    print("\n--- 3. Testing Phase 2: Claim Deduplication Concurrency & Branching ---")
    
    class MockEmbeddings:
        async def embed(self, text):
            return [0.1, 0.2, 0.3]

    mock_neo4j = MockNeo4j()
    pipeline = GraphIngestionPipeline(
        neo4j=mock_neo4j, 
        embeddings=MockEmbeddings()
    )
    
    logger.info("Firing two concurrent claim ingestion jobs for the SAME entity (simulating race condition)...")
    
    async def tracked_call(content_id, text, sentiment):
        logger.info(f"Task {content_id} starting...")
        await pipeline.process_and_insert_claim(
            content_id=content_id, 
            canonical_entity_id="entity-xyz", 
            claim_text=text, 
            sentiment=sentiment
        )
        # For the mock to work perfectly, we simulate the DB update if it created a new claim.
        # But we can just see what Neo4j cypher was called.
        logger.info(f"Task {content_id} finished.")
        
    # We expect the first to acquire lock, see no claims, and INSERT a new claim.
    # The second acquires lock, but wait - our mock_supabase doesn't auto-update when Neo4j is called.
    # So we'll just manually simulate it:
    
    # 1. Run first ingestion
    await tracked_call("content_A", "The pool was amazing", "positive")
    # In a real run, this would be updated in Neo4j. We simulate it loosely.
    
    # 2. Run concurrency test (content B and C hitting at exact same time)
    # Both B and C will attempt to deduplicate via neo4j.
    # With a lock, B acquires, reads `claim-999`, appends, and C acquires, reads `claim-999`, appends.
    await asyncio.gather(
        tracked_call("content_B", "Amazing pool!", "positive"),
        tracked_call("content_C", "Great pool.", "positive")
    )
    
    # 3. Test negative branch (sentiment conflict)
    logger.info("Testing new claim creation for conflicting sentiment (Negative)...")
    await tracked_call("content_D", "The pool was dirty", "negative")
    
    print(f"\nTotal Neo4j write calls executed: {len(mock_neo4j.cypher_calls)}")
    for i, (cypher, _) in enumerate(mock_neo4j.cypher_calls):
        if "MERGE (c)-[:MAKES_CLAIM]->(claim)" in cypher and "CASE" in cypher:
            print(f"Call {i+1}: DEDUPLICATION (MERGE and APPEND)")
        elif "CREATE (claim:Claim" in cypher:
            print(f"Call {i+1}: CREATION (NEW CLAIM)")

if __name__ == "__main__":
    asyncio.run(run_mock_pipeline())
