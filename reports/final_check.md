bAI Sub-Location Intelligence
Product and Technical Plan
Draft for team review  |  July 2026


1. Problem
Today the funnel is: traveler inputs (budget, likes and dislikes, family size, dates, origin) lead to destination matches like Maui or Cancun. Then we search hotels within that destination.
The missing layer is sub-location. Maui is not one place. Lahaina, Ka'anapali, Kapalua, Wailea, Kihei, Hana and Paia are different products at different price points. A family that loves snorkeling and casual food has a very different best answer than a family that wants a quiet luxury resort. Today we make them figure that out on their own, or we show a flat hotel list that mixes a $180 Kihei condo with an $850 Wailea resort.
Every big OTA has this same blind spot. Fixing it is a real differentiator and it strengthens the empathy-based recommendation story behind our patents.
2. Goal
When a traveler selects a destination, show its sub-locations ranked by fit to their stated preferences, with a plain-English reason for each ranking, and with hotels grouped under the sub-location they sit in.
Success looks like: a family sees "Ka'anapali is your best fit: great snorkeling right off the beach, walkable restaurants, mid-range resort pricing" instead of a wall of hotels.
3. Approach Overview
Add a SubLocation layer to the knowledge graph between Destination and Hotel. Each sub-location carries a scored attribute profile (beach, snorkeling, food scene, nightlife, family friendliness, walkability and more), a price tier, best-for tags and honest tradeoffs. The traveler preference vector we already collect is then scored against sub-location profiles, the same way destination matching works today.
This is deliberately a curation problem, not a big data problem. Fifty destinations at 8 to 12 sub-locations each is roughly 500 records. LLM-seeded, human-verified, published to the graph.
4. Data Model
SubLocation node
Identity: id, name, destination
Geometry: polygon where available, otherwise centroid plus radius
Price: tier 1 to 4, typical nightly range by season
Attribute scores (0 to 10): beach, snorkeling, food scene, nightlife, family friendly, walkability, quiet, luxury, adventure, culture
Family specifics: kid fit by age band, grocery access, car needed, drive minutes from airport
Editorial: best-for tags, honest tradeoff one-liners, seasonality notes
Provenance: last verified date, sources, reviewer
Relationships
Destination HAS_SUBLOCATION SubLocation
Hotel LOCATED_IN SubLocation
SubLocation NEAR POI (anchor points like Molokini or Front Street)
SubLocation EVIDENCED_BY CreatorContent (Phase 4, licensed content only)
Hotel assignment
Amadeus and LiteAPI return hotel coordinates. Assign each hotel to a sub-location by point-in-polygon, with nearest-centroid fallback. At our scale this is a Python script with shapely, run at ingest time and cached. Hotels outside all sub-locations land in an "Other areas" bucket so no inventory disappears.
5. Data Sourcing
Layer the sources by what each is good at. Objective data corrects subjective opinion.

Layer
Source
What it gives us
Taxonomy
Wikivoyage districts, supplier area codes, editorial judgment
What the sub-locations are and how to split them the way a family experiences them
Geometry
OpenStreetMap boundaries via Overpass API
Polygons and centroids for hotel assignment and maps
Subjective scores
LLM-seeded against fixed schema, human-verified with a rubric
Attribute profiles: snorkeling 9, nightlife 3, and the honest tradeoff copy
Objective validation
Median nightly rates from our own LiteAPI and Amadeus pulls; POI density from OSM or Google Places
Price tiers from real data; sanity checks on scores (a food scene of 8 with 4 restaurants is a flag)
Creator content
Licensed creator blogs, vlogs, audio (see Section 6)
Family-specific texture no OTA has: crowd timing, stroller reality, which end of the beach is calm
Our own bookings
Post-launch feedback loop
Which sub-locations families like this one actually book and rate well. This becomes the moat


