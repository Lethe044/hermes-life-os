"""
Hermes Life OS - Hydration Summary
======================================
Summarizes recent hydration logging - average daily intake vs. goal,
how many days the goal was met, and the current consecutive-day streak
of meeting the goal. Pure local arithmetic over data already in
hydration.json (via load_hydration), no new tracking or storage of its
own, no network call.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict

from storage import load_hydration


def compute_hydration_summary(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "goal", "days_logged", "avg_glasses_per_day",
    "days_goal_met", "goal_met_pct", "current_goal_streak"} over the
    last `days` days. Daily totals are rebuilt from the raw "log"
    entries (each a single glasses-logging event) rather than trusting
    the single "today" counter, since that counter only reflects the
    current calendar day.
    """
    hydration = load_hydration()
    goal = hydration.get("goal", 8)
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    by_date: Dict[str, int] = defaultdict(int)
    for entry in hydration.get("log", []):
        date = entry.get("date", "")
        if date >= cutoff:
            by_date[date] += entry.get("glasses", 0)

    if not by_date:
        return {"days": days, "goal": goal, "days_logged": 0,
                "avg_glasses_per_day": 0.0, "days_goal_met": 0,
                "goal_met_pct": 0.0, "current_goal_streak": 0}

    days_logged = len(by_date)
    total_glasses = sum(by_date.values())
    days_goal_met = sum(1 for total in by_date.values() if total >= goal)

    all_by_date: Dict[str, int] = defaultdict(int)
    for entry in hydration.get("log", []):
        all_by_date[entry.get("date", "")] += entry.get("glasses", 0)

    streak = 0
    cursor = datetime.utcnow().date()
    while all_by_date.get(cursor.strftime("%Y-%m-%d"), 0) >= goal:
        streak += 1
        cursor -= timedelta(days=1)

    return {
        "days": days,
        "goal": goal,
        "days_logged": days_logged,
        "avg_glasses_per_day": round(total_glasses / days_logged, 1),
        "days_goal_met": days_goal_met,
        "goal_met_pct": round(100.0 * days_goal_met / days_logged, 1),
        "current_goal_streak": streak,
    }


def format_hydration_summary(result: Dict[str, Any]) -> str:
    """Turns compute_hydration_summary()'s output into a friendly
    multi-line summary."""
    if result["days_logged"] == 0:
        return f"No hydration logged in the last {result['days']} days."

    lines = [
        f"Averaged {result['avg_glasses_per_day']} glasses/day over "
        f"{result['days_logged']} logged day(s) (goal: {result['goal']}).",
        f"Hit the goal on {result['days_goal_met']}/{result['days_logged']} logged days "
        f"({result['goal_met_pct']}%).",
    ]
    if result["current_goal_streak"] > 0:
        lines.append(f"Current goal-met streak: {result['current_goal_streak']} day(s).")
    return "\n".join(lines)
