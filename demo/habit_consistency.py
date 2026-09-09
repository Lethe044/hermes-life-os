"""
Hermes Life OS - Habit Consistency Score
============================================
Reports, for each habit with recorded check-ins, what percentage of
its check-ins were successful (done outright or protected with a
freeze) versus missed, using the per-check-in "habit_completion"
memory entries written by update_habit(). This is a genuine
per-check-in history, unlike the streak counters in habits.json which
only reflect the current state - a habit can have a short current
streak after a long run of consistency, and this surfaces that.
Pure local arithmetic, no new tracking of its own, no network call.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from storage import get_recent_memory


def compute_habit_consistency(days: int = 90) -> List[Dict[str, Any]]:
    """Returns a list of {"name", "total_checkins", "completed_checkins",
    "consistency_pct"} for every habit with at least one
    "habit_completion" memory entry in the last `days` days, sorted by
    consistency_pct descending.
    """
    entries = get_recent_memory(days)
    by_habit: Dict[str, List[bool]] = defaultdict(list)
    for e in entries:
        if e.get("type") != "habit_completion":
            continue
        habit = e.get("habit", "")
        if not habit:
            continue
        by_habit[habit].append(bool(e.get("completed", False)))

    results = []
    for habit, outcomes in by_habit.items():
        completed = sum(1 for o in outcomes if o)
        results.append({
            "name": habit,
            "total_checkins": len(outcomes),
            "completed_checkins": completed,
            "consistency_pct": round(100.0 * completed / len(outcomes), 1),
        })

    results.sort(key=lambda r: -r["consistency_pct"])
    return results


def format_habit_consistency(results: List[Dict[str, Any]]) -> str:
    """Turns compute_habit_consistency()'s output into a friendly
    multi-line summary, one line per habit."""
    if not results:
        return "No habit check-ins recorded yet - update a habit to start tracking consistency."

    lines = ["Habit consistency:"]
    for r in results:
        lines.append(
            f"- {r['name']}: {r['consistency_pct']}% "
            f"({r['completed_checkins']}/{r['total_checkins']} check-ins)"
        )
    return "\n".join(lines)
