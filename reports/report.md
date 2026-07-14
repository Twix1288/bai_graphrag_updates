# GraphRAG Sub-Location Intelligence — Engineering Report

**Author:** Rishit Agnihotri
**Date:** 14 July 2026
**Audience:** Engineering management

---

## TL;DR

We took the GraphRAG travel engine from a demo scaffold with real correctness bugs
to a system that runs end-to-end on live infrastructure and implements the core of
the Sub-Location Intelligence product plan. We closed every finding from the prior
security/quality audit, fixed a data-integrity bug that live testing exposed (88
distinct places were silently collapsing into 21), and built the deterministic
ranking engine the product vision calls for. A traveler can now pick a destination,
describe their trip in plain English, and get its sub-locations ranked by fit —
each with a price tier, a "why this fits you" line, and an honest tradeoff.

The approach is sound and the system genuinely runs. It is **not yet fully
production-ready**: ranking quality is currently limited by the small model doing
the score-seeding, and several product surfaces (hotel grouping, the curation
pipeline, creator content) are deliberately out of scope for this pass. Those are
scoped in Section 6. Test suite: **27 passing.**

---

## 1. What We Set Out to Do

Three documents drove this work:

1. `system_audit_report.md` — a prior audit flagging four correctness bugs.
2. `audit_to_production.md` — a plan to close three HIGH-severity production
   blockers and three medium gaps.
3. `final_check.md` — the product/technical plan for Sub-Location Intelligence.

The brief was to make the system behave according to those documents "or better,"
and to be able to test the chat experience against real data.

---

## 2. What We Did

### 2.1 Closed the audit findings

| Finding | Resolution |
|---|---|
| Sub-location ranking returned an identical score for everything | Replaced with a real ranking engine (§2.5) |
| Structured data was invisible to the query engine (no `Entity` label, UUID, or alias) | Structured nodes unified into the graph with stable IDs |
| Structured attractions were never geocoded | Geocoding wired into structured ingestion |
| Distributed lock could deadlock on a crash | Lock now self-heals via a TTL applied at acquisition |

### 2.2 Hardened the production blockers

- **Cypher injection** in the query-fallback path was closed by parameterizing user
  input. Verified live: a `DETACH DELETE` payload sent through the engine deleted
  nothing.
- **Query timeout** that the driver was silently dropping is now correctly applied
  server-side, bounded at 5 seconds, by wrapping the statement in a `neo4j.Query`
  object rather than passing an unrecognized config kwarg.
- **Routing bug** — every resolvable destination was skipping the sub-location
  ranker (it only ran on resolution *failure*). Fixed with a graph probe that
  respects the actual `Destination → Region → SubLocation` shape.
- **TLS verification**, previously disabled and exposing the API key, now verifies
  against a portable CA bundle — secure *and* working on machines with an
  incomplete system trust store (the original reason it was turned off).
- Embedding calls now use the correct query/passage input types; dependencies and
  schema documentation were corrected.

### 2.3 Wired keyless geocoding

We integrated **OpenStreetMap Nominatim** — no API key, respecting the
1-request-per-second usage policy with a proper contact header — replacing a Google
Maps key that was never activated. Query normalization (stripping diacritics,
parentheticals, and slashes) plus a bare-name fallback took geocoding coverage from
near-zero to ~83% of entities (75 of 90).

### 2.4 Fixed a data-integrity bug that live testing exposed

This was the most important finding of the cycle. When we ingested the real Hawaii
dataset, **88 distinct places collapsed into 21 entities** — "O'ahu" ended up
labeled simultaneously as a Destination, Region, SubLocation, and Attraction. The
hierarchy was corrupt and queries returned nothing.

Root cause: the audit's schema-unification routed structured places through a
resolver built for deduplicating *hotel mentions across blog posts*, which merges on
name similarity alone. It collapsed the two different "North Shore" regions (one on
O'ahu, one on Kaua'i) and near-duplicate names.

We fixed it by giving structured entities **deterministic IDs keyed by (type,
normalized name, parent)**, bypassing the fuzzy resolver entirely, and removing the
name-uniqueness constraints that were incompatible with legitimately repeated names
(identity is the `id`, not the name). Result: **90 clean entities, zero collapses,
and both "North Shore" regions coexisting.**

### 2.5 Built the deterministic ranking engine (the product core)

Per `final_check.md` §8, the ranking is a **deterministic weighted dot product** of a
traveler's preference weights against a sub-location's 0–10 attribute scores (beach,
snorkeling, food scene, nightlife, family-friendliness, walkability, quiet, luxury,
adventure, culture), minus a price penalty. The language model is used *only* to
translate free text into weights, seed attribute scores from editorial text, and
write the explanation copy — **never for the ranking math itself.** That is what
keeps the recommendation fast, cheap, debuggable, and defensible.

New modules:

- `src/ranking.py` — the pure ranking math plus a budget hard-filter and a soft
  penalty for tier mismatch in either direction. No LLM; fully unit-tested.
- `src/models/sublocation_attributes.py` — the fixed 10-attribute schema.
- `src/sublocation_intel.py` — the three narrow LLM jobs (seed, map preferences,
  write copy), each with a graceful non-LLM fallback.
- `src/engine.py` — the sub-location resolver, rewired onto the deterministic ranker.
- `src/subloc_chat.py` — the ChatPlanning surface (§9): pick a destination, describe
  your trip, get ranked cards.