Licensing notes: OSM and Wikivoyage need simple attribution (a data credits line covers it). Google Places has strict caching rules, so we store derived counts and scores, never raw Places content.
6. Creator Content Pipeline
Creator content answers the weakness in every other source. Wikivoyage tells us Ka'anapali exists. OSM tells us it has 23 restaurants. Only a creator tells us the snorkeling at Black Rock is great in the morning but the beach is packed by 10 and parking is hard with a stroller. This ties directly into the creator ecosystem patent.
What it feeds
Score evidence. Multiple creators independently praising an area raises confidence in a score. Disagreement with our seeded score triggers human review.
Attributes we cannot get elsewhere. Stroller friendliness, crowd timing, kids menu quality, parking reality.
Explanation grounding. "Families consistently mention the morning snorkeling at Black Rock" is a stronger why-line than generic prose, and it can credit the creator.
Pipeline design
Ingest to GCS. Blog HTML, video transcripts, audio transcripts as raw files with URL, date and license status. Vlogs and audio go through speech-to-text first, using the same infrastructure that already powers Zara.
Extract structured claims, not prose. An LLM pass turns each piece into rows: sub-location, attribute, sentiment, claim text, family context, recency, source. Claims land in a creator_claims table and become queryable evidence.
Aggregate into scores. Claims never write scores directly. They aggregate into a confidence signal (claim count, sentiment mix, recency, creator credibility). Disagreement with the curated score routes to a human. This keeps one bad extraction or one outlier creator from polluting the graph.
Recency decay. Claims are weighted by age. A 2019 Lahaina post is not just stale, it is wrong. Decay handles this structurally.
The legal line
Licensed creators (our ecosystem): full pipeline. Store transcripts, quote with attribution, feature in the UI.
Public content without agreement: aggregate signal only. No verbatim storage or display. Unlicensed YouTube transcripts are a gray zone, so treat them as signal at most.
This constraint doubles as a business development funnel: any creator whose public content keeps scoring as high-value evidence is exactly who we invite into the creator program.
7. Storage Architecture
Three layers, each doing the one job it is good at. Neo4j is a serving layer, not the system of record. The graph must always be rebuildable from source data.

Layer
Holds
Why here
GCS (raw files)
Wikivoyage dumps, OSM extracts, rate snapshots, creator transcripts. Path convention raw/{source}/{destination}/{date}
Cheap, versioned, immutable provenance. Fetched once, reprocessed when the rubric changes. We already use GCS for hotel images
Supabase (working set)
One small table set: sub_locations with geometry, scores with provenance and status, creator_claims. Roughly 500 sub-location rows
This is what humans edit and workflows query. Row-level state for the intern verification flow (draft, verified, approved, reviewer, last_verified). Simple admin UI in an afternoon. SQL joins for the price-tier validation
Neo4j (serving)
Approved records only: final scores, tags, price tier, copy, centroid, relationships to Destination, Hotels, and licensed CreatorContent
What the LangGraph resolver reads at request time. Published from Supabase by a small ETL job on approval. Fast, clean, rebuildable


