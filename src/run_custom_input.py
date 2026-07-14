import sys
import asyncio
import logging
from src.extraction import ContentExtractor
from src.geocoding import Geocoder
from src.ingestion import GraphIngestionPipeline

logging.basicConfig(level=logging.ERROR)

# ===============================
# Mock Clients
# ===============================
class MockLLM:
    async def complete(self, prompt, **kwargs):
        # We just return a generic mock response for extraction
        return '{"extracted_topics": ["MockTopic1", "MockTopic2"]}'

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

# Supabase removed

async def run_custom(text_input, location_input):
    print(f"\n--- Processing Input ---")
    print(f"Text: '{text_input}'")
    print(f"Location: '{location_input}'\n")

    print("1. Extracting Topics (Mocked)...")
    extractor = ContentExtractor(MockLLM())
    topics = await extractor.extract_topics(text_input)
    print(f"-> Extracted topics: {topics}\n")
    
    print("2. Geocoding Location (Mocked)...")
    geocoder = Geocoder(google_maps_client=MockGmaps())
    res = await geocoder.resolve_location(location_input, "Global")
    print(f"-> Resolved location hierarchy: {res['hierarchy'] if res else 'None (Ambiguous/Not Found)'}\n")
    
    print("3. Ingesting Claim (Mocked)...")
    mock_neo4j = MockNeo4j()
    pipeline = GraphIngestionPipeline(
        neo4j=mock_neo4j, 
        embeddings=None
    )
    
    await pipeline.process_and_insert_claim(
        content_id="custom_content_1", 
        canonical_entity_id="entity-custom", 
        claim_text=text_input, 
        sentiment="neutral"
    )
    
    print(f"-> Neo4j Graph queries generated:")
    for i, (cypher, params) in enumerate(mock_neo4j.cypher_calls):
        if "MERGE (c)-[:MAKES_CLAIM]->(claim)" in cypher and "CASE" in cypher:
            print(f"   Call {i+1}: DEDUPLICATION (MERGE and APPEND)")
        elif "CREATE (claim:Claim" in cypher:
            print(f"   Call {i+1}: CREATION (NEW CLAIM)")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/run_custom_input.py <text_input> <location_input>")
        sys.exit(1)
    
    text = sys.argv[1]
    loc = sys.argv[2]
    asyncio.run(run_custom(text, loc))
