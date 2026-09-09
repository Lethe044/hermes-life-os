"""
Hermes Life OS - Spending Trends by Category
================================================
Compares spending per category between a recent window and the equal-
length window before it, to answer "which categories am I spending
more/less on lately?" - unlike get_spending_summary, which only totals
a single window. Pure local arithmetic over data already in
spending.json (via load_spending), no new tracking of its own, no
network call.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict

from storage import load_spending


def compute_spending_trends(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "categories": {category: {"current", "previous",
    "delta", "pct_change"}}} comparing the last `days` days against the
    `days` days before that, per spending category. A category missing
    from one of the two windows still appears, with 0 for that side,
    so a brand-new or a stopped category is visible rather than
    silently dropped.
    """
    now = datetime.utcnow()
    current_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    previous_start = (now - timedelta(days=days * 2)).strftime("%Y-%m-%d")
    previous_end = current_start

    current_by_cat: Dict[str, float] = defaultdict(float)
    previous_by_cat: Dict[str, float] = defaultdict(float)
    for s in load_spending():
        date = s.get("date", "")
        category = s.get("category", "uncategorized")
        amount = s.get("amount", 0)
        if date >= current_start:
            current_by_cat[category] += amount
        elif previous_start <= date < previous_end:
            previous_by_cat[category] += amount

    categories: Dict[str, Dict[str, float]] = {}
    for category in set(current_by_cat) | set(previous_by_cat):
        current = round(current_by_cat.get(category, 0.0), 2)
        previous = round(previous_by_cat.get(category, 0.0), 2)
        delta = round(current - previous, 2)
        pct_change = round((delta / previous * 100.0), 1) if previous else (100.0 if current else 0.0)
        categories[category] = {
            "current": current, "previous": previous,
            "delta": delta, "pct_change": pct_change,
        }

    return {"days": days, "categories": categories}


def format_spending_trends(result: Dict[str, Any]) -> str:
    """Turns compute_spending_trends()'s output into a friendly
    multi-line summary, biggest dollar swings first."""
    if not result["categories"]:
        return f"No spending logged in the last {result['days'] * 2} days to compare."

    lines = [f"Spending trends (last {result['days']} days vs the {result['days']} before):"]
    ordered = sorted(result["categories"].items(), key=lambda kv: -abs(kv[1]["delta"]))
    for category, stats in ordered:
        arrow = "up" if stats["delta"] > 0 else ("down" if stats["delta"] < 0 else "flat")
        lines.append(
            f"- {category}: {stats['current']} vs {stats['previous']} "
            f"({arrow} {abs(stats['pct_change'])}%)"
        )
    return "\n".join(lines)
