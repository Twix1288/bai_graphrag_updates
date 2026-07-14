import os
import sys
import json
import uuid
import asyncio
import logging
from dotenv import load_dotenv

# Load env variables
load_dotenv()

from src.clients import get_neo4j_client, get_llm_client, get_embedding_client, get_redis_client
from src.extraction import ContentExtractor
from src.geocoding import Geocoder
from src.ingestion import GraphIngestionPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Basic Mock Gmaps for now, unless you have a real client
class RealOrMockGmaps:
    def geocode(self, query):
        logger.info(f"Geocoding {query}...")
        # In a real scenario, this uses the real google maps client
        # For presentation purposes, returning a mock generic location
        return [{
            "geometry": {"location": {"lat": -8.5069, "lng": 115.2625}},
            "address_components": [
                {"types": ["neighborhood"], "long_name": "Mock Neighborhood"},
                {"types": ["locality"], "long_name": "Mock City"},
                {"types": ["country"], "long_name": "Mock Country"}
            ]
        }]

async def ingest_scraped_data(file_path: str):
    logger.info(f"Loading data from {file_path}")
    
    with open(file_path, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON file. Ensure it is a valid JSON array.")
            return

    if not isinstance(data, list):
        logger.error("JSON file must contain an array of objects.")
        return

    # Initialize infrastructure
    neo4j_client = get_neo4j_client()
    llm_client = get_llm_client()
    embedding_client = get_embedding_client()
    redis_client = get_redis_client()
    
    extractor = ContentExtractor(llm_client)
    
    gmaps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if gmaps_api_key:
        import googlemaps
        gmaps_client = googlemaps.Client(key=gmaps_api_key)
        logger.info("Using REAL Google Maps Client")
    else:
        gmaps_client = RealOrMockGmaps()
        logger.info("Using MOCK Google Maps Client (no GOOGLE_MAPS_API_KEY found)")
        
    geocoder = Geocoder(google_maps_client=gmaps_client)
    pipeline = GraphIngestionPipeline(neo4j=neo4j_client, embeddings=embedding_client, redis_client=redis_client)

    logger.info(f"Starting ingestion of {len(data)} documents...")

    for i, doc in enumerate(data):
        doc_id = doc.get("id", str(uuid.uuid4()))
        text = doc.get("text", "")
        
        if not text:
            logger.warning(f"Document at index {i} has no 'text' field. Skipping.")
            continue

        logger.info(f"--- Processing Document {i+1}/{len(data)}: {doc_id} ---")
        
        # 1. Insert Content Node (for Late Fusion later)
        content_cypher = """
        MERGE (c:Content {id: $doc_id})
        SET c.chunk_text = $text, c.url = $url
        """
        await neo4j_client.execute_query(content_cypher, {
            "doc_id": doc_id, 
            "text": text,
            "url": doc.get("url", "")
        })

        # 2. Extract structured data via LLM
        extracted_data = await extractor.run_extraction_pipeline(text)
        
        # 3. Link Topics
        topics = extracted_data.get("topics", [])
        logger.info(f"Extracted {len(topics)} topics: {topics}")
        for topic in topics:
            topic_cypher = """
            MERGE (t:Topic {name: $name})
            ON CREATE SET t.id = randomUUID()
            WITH t
            MATCH (c:Content {id: $doc_id})
            MERGE (c)-[:DISCUSSES]->(t)
            """
            await neo4j_client.execute_query(topic_cypher, {"name": topic, "doc_id": doc_id})

        # 4. Process Entities and Claims
        entities = extracted_data.get("entities", [])
        logger.info(f"Extracted {len(entities)} entities.")
        for entity in entities:
            entity_name = entity.get("name")
            entity_type = entity.get("type", "Hotel").lower()
            location_context = entity.get("location_context", "")
            
            if not entity_name: continue
            
            # 4a. Geocode Location
            geo_query = f"{entity_name} {location_context}".strip()
            geo_res = await geocoder.resolve_location(geo_query, "Global")
            
            # 4b. Resolve Entity Alias
            canonical_id = await pipeline.resolve_or_create_alias(entity_name, entity_type, geo_res)
            
            if not canonical_id:
                logger.warning(f"Could not resolve or create canonical ID for '{entity_name}'. Skipping claims.")
                continue
                
            # 4c. Process Claims
            claims = entity.get("claims", [])
            logger.info(f"Processing {len(claims)} claims for entity '{entity_name}' (ID: {canonical_id})")
            for c in claims:
                claim_text = c.get("claim", "")
                sentiment = c.get("sentiment", "neutral")
                
                if claim_text:
                    await pipeline.process_and_insert_claim(
                        content_id=doc_id,
                        canonical_entity_id=canonical_id,
                        claim_text=claim_text,
                        sentiment=sentiment
                    )

    logger.info("Bulk ingestion complete!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/ingest_scraped_data.py <path_to_json>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    asyncio.run(ingest_scraped_data(file_path))
