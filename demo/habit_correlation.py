"""
Hermes Life OS - Habit Mood Impact
======================================
Compares average mood on days a given habit was completed versus days
it was logged but missed, using the "habit_completion" memory entries
written by update_habit(). Built on correlation_utils.py's shared
same-calendar-day comparison logic - this one uses
compute_metric_impact_by_status() rather than the "presence" variant,
since a day with no check-in at all must be excluded, not counted as
"missed" the way an ordinary absence would be for workouts or
substances. No new tracking of its own, no network call. Needs
check-ins on both outcomes to say anything, so this is naturally a
forward-looking feature - it only reflects habit activity recorded
going forward, not history from before this feature existed.
"""

from __future__ import annotations

from typing import Any, Dict

from correlation_utils import compute_metric_impact_by_status, entry_date
from storage import get_recent_memory


def compute_habit_mood_impact(habit_name: str, days: int = 90) -> Dict[str, Any]:
    """Returns {"habit_name", "days", "days_completed", "days_missed",
    "avg_mood_completed", "avg_mood_missed", "mood_diff"} over the last
    `days` days, matching each day's mood average against whether the
    habit was completed that day. A day with a habit check-in but no
    mood logged is simply excluded from the relevant average - it
    isn't counted as neutral. "mood_diff" is avg_mood_completed -
    avg_mood_missed, or None if either side has no data.
    """
    entries = get_recent_memory(days)
    status_by_date: Dict[str, bool] = {}
    for e in entries:
        if e.get("type") == "habit_completion" and e.get("habit", "").lower() == habit_name.lower():
            date = entry_date(e)
            if date:
                status_by_date[date] = bool(e.get("completed", False))

    r = compute_metric_impact_by_status(status_by_date, "mood", days)
    return {
        "habit_name": habit_name,
        "days": r["days"],
        "days_completed": r["days_true"],
        "days_missed": r["days_false"],
        "avg_mood_completed": r["avg_metric_true"],
        "avg_mood_missed": r["avg_metric_false"],
        "mood_diff": r["diff"],
    }


def format_habit_mood_impact(result: Dict[str, Any]) -> str:
    """Turns compute_habit_mood_impact()'s output into a friendly
    multi-line summary."""
    if result["mood_diff"] is None:
        return (f"Not enough overlapping mood and check-in data for '{result['habit_name']}' "
                 f"in the last {result['days']} days to compare - log mood on both completed "
                 f"and missed days to see the impact.")

    direction = "higher" if result["mood_diff"] > 0 else ("lower" if result["mood_diff"] < 0 else "the same")
    return (
        f"On days '{result['habit_name']}' was completed ({result['days_completed']} day(s)), "
        f"average mood was {result['avg_mood_completed']}. On days it was missed "
        f"({result['days_missed']} day(s)), average mood was {result['avg_mood_missed']} - "
        f"{abs(result['mood_diff'])} points {direction} on completed days."
    )
