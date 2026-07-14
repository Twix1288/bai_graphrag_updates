# GraphRAG Sub-Location Intelligence 

Hey! So the original demo for this travel recommendation engine was a really cool proof-of-concept, but I wanted to take it from a demo scaffold and make it genuinely production-ready.

With Claude's help, I ran a deep audit on the system and ended up rewriting big chunks of the core logic to make it secure, accurate, and totally end-to-end capable. Here’s a rundown of what I actually changed and why.

## 🛠️ What Claude and I Fixed & Improved

### 1. Stopping the Data Collapse
When I tried running the real Hawaii dataset through the original ingestion, I noticed something crazy: 88 distinct places were silently collapsing into just 21 entities. "O'ahu" somehow got tagged as a Destination, Region, SubLocation, *and* Attraction all at once. 
**The fix:** I bypassed the old fuzzy string-matching and implemented deterministic IDs keyed by `(type, normalized name, parent)`. Now, if there are two "North Shore" regions (one on Oahu, one on Kauai), they coexist perfectly without squashing each other.

### 2. Building a Real Ranking Engine
The old sub-location ranker was accidentally assigning identical scores to everything because of a fallback bug. I ripped that out and built a **deterministic weighted dot-product engine**. Now, it mathematically ranks areas against a fixed 10-attribute schema (beach, snorkeling, food scene, etc.), complete with strict budget hard-filters and penalties. The LLM is strictly used to translate text to weights and write the final copy—it is completely removed from the actual ranking math.

### 3. Plugging Security Holes & Routing Bugs
- **Cypher Injection:** Found a live injection vulnerability in the NL2Cypher fallback path. I parameterized the query to lock it down.
- **Silent Timeouts & TLS:** Fixed the Neo4j query timeout so the 5-second limit actually works server-side. Also enforced TLS verification on the embeddings client using a portable CA bundle so it works securely on macOS.
- **Routing:** There was a bug where resolvable destinations were entirely skipping the sub-location ranker. I added a graph probe (`[:PART_OF]`) so the engine dynamically routes to the correct planner now.

### 4. Keyless Geocoding
The old setup had an inactive Google Maps key, meaning attractions were never getting geocoded. I swapped that out for OpenStreetMap Nominatim. Added some query normalization and fallback parsing, and now we're successfully geocoding ~83% of the entities right out of the box (while playing nice with their 1-request/second limit).

---

## 🌟 How the Engine Works Now

When you pick a destination and describe your trip (e.g., "We love snorkeling and casual food on a mid-range budget"):
1. The engine translates your text into a mathematical weight vector.
2. It scores the destination's sub-locations against those weights using the new deterministic engine.
3. It hands back ranked area cards with a "why this fits you" explanation and an honest tradeoff.

Because it relies on math instead of an opaque LLM prompt for the ranking, it's fast, cheap, completely debuggable, and doesn't hallucinate.

## 🚀 Running It Locally

You can spin the whole thing up locally with Docker (just make sure you're on Neo4j 5.18+ so `vector.similarity.cosine` works).

```bash
# 1. Spin up the infrastructure
docker run -d --name graphrag-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=<user>/<pass> neo4j:5.24-community
docker run -d --name graphrag-redis -p 6379:6379 redis:7-alpine

# 2. Setup the schema and ingest the sample data
docker cp setup_neo4j.cypher graphrag-neo4j:/tmp/setup.cypher
docker exec graphrag-neo4j cypher-shell -u <user> -p <pass> -f /tmp/setup.cypher
python3 -m src.ingest_structured_data data/sample_scraped_data.json

# 3. Try out the Interactive Chat Planner!
PYTHONPATH=. python3 -m src.subloc_chat
```

### Tests
I also wrote 27 new tests to cover the ranking math, injection safety, and routing. You can run them with:
```bash
python3 -m pytest tests/
```

## 🗺️ Next Steps
- **Human-in-the-Loop Curation**: I want to set up a GCS → Supabase pipeline so human curators can tweak the LLM-seeded attribute scores before they ever hit Neo4j.
- **Hotel Grouping**: Need to wire up point-in-polygon assignment to actually group real hotel inventory under these ranked sub-locations.
- **Evaluation Harness**: Build a set of golden destination/preference pairs to continuously test the ranking quality as we swap out models.
