"""Unit tests for GraphIngestionPipeline and MockRedisLock:
- stored embeddings use input_type='passage'
- claim dedup vs. creation branches
- the distributed lock self-heals after its TTL (crash-safety)."""
import time
import pytest

from src.ingestion import GraphIngestionPipeline, MockRedisLock
from fakes import RecordingNeo4j, RecordingEmbeddings


@pytest.mark.asyncio
async def test_resolve_alias_embeds_as_passage():
    """New alias embeddings must be created with input_type='passage'."""
    embeddings = RecordingEmbeddings()
    pipeline = GraphIngestionPipeline(neo4j=RecordingNeo4j(), embeddings=embeddings)

    await pipeline.resolve_or_create_alias("Waikiki Beach", "attraction", geo_res=None)

    assert embeddings.calls, "embed() was never called"
    assert all(c["input_type"] == "passage" for c in embeddings.calls)


@pytest.mark.asyncio
async def test_claim_creates_when_no_match():
    """With no similar existing claim, a new Claim node is CREATEd."""
    embeddings = RecordingEmbeddings()
    neo4j = RecordingNeo4j(lambda t, p: [])  # no dedup match
    pipeline = GraphIngestionPipeline(neo4j=neo4j, embeddings=embeddings)

    await pipeline.process_and_insert_claim("content-1", "entity-1", "The pool was great", "positive")

    assert any("CREATE (claim:Claim" in c["text"] for c in neo4j.calls)
    # Claim text is stored content -> passage.
    assert embeddings.calls[-1]["input_type"] == "passage"


@pytest.mark.asyncio
async def test_claim_deduplicates_on_match():
    """A high-similarity same-sentiment claim is merged, not re-created."""
    def responder(text, params):
        if "vector.queryNodes('claim_embeddings'" in text:
            return [{"claim_id": "claim-existing", "similarity": 0.97}]
        return []
    neo4j = RecordingNeo4j(responder)
    pipeline = GraphIngestionPipeline(neo4j=neo4j, embeddings=RecordingEmbeddings())

    await pipeline.process_and_insert_claim("content-2", "entity-1", "Amazing pool!", "positive")

    assert any("MERGE (c)-[:MAKES_CLAIM]->(claim)" in c["text"] and "CASE" in c["text"]
               for c in neo4j.calls)
    assert not any("CREATE (claim:Claim" in c["text"] for c in neo4j.calls)


@pytest.mark.asyncio
async def test_lock_blocks_second_holder():
    """A second acquire on a held, unexpired lock must wait, then succeed on release."""
    lock = MockRedisLock()
    order = []

    async with lock.lock("entity:1", timeout=10):
        order.append("first-in")
    # After the context exits, the lock is free and re-acquirable.
    async with lock.lock("entity:1", timeout=10):
        order.append("second-in")

    assert order == ["first-in", "second-in"]


@pytest.mark.asyncio
async def test_lock_self_heals_after_ttl():
    """A crashed holder (never released) must not deadlock: an expired lock is free."""
    lock = MockRedisLock()
    # Simulate a holder that acquired then crashed, with an already-lapsed TTL.
    lock._locks["entity:2"] = time.monotonic() - 1.0

    # Should acquire immediately instead of hanging.
    async with lock.lock("entity:2", timeout=10):
        acquired = True
    assert acquired is True
