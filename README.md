# GraphRAG Sub-Location Intelligence: An Investigation

I originally outlined a product plan to move beyond generic destination matching. Instead of dropping travelers into a massive list of hotels in "Maui", I wanted a recommendation engine that understands sub-locations (like Ka'anapali vs. Wailea), ranks them based on user preferences, and explains why a place fits them.

This document serves as an investigation into the viability of that plan. I have implemented the core of this system to evaluate how it works in practice, identify its limitations, and determine how the model and architecture can be improved.

## What I Implemented

1. **Deterministic Ranking Engine**: I built a system that translates free-text preferences into weights, scores them against a 10-attribute schema, applies a budget filter, and penalizes price mismatches. It is fast, debuggable, and avoids LLM hallucination during the ranking step.
2. **Fixed Data Collapse**: When ingesting the Hawaii dataset, 88 places were collapsing into 21. I implemented deterministic IDs keyed by `(type, normalized name, parent)` so overlapping names coexist perfectly.
3. **Security & Correctness**: I closed a live Cypher injection vulnerability by parameterizing queries, fixed silent driver timeouts, enforced TLS verification for embeddings, and corrected a major routing bug so destinations actually hit the sub-location ranker.
4. **Keyless Geocoding**: I integrated OpenStreetMap Nominatim, added query normalization, and geocoded ~83% of the entities.

## Limitations Encountered

1. **LLM Seeding Bottleneck**: I used a small 4B-parameter model to "seed" the 0-10 attribute scores for each sub-location. The model sometimes returns neutral or incorrect values. 
2. **Fragile Structured Outputs**: The model's native structured output feature was broken. I had to work around it using plain-text JSON prompting and tolerant parsing, which feels brittle.
3. **Geocoding Rate Limits**: Nominatim caps requests at 1/second. This makes ingesting large corpuses too slow for production volume.
4. **No Curation Pipeline**: I am currently ingesting straight into Neo4j. The plan called for a Supabase layer where humans could review LLM-seeded scores before publishing, which does not exist yet.

## Investigation & Evaluation

### How the Model Works in Practice
Through end-to-end testing, the deterministic math engine proves to be highly effective when given accurate inputs. Because scoring is a plain weighted sum with explicit penalties rather than an opaque model judgment, every result can be explained and reproduced. For example, a sub-location with a higher raw fit score correctly ranks *below* a slightly lower-fit sub-location if it violates the traveler's budget constraints. 

However, the evaluation reveals a critical dependency: **the system is only as good as its seeded scores.** Because the 4B-parameter model struggles to consistently infer accurate attribute scores from unstructured text (e.g., misinterpreting "money is no object" as a low budget tier), the final rankings can suffer despite the math being flawless.

### How It Can Be Better
To make this system truly production-ready, the architecture needs to evolve:
1. **Model Upgrade**: Swap the 4B-parameter model for a more capable LLM with reliable structured JSON output to drastically improve the accuracy of the initial attribute seeding.
2. **Human-in-the-Loop Validation**: Stand up the GCS → Supabase → Neo4j pipeline so human curators can review and correct the seeded scores before they impact live rankings.
3. **Formal Evaluation Harness**: Build a golden dataset of destination/preference pairs to continuously and programmatically evaluate ranking accuracy as models are swapped.

### Rating the Plan
**Viability Rating: 8/10**
The core concept—separating LLM text extraction from deterministic mathematical ranking—is highly successful and solves the explainability and hallucination problems native to standard RAG applications. The architecture is sound. The remaining 20% to reach production readiness requires operational maturity: better underlying models for data extraction and a proper human-in-the-loop curation pipeline.

---

## Running It Locally

Neo4j 5.18+ is required for `vector.similarity.cosine`.

```bash
# 1. Infrastructure
docker run -d --name graphrag-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=<user>/<pass> neo4j:5.24-community
docker run -d --name graphrag-redis -p 6379:6379 redis:7-alpine

# 2. Schema and Data
docker cp setup_neo4j.cypher graphrag-neo4j:/tmp/setup.cypher
docker exec graphrag-neo4j cypher-shell -u <user> -p <pass> -f /tmp/setup.cypher
python3 -m src.ingest_structured_data data/sample_scraped_data.json

# 3. Interactive Chat Planner
PYTHONPATH=. python3 -m src.subloc_chat
```

### Tests
I wrote 27 new tests covering the ranking math, injection safety, and routing:
```bash
python3 -m pytest tests/
```
