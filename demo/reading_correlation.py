"""
Hermes Life OS - Reading Mood Impact
========================================
Compares average mood on days a reading session was logged versus days
without one, using data already in reading.json (via load_reading).
Built on correlation_utils.py's shared same-calendar-day comparison
logic - the same "extra" this refactor was meant to make cheap to add.
No new tracking of its own, no network call.
"""

from __future__ import annotations

from typing import Any, Dict

from correlation_utils import compute_metric_impact_by_presence
from storage import load_reading


def compute_reading_mood_impact(days: int = 90) -> Dict[str, Any]:
    """Returns {"days", "days_with_reading", "days_without_reading",
    "avg_mood_with_reading", "avg_mood_without_reading", "mood_diff"}
    over the last `days` days. "mood_diff" is avg_mood_with_reading -
    avg_mood_without_reading, or None if either side has no data.
    """
    reading_dates = {r.get("date", "") for r in load_reading() if r.get("date")}
    r = compute_metric_impact_by_presence(reading_dates, "mood", days)
    return {
        "days": r["days"],
        "days_with_reading": r["days_true"],
        "days_without_reading": r["days_false"],
        "avg_mood_with_reading": r["avg_metric_true"],
        "avg_mood_without_reading": r["avg_metric_false"],
        "mood_diff": r["diff"],
    }


def format_reading_mood_impact(result: Dict[str, Any]) -> str:
    """Turns compute_reading_mood_impact()'s output into a friendly
    multi-line summary."""
    if result["mood_diff"] is None:
        return (f"Not enough overlapping mood and reading logging in the last {result['days']} "
                 f"days to compare.")

    direction = "higher" if result["mood_diff"] > 0 else ("lower" if result["mood_diff"] < 0 else "the same")
    return (
        f"On days with a logged reading session ({result['days_with_reading']} day(s)), "
        f"average mood was {result['avg_mood_with_reading']}. On days without one "
        f"({result['days_without_reading']} day(s)), average mood was {result['avg_mood_without_reading']} - "
        f"{abs(result['mood_diff'])} points {direction} on reading days."
    )
