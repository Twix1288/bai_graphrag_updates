"""
Fixed attribute schema for SubLocation intelligence (final_check.md §4/§8).

The ranking engine is a deterministic weighted dot product of a traveler's
preference weights against these attribute scores, minus price penalties. The
LLM only translates free text into weights and writes explanation copy — it is
never used for the ranking math. Keeping the attribute set fixed and small is
what makes the score inspectable and defensible.
"""
from typing import Dict

# Attribute scores are stored on SubLocation nodes as `score_<key>` (0-10 floats).
ATTRIBUTES = [
    "beach",
    "snorkeling",
    "food_scene",
    "nightlife",
    "family_friendly",
    "walkability",
    "quiet",
    "luxury",
    "adventure",
    "culture",
]

SCORE_MIN = 0.0
SCORE_MAX = 10.0
NEUTRAL_SCORE = 5.0  # used only as a graceful fallback when seeding fails

# Price tiers 1 (budget) .. 4 (luxury), per §4.
PRICE_TIER_MIN = 1
PRICE_TIER_MAX = 4


def score_property(attribute: str) -> str:
    """Neo4j property name for an attribute score (e.g. 'beach' -> 'score_beach')."""
    return f"score_{attribute}"


def empty_scores() -> Dict[str, float]:
    """Neutral profile — every attribute at the midpoint (fallback only)."""
    return {attr: NEUTRAL_SCORE for attr in ATTRIBUTES}
