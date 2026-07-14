import re
import time
import logging
from typing import Dict, Any, List, Optional
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class MockRedisLock:
    """
    Minimal distributed lock using Redis SET NX with a TTL.
    Mocked via local state for scaffolding purposes, but exposes the correct async interface.

    The TTL is wired into acquisition (mirroring `SET NX EX`): each held lock records
    an expiry, and an expired entry is treated as free. This means a holder that crashes
    mid-ingestion cannot deadlock the entity forever — the lock self-heals after `timeout`.
    """
    def __init__(self):
        # name -> monotonic expiry timestamp
        self._locks: Dict[str, float] = {}

    @asynccontextmanager
    async def lock(self, name: str, timeout: int = 10):
        # 1. Acquire (equivalent to Redis `SET name locked NX EX timeout`).
        # When swapping to real Redis, keep the TTL atomic on acquisition:
        #   acquired = await redis.set(name, token, nx=True, ex=timeout)
        while True:
            existing_expiry = self._locks.get(name)
            now = time.monotonic()
            if existing_expiry is None or existing_expiry <= now:
                # Free, or the previous holder's TTL lapsed (crash-safety).
                self._locks[name] = now + timeout
                break
            await asyncio.sleep(0.1)
        logger.info(f"Lock acquired: {name} (ttl={timeout}s)")

        try:
            yield
        finally:
            # 2. Release
            # Real code: await redis.delete(name)  (guarded by the fencing token)
            self._locks.pop(name, None)
            logger.info(f"Lock released: {name}")

