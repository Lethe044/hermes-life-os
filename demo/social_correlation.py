"""
Hermes Life OS - Social Mood Impact
=======================================
Compares average mood on days with a logged social interaction versus
days without one, using data already in social.json (via load_social).
Built on correlation_utils.py's shared same-calendar-day comparison
logic. No new tracking of its own, no network call.
"""

from __future__ import annotations

from typing import Any, Dict

from correlation_utils import compute_metric_impact_by_presence
from storage import load_social


def compute_social_mood_impact(days: int = 90) -> Dict[str, Any]:
    """Returns {"days", "days_with_social", "days_without_social",
    "avg_mood_with_social", "avg_mood_without_social", "mood_diff"}
    over the last `days` days. "mood_diff" is avg_mood_with_social -
    avg_mood_without_social, or None if either side has no data.
    """
    social_dates = {s.get("date", "") for s in load_social() if s.get("date")}
    r = compute_metric_impact_by_presence(social_dates, "mood", days)
    return {
        "days": r["days"],
        "days_with_social": r["days_true"],
        "days_without_social": r["days_false"],
        "avg_mood_with_social": r["avg_metric_true"],
        "avg_mood_without_social": r["avg_metric_false"],
        "mood_diff": r["diff"],
    }


def format_social_mood_impact(result: Dict[str, Any]) -> str:
    """Turns compute_social_mood_impact()'s output into a friendly
    multi-line summary."""
    if result["mood_diff"] is None:
        return (f"Not enough overlapping mood and social logging in the last {result['days']} "
                 f"days to compare.")

    direction = "higher" if result["mood_diff"] > 0 else ("lower" if result["mood_diff"] < 0 else "the same")
    return (
        f"On days with a logged social interaction ({result['days_with_social']} day(s)), "
        f"average mood was {result['avg_mood_with_social']}. On days without one "
        f"({result['days_without_social']} day(s)), average mood was {result['avg_mood_without_social']} - "
        f"{abs(result['mood_diff'])} points {direction} on social days."
    )
