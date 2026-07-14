"""
Fixed attribute schema for SubLocation intelligence (final_check.md §4/§8).

The ranking engine is a deterministic weighted dot product of a traveler's
preference weights against these attribute scores, minus price penalties. The
LLM only translates free text into weights and writes explanation copy — it is
never used for the ranking math. Keeping the attribute set fixed and small is
what makes the score inspectable and defensible.
"""
from typing import Dict, Optional

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


# Keyword -> price tier, most-expensive first so "luxury boutique" resolves to 4.
_PRICE_TIER_KEYWORDS = [
    (4, ("luxury", "ultra", "five-star", "5-star")),
    (3, ("boutique", "historic", "upscale", "resort", "premium", "four-star", "4-star")),
    (1, ("budget", "hostel", "economy", "value", "backpacker", "guesthouse")),
    (2, ("mid", "moderate", "standard", "three-star", "3-star")),
]


def price_tier_from_category(category: Optional[str]) -> Optional[int]:
    """
    Derive a 1-4 price tier from a hotel's free-text category (e.g.
    "Luxury / Historic" -> 4). Returns None when nothing matches, so callers can
    decide how to treat unknowns rather than guessing a misleading tier.
    """
    if not category:
        return None
    text = category.lower()
    for tier, keywords in _PRICE_TIER_KEYWORDS:
        if any(k in text for k in keywords):
            return tier
    return None


# Budget signals in a traveler's own words -> tier, strongest first. Deterministic
# because the small seeding/mapping model is unreliable here ("money is no object"
# was inferred as tier 2). Keyword hits override the LLM's guess.
_BUDGET_TIER_PHRASES = [
    (4, ("money is no object", "money no object", "spare no expense", "splurge",
         "luxury", "high-end", "high end", "five star", "5 star", "5-star",
         "top of the line", "best of the best", "ultra", "premium")),
    (1, ("budget", "cheap", "affordable", "backpack", "hostel", "shoestring",
         "low cost", "low-cost", "inexpensive", "save money", "on a dime")),
    (2, ("mid-range", "mid range", "midrange", "moderate", "reasonably priced",
         "reasonable budget")),
]


def budget_tier_from_text(text: Optional[str]) -> Optional[int]:
    """
    Deterministically infer a 1-4 budget tier from the traveler's own words.
    Returns None when there's no explicit signal, so the LLM's inference is used
    as the fallback rather than being overridden by a guess.
    """
    if not text:
        return None
    lowered = text.lower()
    for tier, phrases in _BUDGET_TIER_PHRASES:
        if any(p in lowered for p in phrases):
            return tier
    return None
