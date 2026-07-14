# GraphRAG Sub-Location Intelligence 

Hey! So we originally laid out a grand vision in our `final_check.md` product plan: rather than just dropping a traveler into a massive list of hotels in "Maui", we wanted to build a recommendation engine that actually understands the *sub-locations* (like Ka'anapali vs. Wailea). We wanted to rank these areas based on a family's stated preferences, budget, and vibe, and explain exactly *why* a place fits them.

With Claude's help, I took that vision and actually built the core of it out. Here’s a rundown of how we implemented the plan, what worked perfectly, the limitations we hit (looking at you, LLMs), and where we go from here.

## 🎯 What We Set Out To Do (The Vision)
The goal from the plan was simple but ambitious:
- Add a `SubLocation` layer to the knowledge graph with a scored 10-attribute profile (beach, snorkeling, food scene, etc.) and a price tier.
- Score a traveler's preferences against these profiles using a **deterministic math formula** (weighted dot-product) instead of an opaque LLM prompt.
- Provide honest tradeoffs (e.g., "Great beaches, but resort-level dining prices").

## 🛠️ How We Implemented It (What Worked)

We got the core engine running end-to-end on live infrastructure (Neo4j, Redis, Nominatim). Here are the big wins:

1. **The Deterministic Ranking Engine is Alive**: We actually built it! The system translates free-text preferences into weights, scores them against the 10-attribute schema, applies a budget hard-filter, and penalizes price mismatches. It’s entirely math-based, meaning it's fast, cheap, completely debuggable, and doesn't hallucinate. 
2. **Fixed the Data Collapse**: When we ingested the Hawaii dataset, 88 places were collapsing into 21. We bypassed fuzzy string-matching and implemented **deterministic IDs** keyed by `(type, normalized name, parent)`. Now, overlapping names (like two different "North Shore" regions) coexist perfectly.
3. **Plugging Security & Correctness Holes**: We closed a live Cypher injection vulnerability by parameterizing queries, fixed silent driver timeouts, enforced TLS verification for embeddings, and corrected a major routing bug so destinations actually hit the sub-location ranker.
4. **Keyless Geocoding**: We successfully integrated OpenStreetMap Nominatim, added query normalization, and geocoded ~83% of the entities right out of the box.

## ⚠️ What Didn't Work So Well (Limitations & Gotchas)

While the engine works beautifully, we definitely hit some rough edges when it came to the inputs and the LLM integration:

1. **The LLM Seeding Bottleneck**: We use a small 4B-parameter model to initially read editorial text and "seed" the 0-10 attribute scores for each sub-location. Honestly, the inputs can be weak. The model sometimes returns neutral or weird values (like inferring the wrong budget tier from "money no object"). The math engine is flawless, but it's currently limited by these weak LLM-seeded inputs. 
2. **Fragile Structured Outputs**: The model's native "guided JSON" feature was completely broken (returning truncated garbage). We had to work around it using plain-text JSON prompting and tolerant parsing. It works, but it feels brittle.
3. **Geocoding Rate Limits**: Nominatim is free but strictly caps us at 1 request/second. This makes ingesting large corpuses incredibly slow. It's fine for a demo, but completely unscalable for production volume.
4. **No Curation Pipeline Yet**: Right now, we ingest straight into Neo4j. The plan called for a Supabase layer where humans could review and edit the LLM-seeded scores *before* they go live. That doesn't exist yet, so we have no human oversight over the graph data.

## 🗺️ Where We Go From Here (Next Steps)

Based on what we learned, here is what we need to tackle next to truly scale this out:

- **Human-in-the-Loop Curation (High Priority)**: We desperately need to stand up the GCS → Supabase → Neo4j pipeline from the product plan. We cannot scale to 50 destinations relying purely on unverified LLM scores. Curators need a UI to tweak scores before publishing.
- **Upgrade the LLM**: We need to swap to a stronger model for score-seeding and structured output generation. 
- **Hotel Grouping**: We have the sub-locations ranked, but we still need to wire up the point-in-polygon logic to seamlessly group actual hotel inventory under them.
- **Commercial Geocoding**: Move off the public Nominatim endpoint to a self-hosted or paid provider so we aren't bottlenecked by the 1-req/sec limit.
- **Evaluation Harness**: Build a set of "golden" destination/preference pairs to automatically test if our ranking quality actually improves when we tweak the model or the math.

---

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
