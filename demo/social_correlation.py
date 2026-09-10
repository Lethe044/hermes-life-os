"""
Hermes Life OS - Social Mood Impact
=======================================
Compares average mood on days with a logged social interaction versus
days without one, using data already in social.json (via load_social)
alongside mood entries in the shared memory log. Pure local
arithmetic, no new tracking of its own, no network call. Compares
same-calendar-day entries, the same convention used by Habit Mood
Impact and Substance-Sleep Impact.
"""

from __future__ import annotations

from typing import Any, Dict

from analytics import extract_metric
from storage import get_recent_memory, load_social


def compute_social_mood_impact(days: int = 90) -> Dict[str, Any]:
    """Returns {"days", "days_with_social", "days_without_social",
    "avg_mood_with_social", "avg_mood_without_social", "mood_diff"}
    over the last `days` days. "mood_diff" is avg_mood_with_social -
    avg_mood_without_social, or None if either side has no data.
    """
    social_dates = {s.get("date", "") for s in load_social() if s.get("date")}

    entries = get_recent_memory(days)
    mood_by_date: Dict[str, list] = {}
    for e in entries:
        extracted = extract_metric(e)
        if extracted and extracted[0] == "mood":
            date = _entry_date(e)
            if date:
                mood_by_date.setdefault(date, []).append(extracted[1])

    with_social = []
    without_social = []
    for date, moods in mood_by_date.items():
        day_avg = sum(moods) / len(moods)
        (with_social if date in social_dates else without_social).append(day_avg)

    avg_with = round(sum(with_social) / len(with_social), 2) if with_social else None
    avg_without = round(sum(without_social) / len(without_social), 2) if without_social else None
    mood_diff = round(avg_with - avg_without, 2) if (avg_with is not None and avg_without is not None) else None

    return {
        "days": days,
        "days_with_social": len(with_social),
        "days_without_social": len(without_social),
        "avg_mood_with_social": avg_with,
        "avg_mood_without_social": avg_without,
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
