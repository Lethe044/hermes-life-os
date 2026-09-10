"""
Hermes Life OS - Workout Mood Impact
========================================
Compares average mood on days a workout was logged versus days
without one, using data already in fitness.json (via load_fitness)
alongside mood entries in the shared memory log. Pure local
arithmetic, no new tracking of its own, no network call. Compares
same-calendar-day entries, the same convention used by Habit Mood
Impact, Substance-Sleep Impact, and Social Mood Impact.
"""

from __future__ import annotations

from typing import Any, Dict

from analytics import extract_metric
from storage import get_recent_memory, load_fitness


def compute_workout_mood_impact(days: int = 90) -> Dict[str, Any]:
    """Returns {"days", "days_with_workout", "days_without_workout",
    "avg_mood_with_workout", "avg_mood_without_workout", "mood_diff"}
    over the last `days` days. "mood_diff" is avg_mood_with_workout -
    avg_mood_without_workout, or None if either side has no data.
    """
    workout_dates = {w.get("date", "") for w in load_fitness() if w.get("date")}

    entries = get_recent_memory(days)
    mood_by_date: Dict[str, list] = {}
    for e in entries:
        extracted = extract_metric(e)
        if extracted and extracted[0] == "mood":
            date = _entry_date(e)
            if date:
                mood_by_date.setdefault(date, []).append(extracted[1])

    with_workout = []
    without_workout = []
    for date, moods in mood_by_date.items():
        day_avg = sum(moods) / len(moods)
        (with_workout if date in workout_dates else without_workout).append(day_avg)

    avg_with = round(sum(with_workout) / len(with_workout), 2) if with_workout else None
    avg_without = round(sum(without_workout) / len(without_workout), 2) if without_workout else None
    mood_diff = round(avg_with - avg_without, 2) if (avg_with is not None and avg_without is not None) else None

    return {
        "days": days,
        "days_with_workout": len(with_workout),
        "days_without_workout": len(without_workout),
        "avg_mood_with_workout": avg_with,
        "avg_mood_without_workout": avg_without,
        "mood_diff": mood_diff,
    }


def _entry_date(entry: Dict[str, Any]):
    from datetime import datetime
    ts = entry.get("timestamp", "")
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
    except ValueError:
        return None


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
