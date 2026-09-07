"""
Hermes Life OS - Habit Milestone Countdown
==============================================
For every habit with an active streak, finds the next round-number
milestone (7, 14, 30, 50, 100, 150, 200, 365, 500, 1000 days) and how
many days remain to reach it - pure arithmetic over data already in
habits.json (via load_habits), no new tracking or storage of its own.
"""

from __future__ import annotations

from typing import Any, Dict, List

from storage import load_habits

MILESTONES = (7, 14, 30, 50, 100, 150, 200, 365, 500, 1000)


def _next_milestone(streak: int) -> int:
    """The smallest milestone strictly greater than `streak`. If the
    streak has already passed every predefined milestone, doubles the
    largest one repeatedly so there's always a next target."""
    for m in MILESTONES:
        if streak < m:
            return m
    milestone = MILESTONES[-1]
    while milestone <= streak:
        milestone *= 2
    return milestone


def compute_habit_milestones() -> List[Dict[str, Any]]:
    """Returns a list of {"name", "streak", "best_streak",
    "next_milestone", "days_remaining"} for every habit with
    streak > 0, sorted by days_remaining ascending (closest milestone
    first). Habits with a streak of 0 are excluded - there's nothing
    to count down toward until the streak restarts."""
    habits = load_habits()
    results = []
    for h in habits:
        streak = h.get("streak", 0)
        if streak <= 0:
            continue
        milestone = _next_milestone(streak)
        results.append({
            "name": h.get("name", "?"),
            "streak": streak,
            "best_streak": h.get("best_streak", streak),
            "next_milestone": milestone,
            "days_remaining": milestone - streak,
        })
    results.sort(key=lambda r: r["days_remaining"])
    return results


def format_habit_milestones(results: List[Dict[str, Any]]) -> str:
    """Turns compute_habit_milestones()'s output into a friendly
    multi-line summary, one line per habit."""
    if not results:
        return "No active habit streaks yet - complete a habit to start one."

    lines = ["Upcoming habit milestones:"]
    for r in results:
        if r["days_remaining"] == 1:
            lines.append(
                f"- {r['name']}: {r['streak']}-day streak, "
                f"1 day from a {r['next_milestone']}-day milestone!"
            )
        else:
            lines.append(
                f"- {r['name']}: {r['streak']}-day streak, "
                f"{r['days_remaining']} days from a {r['next_milestone']}-day milestone"
            )
    return "\n".join(lines)
