"""Tests for the hotel/activity layer: price-tier derivation, grouping under
sub-locations, and the geocode cache. No live DB or network."""
import pytest

from src.models.sublocation_attributes import price_tier_from_category, budget_tier_from_text
from src.engine import GraphRAGQueryEngine
from fakes import RecordingNeo4j


@pytest.mark.parametrize("text,expected", [
    ("money is no object", 4),
    ("we want a luxury beachfront resort", 4),
    ("cheap backpacker trip", 1),
    ("something mid-range please", 2),
    ("we love snorkeling", None),   # no budget signal -> defer to LLM
    ("", None),
])
def test_budget_tier_from_text(text, expected):
    assert budget_tier_from_text(text) == expected


@pytest.mark.parametrize("category,expected", [
    ("Luxury / Historic", 4),
    ("Ultra-luxury resort", 4),
    ("Boutique", 3),
    ("Historic resort", 3),
    ("Mid-range", 2),
    ("Budget hostel", 1),
    ("Backpacker guesthouse", 1),
    ("", None),
    (None, None),
    ("Something unclassifiable", None),
])
def test_price_tier_from_category(category, expected):
    assert price_tier_from_category(category) == expected


def test_luxury_beats_boutique_when_both_present():
    # Most-expensive keyword wins: "luxury boutique" -> 4, not 3.
    assert price_tier_from_category("Luxury Boutique") == 4


@pytest.mark.asyncio
async def test_hotels_and_activities_grouping_filters_nulls():
    # Simulate a sub-location with 2 hotels + 1 activity; nulls (no match) dropped.
    rows = [{
        "hotels_raw": [
            {"name": "The Royal Hawaiian", "category": "Luxury / Historic", "price_tier": 4},
            {"name": "Budget Inn", "category": "Budget", "price_tier": 1},
            {"name": None, "category": None, "price_tier": None},  # OPTIONAL MATCH null
        ],
        "activities_raw": ["Outrigger Canoe Surfing", None],
    }]
    neo4j = RecordingNeo4j(responder=lambda q, p: rows)
    engine = GraphRAGQueryEngine(neo4j, embedding_client=None, llm_client=None)

    grouped = await engine._hotels_and_activities("Waikiki", "O'ahu")

    names = [h["name"] for h in grouped["hotels"]]
    assert names == ["Budget Inn", "The Royal Hawaiian"]  # sorted by price tier asc
    assert grouped["activities"] == ["Outrigger Canoe Surfing"]  # null dropped
    # Scoped by destination to avoid same-named sub-locations colliding.
    assert neo4j.calls[0]["params"] == {"sub": "Waikiki", "dest": "O'ahu"}


def test_geocode_cache_roundtrip(tmp_path):
    from src.geocoding import NominatimClient
    cache_file = tmp_path / "geo.json"
    client = NominatimClient(cache_path=str(cache_file))
    client._cache["Waikiki"] = [{"lat": "21.28", "lon": "-157.83", "address": {}}]
    client._save_cache()
    # A fresh client reads the persisted cache; _fetch returns it without network.
    reloaded = NominatimClient(cache_path=str(cache_file))
    assert reloaded._fetch("Waikiki")[0]["lat"] == "21.28"