The rule of thumb: if a piece of data gets edited by a human or queried by a workflow, it is a row in Supabase. If it is fetched once and reprocessed occasionally, it is a file in GCS. Runtime never touches raw files or working tables, which keeps serving fast and keeps the curation mess out of the request path.
8. Ranking Engine
Preference mapping
The traveler already gives us budget, likes and dislikes, family size and dates. These map to attribute weights: "we love snorkeling" raises the snorkeling weight, kids under 5 raise family friendliness and grocery access and strengthen the airport-drive penalty, budget acts as a hard filter plus a soft penalty on tier mismatch in both directions, and dates apply seasonality adjustments.
Scoring
A weighted dot product of preference weights against attribute scores, minus penalties. Deterministic and inspectable. The LLM is used only to translate free-text likes and dislikes into the weight vector and to write explanation copy. It is not used for the ranking math. A formula is fast, cheap, debuggable and defensible in the patent narrative. An LLM-ranked list is none of those.
Explainability: the empathy layer
Every ranked sub-location ships with a one-line "why this fits you" tied to stated preferences, one honest tradeoff, and a price signal relative to budget. Honest tradeoffs are the trust builder. "Wailea has the best beaches but dining is resort-priced" reads like a friend, not a booking engine.
9. Surfaces
ChatPlanning UI
Ranked sub-location cards after destination selection: name, match indicator, price tier, 2 to 3 best-for tags, one tradeoff line, image, map position
Selecting a card filters hotels to that sub-location, ranked by existing hotel preference logic
"Other areas" always reachable so we never hide inventory
Optional side-by-side compare for the top 2 to 3 sub-locations
Zara (voice)
Voice is where this shines. Instead of reading a hotel list, Zara can say: "Maui has a few distinct areas. For your crew, I would start with Ka'anapali. Snorkeling right off the beach and you can walk to dinner. Wailea is the upgrade pick if you want quieter luxury, but it runs above your nightly budget. Want to hear hotels in Ka'anapali first?" No new voice infrastructure needed, just the ranked output and explanation copy feeding the existing agent.
LangGraph
Add a sub-location resolver node between the destination agent and the hotel agent. Destination selected, resolver pulls profiles from Neo4j, scores against the preference vector, returns a ranked list with explanations, hotel agent queries within the chosen sub-location's geo bounds.
10. Phased Plan
Phase 1: Foundation (2 to 3 weeks)
Finalize SubLocation schema and the scoring rubric (what makes snorkeling a 9 vs a 6)
Pick 10 pilot destinations from actual beta family demand
Ingest raw sources to GCS, LLM-seed profiles, human verify in Supabase, publish to Neo4j
Build hotel-to-sub-location geo assignment at ingest
Phase 2: Ranking and UI (2 to 3 weeks, overlaps Phase 1)
Preference-to-weights mapper and scoring function
Sub-location cards in ChatPlanning, hotel filtering by sub-location
Explanation copy with the honest-tradeoff format
Phase 3: Zara integration (1 to 2 weeks)
Resolver node in LangGraph
Voice patterns for presenting 2 to 3 sub-locations conversationally
Phase 4: Scale and learn (ongoing)
Expand to 50 destinations; quarterly re-verification cadence with event-driven exceptions
Price-tier validation against live rate data
Creator claims pipeline, starting with licensed ecosystem creators on the 10 pilot destinations
Booking and feedback loop into scores
Out of scope for now
Global coverage beyond curated destinations
Real-time review scraping
User-generated sub-location ratings (later, once volume exists)
One exception worth pulling forward: if we onboard even 5 to 10 family travel creators for the ecosystem anyway, run their content through extraction early. Small volume, fully licensed, and it gives us creator-grounded explanations for the Demo Day and investor story: recommendations built from real family experiences, not aggregated star ratings.
11. Metrics
Sub-location card engagement rate after destination selection
Hotel click-through and booking conversion vs the current flat-list flow
Time from destination selection to hotel shortlist
Post-trip "was this area a good fit" signal
Drop in "which part of X should we stay in" questions in chat and support
12. Risks and Mitigations
Stale or wrong scores. Human verification, price cross-check against live rates, quarterly refresh, event-driven exceptions (the Lahaina fire is the template case).
Curation load grows with destinations. Rubric plus intern workflow keeps it cheap. 500 records is manageable. We should resist solving this with a giant pipeline first.
Hotels straddling boundaries. Nearest-centroid fallback and the Other areas bucket so inventory never vanishes.
Thin markets. If a sub-location has too few bookable hotels for the dates, merge it visually with its neighbor rather than showing an empty state.
Creator data quality. Claims aggregate into confidence signals, never write scores directly. Recency decay. Disagreement routes to a human.
Licensing. Verbatim creator content only under agreement. Attribution lines for OSM and Wikivoyage. Derived data only from Google Places.
Sensitive local context. Some areas carry real-world weight. Copy tone rules: factual, respectful, current.
13. Decisions Needed
Sub-location layer before hotels (extra step) or alongside them (grouped list)? Recommendation: grouped list first, since it adds no friction.
Polygon source per destination: OSM boundaries, hand-drawn, or radius-only for v1?
Should sub-location fit affect destination ranking upstream? A destination whose best sub-location fits poorly may deserve a lower rank.
Which 10 pilot destinations, based on beta family demand data?
Rubric ownership: who signs off on scores, and do interns do first-pass verification?
Which 5 to 10 ecosystem creators to run through the claims pipeline first?
