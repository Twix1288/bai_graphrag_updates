"""Unit tests for deterministic structured-entity IDs: distinct places that
share a name must NOT collapse, and re-ingesting a node must be idempotent."""
from src.ingestion import GraphIngestionPipeline
from src.ingest_structured_data import structured_entity_id
from fakes import RecordingNeo4j, RecordingEmbeddings


def _pipeline():
    return GraphIngestionPipeline(neo4j=RecordingNeo4j(), embeddings=RecordingEmbeddings())


def test_same_key_is_idempotent():
    p = _pipeline()
    a = structured_entity_id(p, "region", "North Shore", parent_id="oahu")
    b = structured_entity_id(p, "region", "North Shore", parent_id="oahu")
    assert a == b


def test_same_name_different_parent_does_not_collapse():
    """'North Shore' on O'ahu vs Kaua'i are distinct regions."""
    p = _pipeline()
    oahu = structured_entity_id(p, "region", "North Shore", parent_id="oahu")
    kauai = structured_entity_id(p, "region", "North Shore", parent_id="kauai")
    assert oahu != kauai


def test_same_name_different_type_does_not_collapse():
    """SubLocation 'Hana' vs Attraction 'Hana' under the same parent stay distinct."""
    p = _pipeline()
    sub = structured_entity_id(p, "sublocation", "Hana", parent_id="east-maui")
    attr = structured_entity_id(p, "attraction", "Hana", parent_id="east-maui")
    assert sub != attr


def test_normalization_folds_case_and_punctuation():
    """Trivial formatting differences resolve to the same id."""
    p = _pipeline()
    a = structured_entity_id(p, "sublocation", "Waikiki", parent_id="r1")
    b = structured_entity_id(p, "sublocation", "  waikiki!! ", parent_id="r1")
    assert a == b
