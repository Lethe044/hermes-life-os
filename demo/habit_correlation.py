"""
Hermes Life OS - Habit Mood Impact
======================================
Compares average mood on days a given habit was completed versus days
it was logged but missed, using the "habit_completion" memory entries
written by update_habit() alongside logged mood entries for the same
calendar day. Pure local arithmetic, no new tracking of its own, no
network call. Needs check-ins on both outcomes to say anything, so
this is naturally a forward-looking feature - it only reflects habit
activity recorded going forward, not history from before this feature
existed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from analytics import extract_metric
from storage import get_recent_memory


def compute_habit_mood_impact(habit_name: str, days: int = 90) -> Dict[str, Any]:
    """Returns {"habit_name", "days", "days_completed", "days_missed",
    "avg_mood_completed", "avg_mood_missed", "mood_diff"} over the last
    `days` days, matching each day's mood average (mean of every mood
    entry logged that day) against whether the habit was completed
    that day. A day with a habit check-in but no mood logged is simply
    excluded from the relevant average - it isn't counted as neutral.
    "mood_diff" is avg_mood_completed - avg_mood_missed, or None if
    either side has no data.
    """
    entries = get_recent_memory(days)

    mood_by_date: Dict[str, list] = {}
    habit_status_by_date: Dict[str, bool] = {}

    for e in entries:
        date = _entry_date(e)
        if not date:
            continue
        if e.get("type") == "habit_completion" and e.get("habit", "").lower() == habit_name.lower():
            habit_status_by_date[date] = bool(e.get("completed", False))
        else:
            extracted = extract_metric(e)
            if extracted and extracted[0] == "mood":
                mood_by_date.setdefault(date, []).append(extracted[1])

    completed_moods = []
    missed_moods = []
    for date, was_completed in habit_status_by_date.items():
        if date not in mood_by_date:
            continue
        day_avg = sum(mood_by_date[date]) / len(mood_by_date[date])
        (completed_moods if was_completed else missed_moods).append(day_avg)

    avg_completed = round(sum(completed_moods) / len(completed_moods), 2) if completed_moods else None
    avg_missed = round(sum(missed_moods) / len(missed_moods), 2) if missed_moods else None
    mood_diff = round(avg_completed - avg_missed, 2) if (avg_completed is not None and avg_missed is not None) else None

    return {
        "habit_name": habit_name,
        "days": days,
        "days_completed": len(completed_moods),
        "days_missed": len(missed_moods),
        "avg_mood_completed": avg_completed,
        "avg_mood_missed": avg_missed,
        "mood_diff": mood_diff,
    }


def _entry_date(entry: Dict[str, Any]) -> Optional[str]:
    from datetime import datetime
    ts = entry.get("timestamp", "")
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
    except ValueError:
        return None


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
