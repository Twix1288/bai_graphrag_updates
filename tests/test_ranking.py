"""Unit tests for the deterministic sub-location ranking (final_check.md §8).
No LLM involved — this is the inspectable ranking math."""
from src.ranking import (
    normalize_weights, score_sublocation, rank_sublocations,
    HARD_OVER_BUDGET_MARGIN, SOFT_PENALTY_PER_TIER,
)
from src.models.sublocation_attributes import ATTRIBUTES


def test_normalize_weights_l1():
    w = normalize_weights({"beach": 3, "snorkeling": 1})
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["beach"] == 0.75 and w["snorkeling"] == 0.25


def test_normalize_weights_empty_is_uniform():
    w = normalize_weights({})
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(abs(v - 1.0 / len(ATTRIBUTES)) < 1e-9 for v in w.values())


def test_fit_is_weighted_dot_product():
    # All weight on beach; beach score 8 => fit 8.0.
    w = normalize_weights({"beach": 1})
    r = score_sublocation(w, {"beach": 8.0, "snorkeling": 2.0})
    assert r["fit"] == 8.0
    assert r["penalty"] == 0.0
    assert r["total"] == 8.0


def test_budget_soft_penalty_both_directions():
    w = normalize_weights({"beach": 1})
    scores = {"beach": 10.0}
    over = score_sublocation(w, scores, budget_tier=2, price_tier=3)   # 1 over
    under = score_sublocation(w, scores, budget_tier=3, price_tier=2)  # 1 under
    assert over["penalty"] == SOFT_PENALTY_PER_TIER
    assert under["penalty"] == SOFT_PENALTY_PER_TIER  # penalized both ways


def test_hard_filter_when_over_budget():
    w = normalize_weights({"luxury": 1})
    scores = {"luxury": 10.0}
    excluded = score_sublocation(w, scores, budget_tier=1, price_tier=1 + HARD_OVER_BUDGET_MARGIN + 1)
    assert excluded["excluded"] is True
    ok = score_sublocation(w, scores, budget_tier=1, price_tier=1 + HARD_OVER_BUDGET_MARGIN)
    assert ok["excluded"] is False


def test_rank_orders_by_total_and_drops_over_budget():
    w = {"beach": 10}
    candidates = [
        {"name": "Cheap Beach", "price_tier": 1, "scores": {"beach": 6}},
        {"name": "Lux Beach", "price_tier": 4, "scores": {"beach": 10}},   # over budget -> dropped
        {"name": "Mid Beach", "price_tier": 2, "scores": {"beach": 8}},
    ]
    ranked = rank_sublocations(w, candidates, budget_tier=1, limit=3)
    names = [r["name"] for r in ranked]
    assert "Lux Beach" not in names          # hard-filtered (3 tiers over budget)
    # Mid Beach: fit 8 - 1.25 penalty = 6.75 beats Cheap Beach fit 6.0.
    assert names[0] == "Mid Beach"


def test_rank_never_empty_when_all_over_budget():
    """Thin-market guard (§12): if everything is over budget, still return something."""
    w = {"luxury": 10}
    candidates = [{"name": "Only Resort", "price_tier": 4, "scores": {"luxury": 9}}]
    ranked = rank_sublocations(w, candidates, budget_tier=1, limit=3)
    assert len(ranked) == 1 and ranked[0]["name"] == "Only Resort"
