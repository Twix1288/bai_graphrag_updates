# Investigating the GraphRAG "Sub-Location Intelligence" Plan

Hey! I took the original product plan (`final_check.md`) and actually built out the core of the Sub-Location Intelligence engine to see if the vision holds up in reality. 

The goal was to stop treating "Maui" as one giant hotel list and instead recommend specific sub-locations (like Ka'anapali vs. Wailea) based on a family's vibe and budget.

I wired it up end-to-end on live infrastructure (Neo4j, Redis, Nominatim). Here is my brutally honest evaluation of what works, what completely falls flat, and how efficient the whole setup really is.

## 🎯 Evaluating the Implementation (The Brutal Truth)

### 1. The Deterministic Ranking Engine: 10/10 (Highly Efficient)
**The Plan:** Score traveler preferences against a fixed 10-attribute schema using plain math (a weighted dot-product) instead of asking an LLM to rank things.
**The Reality:** This is the best part of the system. It works flawlessly. By keeping the LLM entirely out of the ranking math, the queries are incredibly fast, ridiculously cheap, and completely debuggable. If a sub-location ranks lower, I can look at the math and see *exactly* why (e.g., a budget penalty kicked in). Zero hallucinations during the ranking phase.

### 2. Fixing the Data Model & Schema: 9/10
**The Plan:** Unify structured places into the graph so destinations, regions, and sub-locations are connected.
**The Reality:** The original ingestion was completely broken. When I fed it real Hawaii data, 88 distinct places collapsed into just 21 nodes because of fuzzy string-matching ("O'ahu" became everything). I ripped that out and forced deterministic IDs based on `(type, name, parent)`. Now, the graph is rock solid. Two different "North Shore" regions can coexist perfectly.

### 3. The LLM Score Seeding: 3/10 (Major Bottleneck)
**The Plan:** Use an LLM to read editorial text and "seed" the 0-10 attribute scores for each sub-location, then have humans verify it later.
**The Reality:** Honestly, the 4B-parameter model I used for this is a huge liability. It struggles to infer accurate scores from unstructured text (e.g., it misinterprets "money is no object" as a low budget tier). Also, the model's native "guided JSON" feature was completely broken and returned truncated garbage. I had to hack around it with plain-text prompting. The math engine is flawless, but right now it is running on deeply flawed, LLM-hallucinated inputs. We absolutely cannot scale this without a stronger model.

### 4. Keyless Geocoding (Nominatim): 4/10 (Terrible for Scale)
**The Plan:** Use OpenStreetMap Nominatim for free geocoding.
**The Reality:** I got it working, added query normalization, and geocoded ~83% of the entities. But Nominatim enforces a strict 1-request-per-second rate limit. That makes ingesting a large corpus painfully slow. It’s fine for a demo, but wildly inefficient for production. We *must* move to a paid provider or self-host a geocoder before we expand to 50 destinations.

### 5. The Missing Curation Pipeline: 0/10 (Not Built Yet)
**The Plan:** A three-layer architecture (GCS -> Supabase -> Neo4j) where humans review the LLM-seeded scores in Supabase before they hit the live graph.
**The Reality:** I didn't build this yet. Right now, I'm dumping the unverified, often-flawed LLM scores straight into Neo4j. This is extremely dangerous for data quality. The human-in-the-loop Supabase layer is no longer a "nice to have"—it's an absolute necessity given how weak the LLM seeding currently is.

---

## 🗺️ Final Verdict & Next Steps

**Overall Plan Rating: 7/10**

The core concept—separating text extraction from mathematical ranking—is a massive success. It solves the explainability problem that plagues most RAG systems. 

But to get this out of "demo mode" and into production, we have to fix the inputs. 

**What I need to build next:**
1. **Swap the LLM**: We need a heavier model that can actually generate reliable structured JSON for the attribute seeding.
2. **Build the Supabase UI**: I need to build the curation pipeline so curators can intercept and fix the LLM's bad scores before they go live.
3. **Ditch Public Nominatim**: Wire up a commercial geocoder so ingestion doesn't take hours.
4. **Hotel Grouping**: Write the point-in-polygon script to actually group hotel inventory under these newly ranked sub-locations.

---

## 🚀 Running the Current State Locally

If you want to see the math engine in action, you can spin it up via Docker (Neo4j 5.18+ required):

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
