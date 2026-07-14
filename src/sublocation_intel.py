"""
LLM-facing helpers for sub-location intelligence (final_check.md §5, §8).

Two narrow jobs the LLM is actually allowed to do:
  * seed attribute scores + price tier from editorial text (§5, human-verified later)
  * translate a traveler's free-text likes/dislikes into a weight vector (§8)
  * write the "why this fits you" + honest-tradeoff explanation copy (§8)

The ranking math itself lives in src/ranking.py and never touches the LLM.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.models.sublocation_attributes import (
    ATTRIBUTES, SCORE_MIN, SCORE_MAX, NEUTRAL_SCORE,
    PRICE_TIER_MIN, PRICE_TIER_MAX, empty_scores, budget_tier_from_text,
)

logger = logging.getLogger(__name__)


def _parse_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON extraction from an LLM response (tolerates code fences/prose)."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
    return {}


def _clamp_score(v: Any) -> float:
    try:
        return max(SCORE_MIN, min(SCORE_MAX, float(v)))
    except (TypeError, ValueError):
        return NEUTRAL_SCORE


def _clamp_tier(v: Any) -> Optional[int]:
    try:
        return max(PRICE_TIER_MIN, min(PRICE_TIER_MAX, int(v)))
    except (TypeError, ValueError):
        return None


async def seed_attribute_scores(llm, name: str, category: str, description: str,
                                insider_tip: str = "") -> Dict[str, Any]:
    """
    LLM-seed a sub-location's 0-10 attribute profile + price tier from its
    editorial text (§5). Returns {'scores': {...}, 'price_tier': int|None}.
    Falls back to a neutral profile if the model errors — never raises.
    """
    # NOTE: nvext `guided_json` is broken on the current model (nemotron-mini-4b) —
    # it returns truncated garbage. A plain JSON prompt + tolerant parsing is reliable.
    example = "{" + ", ".join(f'"{a}": 5' for a in ATTRIBUTES) + ', "price_tier": 2}'
    prompt = f"""
    You are scoring a travel sub-location on a fixed set of attributes for a family
    trip-planning product. Score each attribute from 0 (none/poor) to 10 (world-class),
    based ONLY on the text provided. Also assign a price_tier from 1 (budget) to 4 (luxury).

    Attributes: {", ".join(ATTRIBUTES)}

    Sub-location: {name}
    Category: {category}
    Description: {description}
    Insider tip: {insider_tip}

    Return ONLY a JSON object, no prose, exactly these keys, e.g.:
    {example}
    """
    try:
        raw = await llm.complete(prompt)
        data = _parse_json(raw)
    except Exception as e:  # noqa: BLE001 - seeding must never break ingestion
        logger.warning(f"Score seeding failed for '{name}': {e}. Using neutral profile.")
        data = {}

    scores = {a: _clamp_score(data.get(a, NEUTRAL_SCORE)) for a in ATTRIBUTES} if data else empty_scores()
    return {"scores": scores, "price_tier": _clamp_tier(data.get("price_tier")) if data else None}


async def preferences_to_weights(llm, free_text: str) -> Dict[str, Any]:
    """
    Translate free-text likes/dislikes into attribute weights (0-10 importance)
    plus an optional budget_tier (§8). Returns {'weights': {...}, 'budget_tier': int|None}.
    """
    # Plain JSON prompt (guided_json is broken on the current model — see seeder note).
    example = '{"weights": {' + ", ".join(f'"{a}": 0' for a in ATTRIBUTES) + '}, "budget_tier": 2}'
    prompt = f"""
    A traveler describes what they want from a trip. Convert it into importance
    weights (0 = don't care, 10 = top priority) for this FIXED attribute set, and
    infer a budget_tier from 1 (budget) to 4 (luxury) if stated or implied.

    Attributes: {", ".join(ATTRIBUTES)}

    Traveler said: "{free_text}"

    Return ONLY JSON, no prose, exactly this shape:
    {example}
    Only use attributes from the fixed set.
    """
    try:
        raw = await llm.complete(prompt)
        data = _parse_json(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Preference mapping failed: {e}. Using uniform weights.")
        data = {}

    raw_weights = data.get("weights", {}) if isinstance(data, dict) else {}
    weights = {a: _clamp_score(raw_weights.get(a, 0.0)) for a in ATTRIBUTES}
    if not any(weights.values()):
        weights = {a: NEUTRAL_SCORE for a in ATTRIBUTES}  # uniform fallback
    # A deterministic keyword read of the budget wins over the small model's guess
    # (which mis-inferred "money is no object" as tier 2); LLM value is the fallback.
    budget_tier = budget_tier_from_text(free_text)
    if budget_tier is None:
        budget_tier = _clamp_tier(data.get("budget_tier"))
    return {"weights": weights, "budget_tier": budget_tier}


async def write_explanations(llm, query: str, destination: str,
                             ranked: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """
    Empathy layer (§8): for each ranked sub-location, a one-line 'why this fits
    you' tied to the request and one honest tradeoff. Returns {name: {why, tradeoff}}.
    Degrades to deterministic copy from the scores if the LLM is unavailable.
    """
    summary = [
        {
            "name": r["name"],
            "top_attributes": sorted(r.get("scores", {}).items(), key=lambda kv: kv[1], reverse=True)[:3],
            "price_tier": r.get("price_tier"),
        }
        for r in ranked
    ]
    prompt = f"""
    You are a warm, honest travel assistant. The traveler asked: "{query}" about {destination}.
    For EACH sub-location below, write a one-line "why this fits you" tied to their request,
    and one honest tradeoff (a real downside). Be factual and friendly, not salesy.

    Sub-locations (name, strongest attributes, price tier 1-4): {summary}

    Return JSON: {{"<name>": {{"why": "...", "tradeoff": "..."}}, ...}}.
    """
    try:
        raw = await llm.complete(prompt)
        data = _parse_json(raw)
        if data:
            return {r["name"]: {
                "why": str(data.get(r["name"], {}).get("why", "")),
                "tradeoff": str(data.get(r["name"], {}).get("tradeoff", "")),
            } for r in ranked}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Explanation copy failed: {e}. Falling back to deterministic copy.")

    # Deterministic fallback copy from the scores.
    out = {}
    for r in ranked:
        top = sorted(r.get("scores", {}).items(), key=lambda kv: kv[1], reverse=True)[:2]
        strengths = ", ".join(a.replace("_", " ") for a, _ in top)
        out[r["name"]] = {
            "why": f"Strong on {strengths}.",
            "tradeoff": f"Price tier {r.get('price_tier', 'n/a')}; verify it matches your budget.",
        }
    return out


async def narrate_ranking(llm, query: str, location_label: str,
                          cards: List[Dict[str, Any]]) -> str:
    """
    Write a short, warm conversational lead-in for an ALREADY-ranked, already-scored
    result (the §9 Zara voice). The LLM only phrases the answer — it must present the
    areas in the given order and must not change the ranking or invent places.
    Returns "" if unavailable, so callers fall back to the scored cards alone.
    """
    if not cards:
        return ""
    facts = [
        {"rank": i + 1, "name": c["name"], "island": c.get("island"),
         "fit_score": c.get("fit_score"), "price_tier": c.get("price_tier"),
         "why": c.get("why", ""), "tradeoff": c.get("tradeoff", "")}
        for i, c in enumerate(cards)
    ]
    prompt = f"""
    A traveler asked: "{query}" (about {location_label}).
    Our ranking engine has ALREADY chosen and ordered the best-fit areas below.
    Write 2-3 warm, natural sentences introducing them, like a helpful friend.

    STRICT — DATA ONLY: use ONLY the facts given below. Do NOT name any beach,
    landmark, attraction, activity, hotel, or place that is not in this data. Do NOT
    invent or change scores. Keep the exact order given. Every claim you make must be
    supported by a name, island, price tier, "why", or "tradeoff" field below.

    Ranked areas (the only facts you may use): {facts}

    Return only the sentences, no preamble or JSON.
    """
    try:
        text = await llm.complete(prompt)
        return text.strip() if isinstance(text, str) else ""
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Narration failed: {e}. Showing cards only.")
        return ""