One integration note worth flagging: the model's structured-output ("guided JSON")
feature is **broken** on the current NVIDIA model — it returned truncated garbage. We
worked around it with plain-text JSON prompting and tolerant parsing, which is
reliable.

### 2.6 Tested it

- **27 unit tests** covering the ranking math, injection safety, routing, ingestion
  dedup, the client layer, and deterministic IDs.
- **Live end-to-end validation** on Dockerized Neo4j + Redis with the real Hawaii
  dataset and live embedding/geocoding APIs.

---

## 3. Evidence It Works

- **27/27 tests pass.**
- All 21 sub-locations were seeded with attribute scores and price tiers, with zero
  seeding failures.
- The ranking behaves exactly as specified, penalties included. For O'ahu with a
  "mid budget" request, **Kailua (raw fit 7.5) correctly ranks *below* Waikiki (fit
  6.5)** because Kailua is price tier 3 against a budget tier of 2, so a −1.25
  penalty drops its total to 6.25. Every number is traceable — no black box.

---

## 4. What's Working Well

- **The ranking is honest and inspectable.** Because scoring is a plain weighted sum
  with explicit penalties rather than an opaque model judgment, every result can be
  explained, reproduced, and defended. This is a genuine product and
  patent-narrative asset, not just an engineering nicety.
- **Clean separation of concerns.** The LLM is fenced into three well-defined jobs;
  the ranking, data model, and serving path never depend on model output being
  correct, so a weak model degrades quality gracefully instead of breaking the
  system.
- **The graph is now trustworthy.** Clean hierarchy, distinct entities, and
  idempotent re-ingestion.
- **The security posture is solid.** Injection is closed and verified against a live
  database; TLS is properly enforced.
- **It genuinely runs.** This stands up on real infrastructure and answers real
  queries — not slideware.

---

## 5. Critiques and Risks at Scale

Being candid about where this would strain if scaled as-is:

1. **Score quality is bottlenecked by the seeding model.** Attribute scores are
   seeded by a small 4B model that sometimes returns neutral or off values (e.g.
   inferring the wrong budget tier from "money no object"). The *engine* is correct;
   the *inputs* are weak. At 500 sub-locations this becomes the dominant quality
   risk. The plan already anticipates this — scores are meant to be human-verified —
   but we should not ship unverified LLM scores at scale.

2. **No curation/publishing pipeline yet.** The plan calls for raw files in GCS → an
   editable working set in Supabase → a serving layer in Neo4j, with the graph
   rebuildable from source. Today we ingest straight into Neo4j: no human review, no
   provenance, no clean rebuild path.

3. **Geocoding is rate-limited.** The public Nominatim endpoint caps us at 1
   request/second — slow for a large corpus and not appropriate for production
   volume. A self-hosted geocoder or paid provider is needed at scale.

4. **The provider integration is fragile.** The model's structured-output feature is
   broken, forcing a plain-text workaround. It is reliable but brittle; a stronger
   model with dependable structured output would remove a class of failure. There is
   also no abstraction to route different tasks to different models.

5. **Query-path coverage is uneven.** The sub-location path is well tested
   end-to-end; the hotel-oriented paths (by-topic, near-attraction, vibe summary) are
   unit-tested but never exercised against real data, because the current dataset has
   no hotel/review content.

6. **Operational edges are rough.** Async clients aren't closed cleanly on exit (a
   harmless but visible warning), and there's no connection-pooling story for
   concurrency yet. Minor, but the kind of thing that accumulates.

---

## 6. Recommended Next Steps

In rough priority order:

1. **Upgrade the score-seeding model and add the human-verification loop.** The
   single highest-leverage improvement: seed with a stronger model, then route scores
   through a review step before they reach the serving graph.
2. **Stand up the GCS → Supabase → Neo4j pipeline** so the graph is rebuildable from
   source and curators have an editing surface. This unblocks safe scaling to 50
   destinations.
3. **Build hotel grouping under sub-locations.** Wire the existing point-in-polygon
   assignment code and ingest a real hotel dataset so the full experience works.
4. **Move geocoding off the public endpoint** (self-hosted Nominatim or a commercial
   provider) ahead of real ingestion volume.
5. **Add an evaluation harness for ranking quality** — golden destination/preference
   pairs with expected orderings — so we can measure whether score and weight quality
   improve as we change models.
6. **Tidy the operational edges** — clean async teardown, structured logging, and a
   stronger structured-output path.

---

## 7. How to Run It

```bash
# Infrastructure (Docker) — Neo4j 5.18+ is required for vector.similarity.cosine
docker run -d --name graphrag-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=<user>/<pass> neo4j:5.24-community
docker run -d --name graphrag-redis -p 6379:6379 redis:7-alpine

# Schema + data
docker cp setup_neo4j.cypher graphrag-neo4j:/tmp/setup.cypher
docker exec graphrag-neo4j cypher-shell -u <user> -p <pass> -f /tmp/setup.cypher
python3 -m src.ingest_structured_data data/sample_scraped_data.json

# Tests
python3 -m pytest tests/

# Interactive sub-location planner
PYTHONPATH=. python3 -m src.subloc_chat
```

---

## 8. Bottom Line

The foundation is sound: the ranking engine matches the product vision, the graph is
clean, and the system runs end-to-end. The remaining work is about **quality and
operational maturity** — better score inputs with human verification, the curation
pipeline, and the hotel layer — not about rethinking the approach. We are well
positioned to move from "it works on a demo dataset" to "ready for the first 10 pilot
destinations."
