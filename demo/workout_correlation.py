"""
Hermes Life OS - Workout Mood Impact
========================================
Compares average mood on days a workout was logged versus days
without one, using data already in fitness.json (via load_fitness).
Built on correlation_utils.py's shared same-calendar-day comparison
logic. No new tracking of its own, no network call. Compares
same-calendar-day entries, the same convention used by Habit Mood
Impact, Substance-Sleep Impact, and Social Mood Impact.
"""

from __future__ import annotations

from typing import Any, Dict

from correlation_utils import compute_metric_impact_by_presence
from storage import load_fitness


def compute_workout_mood_impact(days: int = 90) -> Dict[str, Any]:
    """Returns {"days", "days_with_workout", "days_without_workout",
    "avg_mood_with_workout", "avg_mood_without_workout", "mood_diff"}
    over the last `days` days. "mood_diff" is avg_mood_with_workout -
    avg_mood_without_workout, or None if either side has no data.
    """
    workout_dates = {w.get("date", "") for w in load_fitness() if w.get("date")}
    r = compute_metric_impact_by_presence(workout_dates, "mood", days)
    return {
        "days": r["days"],
        "days_with_workout": r["days_true"],
        "days_without_workout": r["days_false"],
        "avg_mood_with_workout": r["avg_metric_true"],
        "avg_mood_without_workout": r["avg_metric_false"],
        "mood_diff": r["diff"],
    }


def format_workout_mood_impact(result: Dict[str, Any]) -> str:
    """Turns compute_workout_mood_impact()'s output into a friendly
    multi-line summary."""
    if result["mood_diff"] is None:
        return (f"Not enough overlapping mood and workout logging in the last {result['days']} "
                 f"days to compare.")

    direction = "higher" if result["mood_diff"] > 0 else ("lower" if result["mood_diff"] < 0 else "the same")
    return (
        f"On days with a logged workout ({result['days_with_workout']} day(s)), "
        f"average mood was {result['avg_mood_with_workout']}. On days without one "
        f"({result['days_without_workout']} day(s)), average mood was {result['avg_mood_without_workout']} - "
        f"{abs(result['mood_diff'])} points {direction} on workout days."
    )
