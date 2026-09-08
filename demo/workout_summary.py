"""
Hermes Life OS - Workout Summary
====================================
Summarizes recent workouts logged via log_workout - totals, breakdown
by workout type, average duration/intensity mix, and a consecutive-day
workout streak. Pure local arithmetic over data already in
fitness.json (via load_fitness), no new tracking or storage of its
own, no network call.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List

from storage import load_fitness


def compute_workout_summary(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "total_workouts", "total_minutes",
    "avg_duration", "by_type": {type: count}, "most_common_type",
    "current_streak"} over the last `days` days. "current_streak" is
    the number of consecutive calendar days (counting back from today)
    that had at least one workout logged, regardless of the lookback
    window - a workout habit stopping mid-window still breaks it.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    workouts = [w for w in load_fitness() if w.get("date", "") >= cutoff]

    if not workouts:
        return {"days": days, "total_workouts": 0, "total_minutes": 0,
                "avg_duration": 0.0, "by_type": {}, "most_common_type": None,
                "current_streak": 0}

    total_minutes = sum(w.get("duration", 0) for w in workouts)
    by_type = Counter(w.get("type", "unknown") for w in workouts)
    most_common_type = by_type.most_common(1)[0][0]

    all_dates = {w.get("date", "") for w in load_fitness()}
    streak = 0
    cursor = datetime.utcnow().date()
    while cursor.strftime("%Y-%m-%d") in all_dates:
        streak += 1
        cursor -= timedelta(days=1)

    return {
        "days": days,
        "total_workouts": len(workouts),
        "total_minutes": total_minutes,
        "avg_duration": round(total_minutes / len(workouts), 1),
        "by_type": dict(by_type),
        "most_common_type": most_common_type,
        "current_streak": streak,
    }


def format_workout_summary(result: Dict[str, Any]) -> str:
    """Turns compute_workout_summary()'s output into a friendly
    multi-line summary."""
    if result["total_workouts"] == 0:
        return f"No workouts logged in the last {result['days']} days."

    lines = [
        f"{result['total_workouts']} workout(s) over the last {result['days']} days "
        f"({result['total_minutes']} min total, {result['avg_duration']} min average)."
    ]
    by_type_str = ", ".join(f"{t}: {c}" for t, c in
                             sorted(result["by_type"].items(), key=lambda kv: -kv[1]))
    lines.append(f"By type: {by_type_str} (most common: {result['most_common_type']}).")
    if result["current_streak"] > 0:
        lines.append(f"Current daily workout streak: {result['current_streak']} day(s).")
    return "\n".join(lines)
