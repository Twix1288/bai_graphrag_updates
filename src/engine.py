import json
import logging
from typing import Dict, Any, List
# Pseudo-imports for the mocked graph engine
from src.models.query_tools import (
    FindHotelsNearAttractionSchema,
    FindHotelsByTopicSchema,
    GetDestinationVibeSummarySchema
)
from src.models.sublocation_attributes import ATTRIBUTES, score_property
from src.ranking import rank_sublocations
from src.sublocation_intel import preferences_to_weights, write_explanations, narrate_ranking

logger = logging.getLogger(__name__)

class GraphRAGQueryEngine:
    """
    Hybrid query engine with Entity-First extraction, Tool Calling, and Late Fusion.
    """
    def __init__(self, neo4j_client, embedding_client, llm_client):
        self.neo4j = neo4j_client
        self.embeddings = embedding_client
        self.llm = llm_client
        
        # Initialize Rate Limiter once per engine instance to persist tokens
        from src.rate_limiter import TokenBucketRateLimiter
        self.rate_limiter = TokenBucketRateLimiter(capacity=10, refill_rate_per_sec=0.1)

    async def _extract_entities_from_query(self, natural_query: str, history: List[Dict] = None) -> Dict[str, List[str]]:
        """
        Fast extraction step (e.g., using Claude 3 Haiku).
        Extracts named entities from the user's query.
        """
        history_context = ""
        if history:
            history_str = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history])
            history_context = f"\n\nContext from previous conversation:\n{history_str}\n"

        prompt = f"""
        Extract the target travel intent from the user's query into a JSON object with keys 'attractions', 'locations', 'topics'.
        
        CRITICAL CONSTRAINT ON TOPICS: If the user's query relates to any of the following topics, you MUST map it to the exact topic name from this list:
        ["Luxury", "Budget", "Boutique", "Eco-Friendly", "Romantic", "Family-Friendly", "Adults-Only", "Business", "Pool", "Beachfront", "Spa & Wellness", "Fitness Center", "Pet-Friendly", "City Center", "Secluded", "Nature", "Fine Dining", "Breakfast Included", "Local Cuisine", "Nightlife", "Culture & History", "Adventure", "Shopping", "Other/Unclassified"]
        
        Mapping Examples:
        - "with family" -> "Family-Friendly"
        - "for couples" -> "Romantic"
        - "with a pool" -> "Pool"
        - "near the beach" -> "Beachfront"
        {history_context}
        Query: {natural_query}
        """
        schema = {
            "type": "object",
            "properties": {
                "attractions": {"type": "array", "items": {"type": "string"}},
                "locations": {"type": "array", "items": {"type": "string"}},
                "topics": {
                    "type": "array", 
                    "items": {
                        "type": "string",
                        "enum": [
                            "Luxury", "Budget", "Boutique", "Eco-Friendly", "Romantic", 
                            "Family-Friendly", "Adults-Only", "Business", "Pool", "Beachfront", 
                            "Spa & Wellness", "Fitness Center", "Pet-Friendly", "City Center", 
                            "Secluded", "Nature", "Fine Dining", "Breakfast Included", 
                            "Local Cuisine", "Nightlife", "Culture & History", "Adventure", 
                            "Shopping", "Other/Unclassified"
                        ]
                    }
                }
            }
        }
        response = await self.llm.complete(prompt, extra_body={"nvext": {"guided_json": schema}})
        return json.loads(response)

    async def _resolve_entity_uuid(self, entity_str: str, entity_type: str) -> str:
        """
        Uses neo4j vector search to resolve an entity to a canonical UUID.
        """
        query_embedding = await self.embeddings.embed(entity_str)
        cypher = """
        CALL db.index.vector.queryNodes('alias_embeddings', 1, $embedding) YIELD node AS a, score
        WHERE score >= $threshold
        MATCH (a)-[:RESOLVES_TO]->(e:Entity)
        RETURN e.id AS entity_id, score
        """
        response = await self.neo4j.execute_query(
            cypher,
            {"embedding": query_embedding, "threshold": 0.70}
        )
        result = [record.data() for record in response.records]
        if not result: 
            raise ValueError(f"Low confidence match for entity: {entity_str}")
        return result[0]['entity_id']

    async def _nl2cypher_fallback(self, natural_query: str, client_id: str = "default_user") -> Dict[str, Any]:
        """
        Fallback path for long-tail queries that fail tool routing or entity resolution.
        SANDBOXED: Rate-limited, read-only transaction, and execution timeout bounded.
        """
        logger.warning("Falling back to NL2Cypher sandbox")
        
        # 1. Rate limiting
        allowed = await self.rate_limiter.consume(client_id)
        if not allowed:
            return {"error": "Rate limit exceeded for NL2Cypher fallback."}
        
        # 2. Timeout & Read-Only execution.
        # SECURITY: parameterize the user query — never interpolate it into Cypher.
        # TIMEOUT: wrap in a neo4j Query so the server-side transaction timeout is
        # actually applied. execute_query treats unknown kwargs as query parameters,
        # so the previous `transaction_config={"timeout": ...}` was a silent no-op.
        cypher = "MATCH (n) WHERE n.name = $query RETURN n LIMIT 1"

        try:
            from neo4j import RoutingControl, Query
            timed_query = Query(cypher, timeout=5.0)  # 5s server-side timeout
            response = await self.neo4j.execute_query(
                timed_query,
                {"query": natural_query},
                routing_=RoutingControl.READ,
                database_="neo4j",
            )
            results = [record.data() for record in response.records]
            return {"results": results, "fallback_used": True}
        except Exception as e:
            logger.error(f"NL2Cypher fallback query failed: {e}")
            return {"error": "Query too complex, timed out or failed."}

    async def search(self, natural_query: str, client_id: str = "default_user", history: List[Dict] = None) -> Dict[str, Any]:
        """
        Main entry point for hybrid query processing.
        """
        try:
            # 1. Entity-First Extraction
            entities = await self._extract_entities_from_query(natural_query, history)
            
            # Decide which tool to use based on extracted entities (simplified router)
            if entities.get("attractions"):
                attraction_name = entities["attractions"][0]
                resolved_uuid = await self._resolve_entity_uuid(attraction_name, "attraction")
                return await self._execute_find_hotels_near_attraction(resolved_uuid, natural_query, history)
                
            elif entities.get("locations"):
                location_name = entities["locations"][0]
                # Try resolving as a canonical entity first.
                try:
                    resolved_uuid = await self._resolve_entity_uuid(location_name, "location")
                    # A resolved location may be a Destination with SubLocations.
                    # Probe the graph: if sub-locations hang off it, rank them;
                    # otherwise give a general vibe summary. Without this, every
                    # resolvable destination skipped the sub-location ranker.
                    if await self._has_sublocations(resolved_uuid):
                        return await self._execute_find_sublocations_for_destination(location_name, natural_query, history)
                    return await self._execute_destination_vibe_summary(resolved_uuid, natural_query, history)
                except ValueError:
                    # A broad/unresolvable place (e.g. "Hawaii" the region) — rank
                    # sub-locations across ALL destinations by stated preferences.
                    return await self._execute_rank_sublocations_globally(natural_query, history)

            elif entities.get("topics"):
                # A preference/vibe query with no specific place ("family-friendly
                # spots"). Rank sub-locations across all destinations. (Previously
                # routed to hotels-by-topic, which needs review data we don't have.)
                return await self._execute_rank_sublocations_globally(natural_query, history)

            else:
                # No clear entities extracted, fallback
                return await self._nl2cypher_fallback(natural_query, client_id)
                
        except ValueError as e:
            # Low confidence entity resolution
            logger.info(f"Resolution failed: {str(e)}")
            return await self._nl2cypher_fallback(natural_query, client_id)

    async def _execute_find_hotels_near_attraction(self, attraction_uuid: str, query: str, history: List[Dict] = None) -> Dict[str, Any]:
        """
        Tool Execution: Find hotels near a specific attraction.
        Uses parameterized Cypher to completely eliminate hallucination.
        """
        cypher = """
        MATCH (a:Entity {id: $uuid})
        MATCH (h:Entity)
        WHERE toLower(h.type) = 'hotel' AND h.location IS NOT NULL AND a.location IS NOT NULL
        AND point.distance(h.location, a.location) < $max_distance
        MATCH (c:Content)-[r:MAKES_CLAIM]->(claim:Claim)-[:ABOUT]->(h)
        RETURN h.id as hotel_id, h.canonical_name as hotel_name, point.distance(h.location, a.location) as dist, collect(DISTINCT claim.sources) as content_ids
        ORDER BY dist ASC
        LIMIT 5
        """
        response = await self.neo4j.execute_query(cypher, {"uuid": attraction_uuid, "max_distance": 5000})
        graph_results = [record.data() for record in response.records]
        
        # Late Fusion
        final_response = await self._late_fusion_synthesis(graph_results, query, history)
        return {"results": final_response, "tool_used": "find_hotels_near_attraction"}

    async def _execute_find_hotels_by_topic(self, topic: str, query: str, history: List[Dict] = None) -> Dict[str, Any]:
        # Embed the user's query to find mathematically relevant claims
        query_embedding = await self.embeddings.embed(query)
        
        cypher = """
        CALL db.index.vector.queryNodes('claim_embeddings', 20, $embedding) YIELD node AS claim, score
        MATCH (claim)-[:ABOUT]->(h:Entity)
        MATCH (c:Content)-[:MAKES_CLAIM]->(claim)
        MATCH (c)-[:DISCUSSES]->(t:Topic {name: $topic_name})
        WHERE toLower(h.type) = 'hotel'
        RETURN h.id as hotel_id, h.canonical_name as hotel_name, collect(DISTINCT c.id) as content_ids
        """
        response = await self.neo4j.execute_query(cypher, {"topic_name": topic, "embedding": query_embedding})
        graph_results = [record.data() for record in response.records]
        return {"results": await self._late_fusion_synthesis(graph_results, query, history)}

    async def _execute_destination_vibe_summary(self, location_uuid: str, query: str, history: List[Dict] = None) -> Dict[str, Any]:
        cypher = """
        MATCH (l:Entity {id: $uuid})<-[:ABOUT]-(claim:Claim)<-[:MAKES_CLAIM]-(c:Content)
        RETURN collect(DISTINCT c.id) as content_ids
        """
        response = await self.neo4j.execute_query(cypher, {"uuid": location_uuid})
        graph_results = [record.data() for record in response.records]
        return {"results": await self._late_fusion_synthesis(graph_results, query, history)}

    async def _late_fusion_synthesis(self, graph_results: List[Dict], context_query: str, history: List[Dict] = None) -> str:
        """
        LATE FUSION:
        Take the content_ids found by Neo4j and synthesize a response in the authentic blogger voice.
        """
        all_content_ids = []
        for r in graph_results:
            if "content_ids" in r:
                for c_list in r["content_ids"]:
                    if isinstance(c_list, list):
                        all_content_ids.extend(c_list)
                    else:
                        all_content_ids.append(c_list)
        
        # 1. Fetch raw text from Neo4j (assuming chunk_text is stored on Content nodes)
        cypher = """
        MATCH (c:Content)
        WHERE c.id IN $content_ids
        RETURN c.chunk_text AS chunk_text
        """
        response = await self.neo4j.execute_query(cypher, {"content_ids": all_content_ids})
        raw_chunks = [record.data().get("chunk_text") for record in response.records if record.data().get("chunk_text")]
        
        # 2. Inject into LLM
        system_prompt = f"""
        You are a highly knowledgeable travel assistant using RAG (Retrieval-Augmented Generation).
        Synthesize a helpful, conversational answer for the user based strictly on these blogger quotes.
        
        CRITICAL INSTRUCTION: If the retrieved quotes are completely irrelevant to the user's question, DO NOT attempt to answer it. Politely state that you do not have that specific information in your database. Do not hallucinate or make up answers.
        
        Quotes retrieved from the graph database: 
        {raw_chunks}
        """
        
        if history:
            messages = [{"role": "system", "content": system_prompt}] + history
            # The current user query is already at the end of history!
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_query}
            ]
            
        response = await self.llm.complete(messages=messages)
        return response

    async def _has_sublocations(self, entity_uuid: str) -> bool:
        """
        True if the resolved entity is a Destination-like node with SubLocations
        hanging off it. Ingestion nests SubLocation -[:PART_OF]-> Region -[:PART_OF]->
        Destination, so we probe 1-2 PART_OF hops (a 1-hop probe would always miss
        because of the intervening Region).
        """
        cypher = """
        MATCH (e:Entity {id: $uuid})<-[:PART_OF*1..2]-(s:SubLocation)
        RETURN count(s) AS sub_count
        """
        response = await self.neo4j.execute_query(cypher, {"uuid": entity_uuid})
        records = [record.data() for record in response.records]
        return bool(records) and records[0].get("sub_count", 0) > 0

    @staticmethod
    def _rows_to_candidates(rows: List[Dict[str, Any]], with_island: bool = False) -> List[Dict[str, Any]]:
        """Shape Neo4j rows into ranking candidates (name, price_tier, scores[, island])."""
        candidates = []
        for r in rows:
            c = {
                "name": r["name"],
                "category": r.get("category"),
                "price_tier": r.get("price_tier"),
                "scores": {a: r[a] for a in ATTRIBUTES if r.get(a) is not None},
            }
            if with_island:
                c["island"] = r.get("island")
            candidates.append(c)
        return candidates

    async def _rank_and_explain(self, query: str, candidates: List[Dict[str, Any]],
                                location_label: str, with_island: bool = False) -> Dict[str, Any]:
        """
        Shared sub-location ranking path (final_check.md §8):
        1. Translate free text -> attribute weights + budget (LLM).
        2. Rank by a DETERMINISTIC weighted dot product minus price penalties.
        3. Write "why this fits you" + one honest tradeoff per result (LLM copy).
        The LLM never does the ranking math.
        """
        mapped = await preferences_to_weights(self.llm, query)
        weights, budget_tier = mapped["weights"], mapped["budget_tier"]

        ranked = rank_sublocations(weights, candidates, budget_tier=budget_tier, limit=3)
        explanations = await write_explanations(self.llm, query, location_label, ranked)

        cards = []
        for r in ranked:
            card = {
                "name": r["name"],
                "price_tier": r.get("price_tier"),
                "fit_score": r["ranking"]["fit"],
                "total_score": r["ranking"]["total"],
                "why": explanations.get(r["name"], {}).get("why", ""),
                "tradeoff": explanations.get(r["name"], {}).get("tradeoff", ""),
            }
            if with_island:
                card["island"] = r.get("island")
            cards.append(card)

        # Conversational lead-in (LLM voice, grounded on the deterministic order/scores).
        summary = await narrate_ranking(self.llm, query, location_label, cards)

        return {
            "results": {
                "location": location_label,
                "budget_tier": budget_tier,
                "summary": summary,
                "ranked_sublocations": cards,
            },
            "tool_used": "sublocation_resolver",
        }

    async def _execute_find_sublocations_for_destination(self, destination_name: str, query: str, history: List[Dict] = None) -> Dict[str, Any]:
        """Rank the sub-locations of ONE destination by fit to the traveler's request."""
        score_returns = ", ".join(f"s.{score_property(a)} AS {a}" for a in ATTRIBUTES)
        cypher = f"""
        MATCH (d:Destination {{name: $dest_name}})<-[:PART_OF]-(:Region)<-[:PART_OF]-(s:SubLocation)
        RETURN s.name AS name, s.category AS category, s.price_tier AS price_tier, {score_returns}
        """
        db_res = await self.neo4j.execute_query(cypher, {"dest_name": destination_name})
        rows = [record.data() for record in db_res.records]
        if not rows:
            # No sub-locations for this destination — try ranking across all of them.
            return await self._execute_rank_sublocations_globally(query, history)
        return await self._rank_and_explain(query, self._rows_to_candidates(rows), destination_name)

    async def _execute_rank_sublocations_globally(self, query: str, history: List[Dict] = None) -> Dict[str, Any]:
        """
        Rank sub-locations across ALL destinations by fit to the traveler's request.
        This is the answer for open-ended, destination-less questions ("good places
        for a family in Hawaii") — previously those fell through to a hotel path that
        has no data yet and returned nothing.
        """
        score_returns = ", ".join(f"s.{score_property(a)} AS {a}" for a in ATTRIBUTES)
        cypher = f"""
        MATCH (d:Destination)<-[:PART_OF]-(:Region)<-[:PART_OF]-(s:SubLocation)
        RETURN s.name AS name, d.name AS island, s.category AS category,
               s.price_tier AS price_tier, {score_returns}
        """
        db_res = await self.neo4j.execute_query(cypher, {})
        rows = [record.data() for record in db_res.records]
        if not rows:
            return await self._nl2cypher_fallback(query)
        return await self._rank_and_explain(
            query, self._rows_to_candidates(rows, with_island=True),
            "your destinations", with_island=True,
        )
