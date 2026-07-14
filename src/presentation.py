"""Human-friendly rendering of sub-location ranking results for the chat surfaces."""
from typing import Any, Dict


def _bar(score: float, width: int = 10) -> str:
    filled = int(round(max(0.0, min(10.0, float(score))) / 10 * width))
    return "█" * filled + "·" * (width - filled)


def render_sublocations(result: Dict[str, Any]) -> str:
    """Render a sublocation_resolver result as a readable, ranked card list with scores."""
    r = result.get("results", {}) if isinstance(result, dict) else {}
    ranked = r.get("ranked_sublocations", [])
    if not ranked:
        return "  No matching areas found for that request."

    lines = []
    label = r.get("location")
    budget = r.get("budget_tier")

    # LLM conversational lead-in (grounded on the deterministic order/scores).
    summary = r.get("summary")
    if summary:
        lines.append(summary)
        lines.append("")

    header = "Best-fit areas" + (f" in {label}" if label and label != "your destinations" else "")
    if budget:
        header += f"  (your budget tier: {budget}/4)"
    lines.append(header)
    lines.append("")

    for i, s in enumerate(ranked, 1):
        island = f" — {s['island']}" if s.get("island") else ""
        tier = s.get("price_tier")
        tier_str = f"${'$' * (tier - 1)} (tier {tier}/4)" if tier else "price n/a"
        fit = s.get("fit_score", 0)
        lines.append(f"  {i}. {s['name']}{island}")
        lines.append(f"       match  {_bar(fit)}  {fit}/10        {tier_str}")
        if s.get("why"):
            lines.append(f"       ✓ why:      {s['why']}")
        if s.get("tradeoff"):
            lines.append(f"       ⚠ heads-up: {s['tradeoff']}")
        lines.append("")

    return "\n".join(lines).rstrip()
