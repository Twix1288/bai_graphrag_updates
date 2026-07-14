import os
import sys
import json
import uuid
import asyncio
import logging
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Load env variables
load_dotenv()

from src.clients import get_neo4j_client, get_embedding_client, get_redis_client, get_llm_client
from src.geocoding import Geocoder, NominatimClient
from src.ingestion import GraphIngestionPipeline
from src.sublocation_intel import seed_attribute_scores
from src.models.sublocation_attributes import ATTRIBUTES, score_property

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _build_gmaps_client():
    """
    Pick a geocoding backend. Google Maps is used only when explicitly opted in
    (GEOCODER=google) with a key present; otherwise the free, keyless OpenStreetMap
    Nominatim client is the default.
    """
    if os.getenv("GEOCODER", "nominatim").lower() == "google" and os.getenv("GOOGLE_MAPS_API_KEY"):
        import googlemaps
        logger.info("Using REAL Google Maps Client")
        return googlemaps.Client(key=os.getenv("GOOGLE_MAPS_API_KEY"))
    logger.info("Using OpenStreetMap Nominatim geocoder (keyless, <=1 req/s)")
    return NominatimClient()


# Fixed namespace for deterministic structured-entity IDs (stable across runs).
_STRUCTURED_NS = uuid.UUID("6f9b8c2e-0d3a-4e1b-9c7a-2f1e5d4c3b2a")


def structured_entity_id(pipeline: GraphIngestionPipeline, entity_type: str, name: str,
                         parent_id: Optional[str]) -> str:
    """
    Deterministic entity id keyed by (type, normalized name, parent). Distinct
    places that merely share a name — "North Shore" on two islands, or the
    SubLocation "Hana" vs the Attraction "The Road to Hana" — get DIFFERENT ids
    and never collapse. Re-ingesting the same node yields the same id (idempotent
    MERGE). This deliberately bypasses the fuzzy `resolve_or_create_alias` path,
    which is meant for deduping hotel mentions across blog posts, not for building
    a strict containment hierarchy.
    """
    key = f"{entity_type}|{pipeline._normalize_string(name)}|{parent_id or 'ROOT'}"
    return str(uuid.uuid5(_STRUCTURED_NS, key))


