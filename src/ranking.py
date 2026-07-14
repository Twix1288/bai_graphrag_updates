"""
Deterministic sub-location ranking (final_check.md §8).

A weighted dot product of the traveler's preference weights against a
sub-location's attribute scores, minus a price penalty. Pure, inspectable, and
LLM-free — the LLM only produces the weight vector (upstream) and the
explanation copy (downstream), never the ranking number here.
"""
from typing import Dict, List, Optional, Any

from src.models.sublocation_attributes import ATTRIBUTES, NEUTRAL_SCORE

# Budget handling (§8): a hard filter plus a soft penalty on tier mismatch in
# both directions. Scores are normalized to [0,10] so penalties are comparable.
HARD_OVER_BUDGET_MARGIN = 1     # price tiers above budget before a place is dropped
SOFT_PENALTY_PER_TIER = 1.25    # per tier of mismatch (either direction)


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Clamp to known attributes and L1-normalize so the fit score lands in [0,10].
    An all-zero/empty vector falls back to a uniform weighting."""
    clean = {a: max(0.0, float(weights.get(a, 0.0))) for a in ATTRIBUTES}
    total = sum(clean.values())
    if total <= 0:
        return {a: 1.0 / len(ATTRIBUTES) for a in ATTRIBUTES}
    return {a: w / total for a, w in clean.items()}


def score_sublocation(
    weights: Dict[str, float],
    scores: Dict[str, float],
    budget_tier: Optional[int] = None,
    price_tier: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Return an inspectable breakdown: fit (0-10 weighted dot product), price
    penalty, total, and whether the place is hard-filtered out by budget.
    Assumes `weights` is already normalized (see normalize_weights).
    """
    fit = sum(weights.get(a, 0.0) * float(scores.get(a, NEUTRAL_SCORE)) for a in ATTRIBUTES)

    penalty = 0.0
    excluded = False
    if budget_tier is not None and price_tier is not None:
        mismatch = price_tier - budget_tier
        if mismatch > HARD_OVER_BUDGET_MARGIN:
            excluded = True  # meaningfully over budget — filtered out
        penalty = SOFT_PENALTY_PER_TIER * abs(mismatch)

    return {
        "fit": round(fit, 4),
        "penalty": round(penalty, 4),
        "total": round(fit - penalty, 4),
        "excluded": excluded,
    }


def rank_sublocations(
    weights: Dict[str, float],
    candidates: List[Dict[str, Any]],
    budget_tier: Optional[int] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    Rank candidate sub-locations by fit, dropping hard-filtered ones.

    Each candidate dict must carry `scores` (attr -> 0-10) and optionally
    `price_tier`. Returns candidates augmented with a `ranking` breakdown,
    highest total first. If everything is filtered out by budget, fall back to
    ranking by fit alone (never show an empty list — §12 "thin markets").
    """
    norm = normalize_weights(weights)
    scored = []
    for c in candidates:
        breakdown = score_sublocation(norm, c.get("scores", {}), budget_tier, c.get("price_tier"))
        scored.append({**c, "ranking": breakdown})

    in_budget = [c for c in scored if not c["ranking"]["excluded"]]
    pool = in_budget if in_budget else scored
    pool.sort(key=lambda c: c["ranking"]["total"], reverse=True)
    return pool[:limit]
