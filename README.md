# Sub-Location Intelligence (GraphRAG)

This is my build-out of the `final_check.md` product plan. The problem it goes after is that we treat a big destination like "Maui" as one place. A family that wants quiet luxury and a family that wants cheap snorkeling and casual food both get the same flat hotel list. The fix is a sub-location layer (Lahaina vs. Ka'anapali vs. Wailea) that ranks the areas inside a destination against what the traveler actually asked for, gives a plain-English reason for each ranking, and groups the matching hotels underneath.

This README is my account of how I built it against the plan, why the approach holds up, what works today, what doesn't yet, and the limitations I hit. The honest summary: after a fair amount of fighting with the data and the free tooling, the full flow runs end to end and gives a real, explainable answer.

## How it works

The most important decision comes straight from the plan (section 8): the LLM never does the ranking math. The system is split into two halves because of that.

The deterministic core has no AI in it. Every sub-location carries a fixed profile of ten 0-10 attribute scores (beach, snorkeling, food scene, nightlife, family-friendliness, walkability, quiet, luxury, adventure, culture) plus a price tier from 1 to 4. Ranking is a weighted dot product of the traveler's preference weights against those scores, minus a budget penalty. It's about 30 lines of plain Python in `src/ranking.py`, it's unit-tested, and you can read exactly why any place ranked where it did.

The LLM only does three things at the edges, all of them jobs a language model is actually good at:

1. Seed the attribute scores from each place's editorial text, once, at ingest time.
2. Turn the traveler's free text into a weight vector and a budget tier.
3. Write the copy: the "why this fits you" line, the honest tradeoff, and the conversational lead-in.

End to end, the flow is: load the structured islands data, geocode it, build the `Destination -> Region -> SubLocation` graph in Neo4j with hotels and activities linked to their sub-location, seed the attribute scores, and then at query time map preferences to weights, rank the candidates, group the hotels under each winner, and let the LLM phrase the result.

## Why the deterministic approach

The easy version of this feature is to hand the candidates to an LLM and ask it to rank them. I didn't do that, for a few reasons:

- You can see why something ranked where it did. A budget penalty or a low score shows up in the output (7.5 dropping to 6.25, for example), so a ranking can be checked and defended. An LLM ranking can't really be audited.
- It's cheap and fast. The ranking is arithmetic, so it costs nothing per query, and the expensive LLM work happens once at ingest rather than on every request.
- It's stable. The same request gives the same order every time, which you need for a real product feature and for the patent story.

## Efficiency

A query is mostly I/O, not inference. There are at most two LLM calls per query (preferences to weights, then the narration) and none for the ranking itself. Scoring is a handful of multiply-adds per candidate. Score seeding runs once at ingest. I also added a disk-backed geocode cache, so the first ingest pays the geocoding cost once and every re-ingest after that is close to instant.

## What works today

The whole flow runs against a local Neo4j with the real Hawaii dataset: 6 islands, 116 entities, and all 11 hotels and 9 activities linked to their sub-locations. Here's a verbatim transcript of a live run (`python3 -m src.subloc_chat`):

```
Destination: O'ahu
What are you looking for? luxury beachfront resort with great food and nightlife, money is no object

Ranking...

1. "Kailua & Kaneohe, often ranked highly for its off-grid luxury retreats, comes in
   first place in our selection. With a fit_score of 7.0, it offers pristine snorkeling,
   family-friendly options, and upscale amenities near Kaneohe Bay Airport. However,
   expect occasional noise and traffic from the nearby airport outside the resort."

2. "Haleiwa, nestled between the Koolau Mountains and the Pacific Ocean, may be a bit
   less upscale compared to Waikiki and Kaneohe but still delivers numerous family-friendly
   activities, a stunning beach, and decent food options. Its close proximity to the North
   Shore's surf culture makes it a popular choice among locals and visitors alike."

3. "Waikiki, home to famous Waikiki beach, offers a world-class luxury resort experience
   with top-notch entertainment, upscale food scene, and walking distance to the beach.
   While the fit_score drops to 6.5, its central location in Honolulu makes it easily
   accessible while providing a more premium experience compared to Haleiwa."

Best-fit areas in O'ahu  (your budget tier: 4/4)

  1. Kailua & Kaneohe
       match  #######...  7.0/10        $$$ (tier 3/4)
       why:      Offers great food and nightlife with great snorkeling and family-friendly options, making it a luxurious resort that fits your criteria
       heads-up: Located near a busy airport, potential noise and traffic congestion outside the resort

  2. Haleiwa
       match  #######...  7.0/10        $$$ (tier 3/4)
       why:      Numerous family-friendly activities, stunning beaches, and good food options, making it a popular choice for locals and visitors alike
       heads-up: Less upscale accommodations compared to Waikiki and Kaneohe

  3. Waikiki
       match  ######....  6.5/10        $$$ (tier 3/4)
       why:      World-class luxury resort with a vibrant food scene, top-notch entertainment, and walking distance to famous Waikiki beach
       heads-up: More expensive than other nearby areas, potential congestion and higher noise levels due to its central location in Honolulu
       hotels here (3):
          - Queen Kapiolani Hotel  $$$ - Boutique / Mid-range
          - Moana Surfrider, A Westin Resort  $$$$ - Luxury / Historic
          - The Royal Hawaiian  $$$$ - Luxury / Historic
       things to do: Outrigger Canoe Surfing
```

That covers what the plan calls the core loop: the sub-location ranking, the budget-aware penalty, the reason and tradeoff copy, the conversational lead-in, and the hotel grouping that closes the funnel. There are 46 tests over the ranking math, the budget logic, price-tier derivation, hotel grouping, injection safety, and the deterministic IDs.

## What doesn't work yet

Measured against `final_check.md`:

- The three-layer curation pipeline (section 7). Scores go straight into Neo4j right now. The plan wants GCS for raw files, Supabase as a human-verified working set, and Neo4j as the serving layer. Without it there's no human review, no provenance, and no clean rebuild path. This is the biggest gap before scaling.
- Point-in-polygon hotel assignment (section 4). The code is in `src/geocoding.py` but isn't used. Our data is already nested, so hotels are pre-assigned; the polygon path only matters once we pull flat, unassigned hotel lists from a provider like Amadeus.
- The creator-content claims pipeline (section 6). Out of scope so far.
- A ranking-quality eval harness: a set of destination and preference pairs with expected orderings, so we can tell whether a stronger seeding model actually improves the results.

## Limitations

Two things capped how good this could get, and both come back to running on free tooling rather than anything wrong with the design.

- The free LLM is the quality ceiling and it struggles with structured output. I used a free 4B model (NVIDIA nemotron-mini-4b). Its structured-output mode returned truncated, unusable JSON, so I fell back to plain JSON prompting with tolerant parsing and value clamping. It also produces weak results: flat attribute scores that often default to a neutral 5, and shaky budget reads (it read "money is no object" as tier 2). I worked around the budget problem with a deterministic keyword check that correctly resolves it to tier 4, but the seed-score quality is bounded by the model. Because the ranking is separate from the LLM, better inputs (a stronger seeding model plus the section 7 human review step) improve quality without touching the engine. Free geocoding is the other cap: keyless OpenStreetMap Nominatim is limited to one request per second, which is fine with the cache for a demo but not for production volume, and it needed query normalization before it would resolve Hawaiian place names at all.
- A data-collapse bug that only showed up on real data. My first attempt at unifying the schema sent structured places through a resolver meant for deduplicating hotel mentions across blog posts, which merges on name similarity. Ingesting the real data collapsed 88 distinct places into 21 nodes: "O'ahu" ended up as a Destination, Region, SubLocation, and Attraction at once, and the two different "North Shore" regions merged into one. I fixed it by giving structured entities deterministic IDs keyed by (type, name, parent) and dropping the name-uniqueness constraints that legitimately repeated names were violating. After that the hierarchy was clean, nothing collapsed, and both "North Shore" regions survived. It only turned up because I tested against the real dataset instead of a toy fixture.

## Running it locally

Neo4j 5.18 or newer is required (for `vector.similarity.cosine`).

```bash
# 1. Infrastructure
docker run -d --name graphrag-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=<user>/<pass> neo4j:5.24-community
docker run -d --name graphrag-redis -p 6379:6379 redis:7-alpine

# 2. Schema and data. The first ingest takes a few minutes because Nominatim is
#    capped at one request per second; re-ingests are fast thanks to the cache.
docker cp setup_neo4j.cypher graphrag-neo4j:/tmp/setup.cypher
docker exec graphrag-neo4j cypher-shell -u <user> -p <pass> -f /tmp/setup.cypher
python3 -m src.ingest_structured_data data/sample_scraped_data.json

# 3. The interactive planner
PYTHONPATH=. python3 -m src.subloc_chat

# 4. Tests
python3 -m pytest tests/
```