async def _upsert_domain_entity(
    pipeline: GraphIngestionPipeline,
    geocoder: Geocoder,
    *,
    name: str,
    domain_label: str,
    entity_type: str,
    extra_props: Dict[str, Any],
    geo_context: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> Optional[str]:
    """
    Create the canonical Entity for a structured node with a DETERMINISTIC id
    (see `structured_entity_id`), then stamp the domain label and properties.

    Structured nodes still become discoverable by the engine's
    `_resolve_entity_uuid`: they gain the secondary `Entity` label, a stable id,
    a geocoded spatial `location`, and a best-effort `Alias` (name embedding).
    Crucially, two structured nodes are NEVER merged into one — only nodes with
    the same (type, name, parent) share an id.

    Returns the canonical entity id.
    """
    # Geocode so downstream spatial queries (e.g. hotels-near-attraction) work.
    geo_res = await geocoder.resolve_location(name, geo_context)
    lat = geo_res["lat"] if geo_res else None
    lng = geo_res["lng"] if geo_res else None

    canonical_id = structured_entity_id(pipeline, entity_type, name, parent_id)

    # Deterministic MERGE by id. `domain_label` is from a fixed internal set,
    # never user input. `name` is kept for the name-scoped hierarchy queries.
    assignments = ["e.type = $type", "e.canonical_name = $name", "e.name = $name"]
    assignments += [f"e.{key} = ${key}" for key in extra_props]
    params: Dict[str, Any] = {"id": canonical_id, "type": entity_type, "name": name, **extra_props}
    if lat is not None and lng is not None:
        assignments += ["e.latitude = $lat", "e.longitude = $lng",
                        "e.location = point({latitude: $lat, longitude: $lng})"]
        params.update({"lat": lat, "lng": lng})
    merge_cypher = f"""
    MERGE (e:Entity {{id: $id}})
    SET e:{domain_label}, {", ".join(assignments)}
    """
    await pipeline.neo4j.execute_query(merge_cypher, params)

    # Best-effort discoverability alias (name embedding). Alias.normalized_name is
    # UNIQUE, so distinct same-named entities share one alias that resolves to
    # whichever was ingested first — acceptable for search-time resolution, and it
    # never merges the underlying entities.
    normalized = pipeline._normalize_string(name)
    name_embedding = await pipeline.embeddings.embed(normalized, input_type="passage")
    await pipeline.neo4j.execute_query(
        """
        MERGE (a:Alias {normalized_name: $nn})
        ON CREATE SET a.embedding = $emb
        WITH a
        MATCH (e:Entity {id: $id})
        MERGE (a)-[:RESOLVES_TO]->(e)
        """,
        {"nn": normalized, "emb": name_embedding, "id": canonical_id},
    )
    return canonical_id


async def _link(neo4j, child_id: str, parent_id: str, rel: str):
    """MERGE a `child-[:rel]->parent` relationship between two Entity nodes by id."""
    cypher = f"""
    MATCH (child:Entity {{id: $child_id}})
    MATCH (parent:Entity {{id: $parent_id}})
    MERGE (child)-[:{rel}]->(parent)
    """
    await neo4j.execute_query(cypher, {"child_id": child_id, "parent_id": parent_id})


async def _embed_sublocation(neo4j, embeddings, sub_id: str, descriptor: str):
    """Store a description embedding on the SubLocation (kept for semantic search;
    the primary ranking now uses the seeded attribute scores below)."""
    if not descriptor.strip():
        return
    # Stored/indexed text -> "passage" (matches alias/claim ingestion).
    embedding = await embeddings.embed(descriptor, input_type="passage")
    await neo4j.execute_query(
        "MATCH (e:Entity {id: $id}) SET e.embedding = $embedding",
        {"id": sub_id, "embedding": embedding},
    )


async def _seed_sublocation_scores(neo4j, llm, sub_id: str, name: str, category: str,
                                   description: str, insider_tip: str):
    """
    LLM-seed the fixed 0-10 attribute profile + price tier (final_check.md §5/§8)
    and store them as `score_<attr>` + `price_tier` properties for the
    deterministic ranker. Seeding failures degrade to a neutral profile.
    """
    seeded = await seed_attribute_scores(llm, name, category, description, insider_tip)
    assignments = [f"e.{score_property(a)} = ${a}" for a in ATTRIBUTES]
    params = {"id": sub_id, **{a: seeded["scores"][a] for a in ATTRIBUTES}}
    if seeded["price_tier"] is not None:
        assignments.append("e.price_tier = $price_tier")
        params["price_tier"] = seeded["price_tier"]
    await neo4j.execute_query(
        f"MATCH (e:Entity {{id: $id}}) SET {', '.join(assignments)}", params
    )


async def _ingest_attraction(pipeline, geocoder, attr: Dict[str, Any], parent_id: str, geo_context: str):
    """Create an attraction entity (geocoded) and link it to its parent location."""
    attr_name = attr.get("name")
    if not attr_name:
        return
    attr_id = await _upsert_domain_entity(
        pipeline, geocoder,
        name=attr_name,
        domain_label="Attraction",
        entity_type="attraction",
        extra_props={
            "description": attr.get("description", ""),
            "insider_tip": attr.get("insider_tip", ""),
        },
        geo_context=geo_context,
        parent_id=parent_id,
    )
    if attr_id:
        await _link(pipeline.neo4j, attr_id, parent_id, "LOCATED_IN")


async def ingest_structured_data(file_path: str):
    logger.info(f"Loading structured data from {file_path}")

    with open(file_path, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON file.")
            return

    neo4j_client = get_neo4j_client()
    embedding_client = get_embedding_client()
    llm_client = get_llm_client()
    redis_client = get_redis_client()
    geocoder = Geocoder(google_maps_client=_build_gmaps_client())
    pipeline = GraphIngestionPipeline(neo4j=neo4j_client, embeddings=embedding_client, redis_client=redis_client)

    islands = data.get("islands", [])
    logger.info(f"Found {len(islands)} islands to process.")

    for island in islands:
        island_name = island.get("island_name")
        if not island_name:
            continue

        logger.info(f"Processing Destination: {island_name}")

        # 1. Destination (Island)
        dest_id = await _upsert_domain_entity(
            pipeline, geocoder,
            name=island_name,
            domain_label="Destination",
            entity_type="destination",
            extra_props={
                "nickname": island.get("nickname", ""),
                "overview": island.get("overview", ""),
            },
        )
        if not dest_id:
            continue

        for region in island.get("regions", []):
            region_name = region.get("region_name")
            if not region_name:
                continue

            # 2. Region
            region_id = await _upsert_domain_entity(
                pipeline, geocoder,
                name=region_name,
                domain_label="Region",
                entity_type="region",
                extra_props={"vibe": region.get("vibe", "")},
                geo_context=island_name,
                parent_id=dest_id,
            )
            if not region_id:
                continue
            await _link(neo4j_client, region_id, dest_id, "PART_OF")

            for sub in region.get("sub_locations", []):
                sub_name = sub.get("name")
                if not sub_name:
                    continue

                # 3. SubLocation (note: descriptive type stored as `category` to
                #    avoid clobbering the coarse Entity `type`).
                sub_id = await _upsert_domain_entity(
                    pipeline, geocoder,
                    name=sub_name,
                    domain_label="SubLocation",
                    entity_type="sublocation",
                    extra_props={
                        "category": sub.get("type", ""),
                        "description": sub.get("description", ""),
                        "insider_tip": sub.get("insider_tip", ""),
                    },
                    geo_context=island_name,
                    parent_id=region_id,
                )
                if not sub_id:
                    continue
                await _link(neo4j_client, sub_id, region_id, "PART_OF")

                # Embed the sub-location (semantic search) ...
                descriptor = " ".join(filter(None, [
                    sub_name, sub.get("type", ""), sub.get("description", ""), sub.get("insider_tip", "")
                ]))
                await _embed_sublocation(neo4j_client, embedding_client, sub_id, descriptor)
                # ... and LLM-seed its attribute profile for the deterministic ranker.
                await _seed_sublocation_scores(
                    neo4j_client, llm_client, sub_id, sub_name,
                    sub.get("type", ""), sub.get("description", ""), sub.get("insider_tip", ""),
                )

                # Attractions inside the sub-location
                for attr in sub.get("attractions", []):
                    await _ingest_attraction(pipeline, geocoder, attr, sub_id, geo_context=sub_name)

        # Some datasets put attractions under the island directly
        for attr in island.get("attractions", []):
            await _ingest_attraction(pipeline, geocoder, attr, dest_id, geo_context=island_name)

    logger.info("Structured ingestion complete!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/ingest_structured_data.py <path_to_json>")
        sys.exit(1)

    file_path = sys.argv[1]
    asyncio.run(ingest_structured_data(file_path))
