"""Unit tests for GraphRAGQueryEngine: Cypher-injection safety, query timeout,
and the location -> (sub-location ranker | vibe summary) routing probe."""
import pytest

from src.engine import GraphRAGQueryEngine
from fakes import RecordingNeo4j, RecordingEmbeddings


def _make_engine(neo4j=None, embeddings=None, llm=None):
    return GraphRAGQueryEngine(
        neo4j_client=neo4j or RecordingNeo4j(),
        embedding_client=embeddings or RecordingEmbeddings(),
        llm_client=llm,
    )


@pytest.mark.asyncio
async def test_fallback_parameterizes_query_no_injection():
    """The user query must be bound as a parameter, never interpolated into Cypher."""
    neo4j = RecordingNeo4j()
    engine = _make_engine(neo4j=neo4j)

    malicious = "x' RETURN n; MATCH (m) DETACH DELETE m //"
    await engine._nl2cypher_fallback(malicious, client_id="tester")

    # The read query is the last call (rate limiter uses no DB here).
    call = neo4j.calls[-1]
    assert call["text"] == "MATCH (n) WHERE n.name = $query RETURN n LIMIT 1"
    assert call["params"] == {"query": malicious}
    # The raw payload must not appear inside the Cypher text.
    assert "DETACH DELETE" not in call["text"]


@pytest.mark.asyncio
async def test_fallback_applies_server_side_timeout():
    """The fallback query must carry a 5s server-side timeout (via neo4j.Query)."""
    neo4j = RecordingNeo4j()
    engine = _make_engine(neo4j=neo4j)

    await engine._nl2cypher_fallback("anything", client_id="tester")

    call = neo4j.calls[-1]
    assert call["timeout"] == 5.0
    assert call["kwargs"].get("routing_") is not None  # read-only routing set


@pytest.mark.asyncio
async def test_fallback_rate_limited(monkeypatch):
    """When the rate limiter denies the request, no DB query is issued."""
    neo4j = RecordingNeo4j()
    engine = _make_engine(neo4j=neo4j)

    async def deny(_client_id):
        return False
    monkeypatch.setattr(engine.rate_limiter, "consume", deny)

    result = await engine._nl2cypher_fallback("q", client_id="tester")
    assert "error" in result
    assert neo4j.calls == []  # short-circuited before touching Neo4j


@pytest.mark.asyncio
async def test_has_sublocations_probe_uses_variable_length_path():
    """The probe must span 1-2 PART_OF hops (Region sits between Destination and SubLocation)."""
    def responder(text, params):
        assert "PART_OF*1..2" in text
        return [{"sub_count": 3}]
    engine = _make_engine(neo4j=RecordingNeo4j(responder))

    assert await engine._has_sublocations("uuid-1") is True


@pytest.mark.asyncio
async def test_has_sublocations_false_when_zero():
    engine = _make_engine(neo4j=RecordingNeo4j(lambda t, p: [{"sub_count": 0}]))
    assert await engine._has_sublocations("uuid-1") is False


@pytest.mark.asyncio
async def test_routing_destination_with_sublocations(monkeypatch):
    """A resolvable location WITH sub-locations routes to the sub-location ranker."""
    engine = _make_engine()

    async def extract(q, history=None):
        return {"attractions": [], "topics": [], "locations": ["Oahu"]}
    async def resolve(name, etype):
        return "uuid-oahu"
    async def has_subs(uuid):
        return True

    monkeypatch.setattr(engine, "_extract_entities_from_query", extract)
    monkeypatch.setattr(engine, "_resolve_entity_uuid", resolve)
    monkeypatch.setattr(engine, "_has_sublocations", has_subs)
    monkeypatch.setattr(engine, "_execute_find_sublocations_for_destination",
                        lambda *a, **k: _sentinel("sublocations"))
    monkeypatch.setattr(engine, "_execute_destination_vibe_summary",
                        lambda *a, **k: _sentinel("vibe"))

    result = await engine.search("where to stay in Oahu")
    assert result == {"routed": "sublocations"}


@pytest.mark.asyncio
async def test_routing_destination_without_sublocations(monkeypatch):
    """A resolvable location WITHOUT sub-locations routes to the vibe summary."""
    engine = _make_engine()

    async def extract(q, history=None):
        return {"attractions": [], "topics": [], "locations": ["Paris"]}
    async def resolve(name, etype):
        return "uuid-paris"
    async def has_subs(uuid):
        return False

    monkeypatch.setattr(engine, "_extract_entities_from_query", extract)
    monkeypatch.setattr(engine, "_resolve_entity_uuid", resolve)
    monkeypatch.setattr(engine, "_has_sublocations", has_subs)
    monkeypatch.setattr(engine, "_execute_find_sublocations_for_destination",
                        lambda *a, **k: _sentinel("sublocations"))
    monkeypatch.setattr(engine, "_execute_destination_vibe_summary",
                        lambda *a, **k: _sentinel("vibe"))

    result = await engine.search("what's the vibe of Paris")
    assert result == {"routed": "vibe"}


async def _sentinel(tag):
    return {"routed": tag}
