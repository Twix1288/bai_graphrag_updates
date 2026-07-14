# GraphRAG System Audit Report

Based on a thorough review of the codebase (specifically `engine.py`, `ingestion.py`, `ingest_structured_data.py`, `ingest_scraped_data.py`, and the Neo4j schema), here is a brutal and honest assessment of what is working and what is broken in the RAG system.

## 🟢 What is Working (The Good)
1. **Neo4j Vector Search Integration**: The use of `db.index.vector.queryNodes` for entity alias resolution and claim deduplication is correctly implemented and should be fast.
2. **Entity Extraction (Scraped Data)**: The pipeline in `ingest_scraped_data.py` properly geocodes extracted entities, creates canonical `Entity` nodes, links `Alias` nodes for vector resolution, and deduplicates claims based on semantic similarity.
3. **Late Fusion Synthesis**: The approach in `engine.py` to use Neo4j to find relevant `content_ids` and then fetch raw text chunks to feed the LLM for final synthesis is a solid RAG architecture.
4. **Fallback Handling**: The `_nl2cypher_fallback` provides a sandboxed, rate-limited safety net when entity resolution fails.

## 🔴 What is Broken (The Bad & The Ugly)

### 1. SubLocation Ranking is Mathematically Broken (Hallucinated Scores)
In `engine.py`, the `_execute_find_sublocations_for_destination` method attempts to rank sub-locations by taking a dot product of user preference weights against sub-location scores (`snorkeling`, `beach`, `food_scene`, `nightlife`, `family_friendly`). 
* **The Bug**: These scores **do not exist** in `data/sample_scraped_data.json` and are **never ingested** in `ingest_structured_data.py`. 
* **The Result**: The Cypher query uses `coalesce(s.score_snorkeling, 5)`, which defaults all missing scores to `5`. This means *every single sub-location* will receive the exact same final score (`5 * w1 + 5 * w2...`). The ranking is entirely meaningless and input-order dependent.

### 2. Disconnected Graph Entities (Structured Data vs. Engine)
There is a massive schema disconnect between how structured data is ingested and how the engine expects to query it.
* **The Bug**: `ingest_structured_data.py` creates nodes with labels `Destination`, `Region`, `SubLocation`, and `Attraction`. However, it **does not** give them the `Entity` label, does not create an `Alias` node with vector embeddings, and does not assign a UUID (`id` property).
* **The Result**: When the engine extracts an attraction or location from a user query, it calls `_resolve_entity_uuid`. This relies on `alias_embeddings` to find an `Alias` that resolves to an `Entity`. Since structured attractions/locations lack `Alias` nodes, embeddings, and the `Entity` label, **the engine can never resolve them**.

### 3. Missing Geocoding for Structured Attractions
* **The Bug**: `engine.py`'s `_execute_find_hotels_near_attraction` uses a spatial query: `point.distance(h.location, a.location) < $max_distance`. This requires both the hotel and the attraction to have a valid spatial `location` point.
* **The Result**: While scraped entities are geocoded in `ingest_scraped_data.py`, the attractions ingested from structured data (`ingest_structured_data.py`) are never geocoded. Even if the entity resolution bug (above) was fixed, the spatial distance query would still fail because the attractions lack coordinate data.

### 4. Distributed Lock Vulnerability
* **The Bug**: In `ingestion.py` (`MockRedisLock`), there is a comment explicitly noting that the timeout is not wired into the atomic lock acquisition. 
* **The Result**: While currently a mock, if this goes to production with real Redis without setting the TTL atomically on acquisition, a process crash mid-ingestion will cause a permanent deadlock for that entity.

## 🛠️ Recommended Fixes

1. **Fix SubLocation Ranking**: We either need to add the feature scores (`score_snorkeling`, etc.) to the source JSON and ingest them, or we need to change the sub-location ranking logic in the engine to use semantic search against the sub-location descriptions instead of a hardcoded dot product.
2. **Unify the Graph Schema**: Update `ingest_structured_data.py` to:
   * Give `Destination`, `Region`, `SubLocation`, and `Attraction` the secondary `Entity` label.
   * Generate UUIDs for them.
   * Create `Alias` nodes with embeddings for their names so they can be discovered by `_resolve_entity_uuid`.
3. **Add Geocoding to Structured Ingestion**: Integrate the `Geocoder` into `ingest_structured_data.py` so that attractions and locations get proper `latitude`, `longitude`, and Neo4j spatial `location` properties.

Let me know which of these you'd like to tackle first!
