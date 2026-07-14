# Investigating the GraphRAG "Sub-Location Intelligence" Plan

I originally drafted the `final_check.md` product plan to solve a massive blind spot in travel recommendations: treating massive destinations like "Maui" as a single entity. I wanted to build an engine that recommends specific sub-locations (like Ka'anapali vs. Wailea) based on a family's vibe and budget, and explicitly explains *why* a place fits them.

I recently took that vision and started building the core of it out. Here is my brutally honest evaluation of what worked from the original plan, what hasn't been realized yet, and where the architecture needs to go next.

## 🎯 Evaluating the Product Plan Implementation

### What Worked Spectacularly

**1. The Deterministic Ranking Engine (10/10)**
The plan called for scoring traveler preferences against a fixed 10-attribute schema using plain math (a weighted dot-product) instead of asking an AI to hallucinate a ranking. 
*The Reality:* This is the biggest success of the implementation. It works flawlessly. By keeping the scoring purely mathematical, the queries are incredibly fast, completely debuggable, and honest. We achieved the explainability we wanted—if a sub-location ranks lower, the math clearly shows a budget penalty kicked in.

**2. The Data Model (9/10)**
The plan proposed inserting a `SubLocation` layer between Destinations and Hotels, storing attributes, price tiers, and honest tradeoffs.
*The Reality:* The graph schema has been successfully unified. The SubLocation nodes sit perfectly in the Neo4j hierarchy, allowing us to route queries exactly as planned.

### What Didn't Work (Or Is Missing)

**1. The Three-Layer Storage Architecture (2/10)**
The plan required a GCS -> Supabase -> Neo4j pipeline where human curators verify the LLM-generated attribute scores in Supabase before they ever hit the live Neo4j graph.
*The Reality:* I haven't built the Supabase curation layer yet. Right now, unverified scores are being dumped straight into Neo4j. This breaks the vision of having a trusted, human-edited "working set" of data.

**2. Hotel Grouping via Point-in-Polygon (4/10)**
The plan called for assigning every hotel to a sub-location using point-in-polygon math so travelers see hotels grouped geographically.
*The Reality:* While the sub-locations rank beautifully, the hotel assignment logic isn't wired up yet. The final step of the funnel—showing the traveler the specific hotels inside their winning sub-location—is missing.

**3. Creator Content Pipeline (0/10)**
The plan envisioned ingesting creator blogs and vlogs to extract structured claims that act as evidence for the attribute scores.
*The Reality:* This was completely out of scope for the initial pass. The creator pipeline remains totally untouched.

**4. Surfaces: Chat vs. Zara Voice (5/10)**
The plan detailed a ChatPlanning UI and a Zara Voice integration.
*The Reality:* The text-based ChatPlanning UI is functional, but the Zara voice integration (presenting 2-3 sub-locations conversationally) hasn't been implemented yet.

---

## 🗺️ Final Verdict & How to Improve

**Overall Plan Rating: 7/10**

The core concept—separating text extraction from mathematical ranking—is a massive success and solves the explainability problem that plagues most recommendation engines. However, the system is fundamentally incomplete without the human curation layer.

**How we improve from here:**
1. **Build the Supabase UI**: We absolutely must build the curation pipeline so humans can intercept and verify attribute scores before they go live.
2. **Wire Up Hotel Grouping**: Write the point-in-polygon script to actually group hotel inventory under these newly ranked sub-locations.
3. **Formal Evaluation Harness**: Build a set of destination/preference pairs to automatically test ranking quality over time.

---

## 🛑 Small Notes on Local Testing Limitations

While testing this locally, I ran into a few specific roadblocks due to my limited development setup:
- **Small LLM Seeding**: I used a small 4B-parameter model to "seed" the attribute scores, which often hallucinated or failed to return valid structured JSON. We'll need a stronger model for production.
- **Geocoding Rate Limits**: I used OpenStreetMap Nominatim for free geocoding, but its 1-req/second limit makes large-scale ingestion impossibly slow.
- **Data Collapse Bug**: My initial fuzzy string-matching caused 88 distinct Hawaii places to collapse into just 21 nodes (e.g., merging different "North Shore" areas). I fixed this by forcing deterministic IDs.

---

## 🚀 Running the Current State Locally

Neo4j 5.18+ is required.

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
I also wrote 27 new tests to cover the ranking math, injection safety, and routing:
```bash
python3 -m pytest tests/
```