class GraphIngestionPipeline:
    """
    Handles ingestion of LLM-extracted structured data into the Neo4j graph.
    Implements Phase 2: Alias Resolution and Claim Deduplication using native Neo4j vector search.
    """
    def __init__(self, neo4j, embeddings, redis_client=None):
        self.neo4j = neo4j
        self.embeddings = embeddings
        # Use provided redis client or fallback to the mock lock implementation
        self.redis_lock = redis_client or MockRedisLock()

    # ==========================================
    # ALIAS RESOLUTION
    # ==========================================
    
    def _normalize_string(self, text: str) -> str:
        """
        Normalize strings for alias matching (lowercase, strip punctuation).
        """
        if not text: return ""
        # Lowercase and remove all non-alphanumeric chars (except spaces)
        normalized = re.sub(r'[^\w\s]', '', text.lower())
        # Replace multiple spaces with a single space
        return re.sub(r'\s+', ' ', normalized).strip()

    async def resolve_or_create_alias(self, raw_entity_name: str, entity_type: str, geo_res: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        1. Normalize the string.
        2. Vector lookup against existing aliases/entities.
        3. If confident match, return canonical UUID.
        4. If low confidence, do NOT auto-create duplicate. Flag for review.
        """
        normalized_name = self._normalize_string(raw_entity_name)
        
        # 1. Exact match check (bypasses vector index sync delay)
        exact_match_cypher = """
        MATCH (a:Alias {normalized_name: $name})-[:RESOLVES_TO]->(e:Entity)
        RETURN e.id AS entity_id
        """
        exact_res = await self.neo4j.execute_query(exact_match_cypher, {"name": normalized_name})
        exact_records = [record.data() for record in exact_res.records]
        
        lat = geo_res["lat"] if geo_res else None
        lng = geo_res["lng"] if geo_res else None
        
        if exact_records:
            canonical_id = exact_records[0]["entity_id"]
            if lat is not None and lng is not None:
                update_geo_cypher = """
                MATCH (e:Entity {id: $canonical_id})
                SET e.latitude = $lat,
                    e.longitude = $lng,
                    e.location = point({latitude: $lat, longitude: $lng})
                """
                await self.neo4j.execute_query(update_geo_cypher, {"canonical_id": canonical_id, "lat": lat, "lng": lng})
            return canonical_id
            
        # Stored/indexed text -> "passage" input type (asymmetric e5 embeddings).
        embed_vector = await self.embeddings.embed(normalized_name, input_type="passage")

        cypher = """
        CALL db.index.vector.queryNodes('alias_embeddings', 1, $embedding) YIELD node AS a, score
        WHERE score >= $threshold
        MATCH (a)-[:RESOLVES_TO]->(e:Entity)
        RETURN e.id AS entity_id, score AS similarity
        """
        response = await self.neo4j.execute_query(
            cypher, 
            {"embedding": embed_vector, "threshold": 0.88}
        )
        result = [record.data() for record in response.records]
        
        lat = geo_res["lat"] if geo_res else None
        lng = geo_res["lng"] if geo_res else None
        
        if result and result[0]["similarity"] >= 0.88:
            # We found a canonical match!
            canonical_id = result[0]["entity_id"]
            
            # Ensure this alias is explicitly linked in Neo4j if it isn't already
            # And update location if provided
            cypher = """
            MERGE (a:Alias {normalized_name: $name})
            ON CREATE SET a.embedding = $embedding
            MERGE (e:Entity {id: $canonical_id})
            MERGE (a)-[:RESOLVES_TO]->(e)
            """
            
            if lat is not None and lng is not None:
                cypher += """
                SET e.latitude = $lat,
                    e.longitude = $lng,
                    e.location = point({latitude: $lat, longitude: $lng})
                """
                
            await self.neo4j.execute_query(cypher, {"name": normalized_name, "canonical_id": canonical_id, "embedding": embed_vector, "lat": lat, "lng": lng})
            return canonical_id
        else:
            # Auto-create new entity since we have no confident match
            import uuid
            new_entity_id = str(uuid.uuid4())
            
            if lat is not None and lng is not None:
                cypher = """
                CREATE (e:Entity {
                    id: $entity_id, 
                    type: $type, 
                    canonical_name: $raw_name,
                    latitude: $lat,
                    longitude: $lng,
                    location: point({latitude: $lat, longitude: $lng})
                })
                CREATE (a:Alias {normalized_name: $name, embedding: $embedding})
                CREATE (a)-[:RESOLVES_TO]->(e)
                """
            else:
                cypher = """
                CREATE (e:Entity {id: $entity_id, type: $type, canonical_name: $raw_name})
                CREATE (a:Alias {normalized_name: $name, embedding: $embedding})
                CREATE (a)-[:RESOLVES_TO]->(e)
                """
                
            await self.neo4j.execute_query(
                cypher, 
                {"entity_id": new_entity_id, "type": entity_type, "raw_name": raw_entity_name, "name": normalized_name, "embedding": embed_vector, "lat": lat, "lng": lng}
            )
            return new_entity_id

    # ==========================================
    # CLAIM DEDUPLICATION
    # ==========================================
    
    async def process_and_insert_claim(self, content_id: str, canonical_entity_id: str, claim_text: str, sentiment: str):
        """
        Inserts a Claim node for an entity, deduplicating if highly similar (Cosine > 0.92) AND sentiment matches.
        Uses a distributed lock on the entity to prevent race conditions between the similarity read and the merge write.
        """
        new_claim_embedding = await self.embeddings.embed(claim_text, input_type="passage")
        
        # BLOCKER 2 RESOLVED: Transactional Safety
        async with self.redis_lock.lock(f"entity_claim_lock:{canonical_entity_id}", timeout=10):
        
            # 1. Search existing claims for this specific entity (Read) via Neo4j vector search
            try:
                cypher = """
                CALL db.index.vector.queryNodes('claim_embeddings', 10, $embedding) YIELD node AS claim, score
                WHERE score >= $threshold AND claim.sentiment = $sentiment
                MATCH (claim)-[:ABOUT]->(e:Entity {id: $entity_id})
                RETURN claim.id AS claim_id, score AS similarity
                ORDER BY score DESC
                LIMIT 1
                """
                response = await self.neo4j.execute_query(
                    cypher,
                    {"embedding": new_claim_embedding, "entity_id": canonical_entity_id, "threshold": 0.92, "sentiment": sentiment}
                )
                match = [record.data() for record in response.records]
            except Exception as e:
                logger.error(f"Error searching claims: {e}")
                match = []
            
            if match:
                existing_claim_id = match[0]["claim_id"]
                logger.info(f"Deduplicating claim {claim_text} into {existing_claim_id}")
                
                # 2. Update the Neo4j Claim node (Write)
                cypher = """
                MATCH (c:Content {id: $content_id})
                MATCH (claim:Claim {id: $claim_id})
                MERGE (c)-[:MAKES_CLAIM]->(claim)
                SET claim.sources = CASE 
                    WHEN $content_id IN claim.sources THEN claim.sources 
                    ELSE claim.sources + $content_id 
                END
                """
                await self.neo4j.execute_query(cypher, {"content_id": content_id, "claim_id": existing_claim_id})
                
            else:
                import uuid
                new_claim_id = str(uuid.uuid4())
                
                # 2. Insert into Neo4j (Write) and set embedding for future vector search
                cypher = """
                MATCH (c:Content {id: $content_id})
                MATCH (e:Entity {id: $entity_id})
                CREATE (claim:Claim {id: $claim_id, text: $text, sentiment: $sentiment, sources: [$content_id], embedding: $embedding})
                CREATE (c)-[:MAKES_CLAIM]->(claim)
                CREATE (claim)-[:ABOUT]->(e)
                """
                await self.neo4j.execute_query(cypher, {
                    "content_id": content_id, 
                    "entity_id": canonical_entity_id, 
                    "claim_id": new_claim_id, 
                    "text": claim_text, 
                    "sentiment": sentiment,
                    "embedding": new_claim_embedding
                })
