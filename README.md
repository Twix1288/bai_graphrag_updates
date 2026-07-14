# GraphRAG Sub-Location Intelligence

Welcome to the **GraphRAG Sub-Location Intelligence** project! This repository contains a travel recommendation engine that goes beyond generic destination matching (like "Maui" or "Cancun"). Instead, it ranks the *sub-locations* of a destination (like Ka'anapali vs. Wailea) by how well they fit a traveler's specific preferences, and explains its reasoning in plain English.

---

## 🛠️ Recent Improvements & Fixes (What We Changed)

The original demo-scaffold laid a fantastic foundation. Recently, we ran an intensive system audit and applied a series of production-readiness improvements (with the help of Claude) to make the system secure, accurate, and truly end-to-end capable. 

Here are the major changes and edits we made to harden the project:

### 1. Data Integrity & Schema Unification
- **Fixed the Entity Collapse Bug**: When testing against the real Hawaii dataset, we found that 88 distinct places were silently collapsing into just 21 entities (due to fuzzy name-merging). We implemented **deterministic IDs keyed by (type, normalized name, parent)**. Now, legitimately repeated names (like two different "North Shore" regions) can coexist perfectly. 
- **Unified Structured Data**: Structured nodes (Destinations, Regions, SubLocations) now properly receive the `Entity` label and discoverability aliases so the engine can actually query them.

### 2. The Deterministic Ranking Engine
- **Replaced Hallucinated Scores**: The previous sub-location ranker inadvertently assigned identical scores to all sub-locations due to a fallback bug. We built the true **deterministic weighted dot-product engine** from the product plan. 
- **10-Attribute Schema**: It now mathematically ranks areas against a fixed 10-attribute schema (beach, snorkeling, food scene, etc.), with strict budget hard-filters and penalties, keeping the LLM entirely out of the ranking math.

### 3. Security & Correctness
- **Closed Cypher Injection**: Parameterized the NL2Cypher fallback path to close a live injection vulnerability.
- **Enforced Timeouts & TLS**: Fixed the Neo4j query timeout so the 5-second driver limit is actually applied server-side. Enforced TLS verification on the embeddings client using a portable CA bundle.
- **Reconciled Routing**: Fixed a routing gap where resolvable destinations were entirely skipping the sub-location ranker. The engine now uses a graph probe (`[:PART_OF]`) to dynamically route to the correct planner.

### 4. Keyless Geocoding
- **Integrated Nominatim**: Replaced an inactive Google Maps key with OpenStreetMap Nominatim. We added query normalization and fallback parsing, successfully geocoding ~83% of our entities out of the box while respecting the 1-request/second usage policy.

---

## 🌟 What It Does

When a traveler picks a destination and describes what they're looking for (e.g., "We love snorkeling and casual food on a mid-range budget"), the engine:
1. Translates those free-text preferences into a mathematical weight vector.
2. Scores the destination's sub-locations against those weights.
3. Returns ranked area cards containing a "why this fits you" explanation and an honest tradeoff.

Because the ranking is math-based rather than an opaque AI judgment, the results are fast, cheap, debuggable, and fully explainable.

## 🚀 How to Run It

You can spin up the entire system locally using Docker. Note: Neo4j 5.18+ is required for `vector.similarity.cosine` support.

```bash
# 1. Spin up Infrastructure (Neo4j and Redis)
docker run -d --name graphrag-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=<user>/<pass> neo4j:5.24-community
docker run -d --name graphrag-redis -p 6379:6379 redis:7-alpine

# 2. Setup Schema & Ingest Data
docker cp setup_neo4j.cypher graphrag-neo4j:/tmp/setup.cypher
docker exec graphrag-neo4j cypher-shell -u <user> -p <pass> -f /tmp/setup.cypher
python3 -m src.ingest_structured_data data/sample_scraped_data.json

# 3. Run the Interactive Chat Planner
PYTHONPATH=. python3 -m src.subloc_chat
```

### Running Tests
To ensure everything is working correctly, you can run the test suite (we added 27 passing tests covering ranking, injection safety, and routing!):
```bash
python3 -m pytest tests/
```

## 🗺️ Roadmap & Next Steps
- **Human-in-the-Loop Curation**: Standing up a GCS → Supabase pipeline so human curators can review and tweak LLM-seeded attribute scores before they hit Neo4j.
- **Hotel Grouping**: Wiring up point-in-polygon assignment to seamlessly group actual hotel inventory under these ranked sub-locations.
- **Evaluation Harness**: Building a set of golden destination/preference pairs to continuously test ranking quality as models upgrade.
