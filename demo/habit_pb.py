"""
Hermes Life OS - Habit Personal-Best Progress
=================================================
For every habit, reports how the current streak compares to that
habit's personal-best streak - a different angle from
habit_milestones.py's fixed round-number countdown, since a habit
with a best streak of 12 will never hit "the next milestone of 14"
in a way that feels close, but "2 days from tying your best" always
does. Pure arithmetic over data already in habits.json (via
load_habits), no new tracking or storage of its own.
"""

from __future__ import annotations

from typing import Any, Dict, List

from storage import load_habits


def compute_habit_pb_progress() -> List[Dict[str, Any]]:
    """Returns a list of {"name", "streak", "best_streak", "status",
    "days_to_tie"} for every habit that has ever been logged (streak
    or best_streak > 0), sorted with habits currently at or above
    their personal best first, then by closeness to tying it.

    "status" is one of "new_best" (current streak beats the prior
    best), "tied_best" (equal to it), or "chasing_best" (below it).
    "days_to_tie" is 0 for the first two statuses.
    """
    habits = load_habits()
    results = []
    for h in habits:
        streak = h.get("streak", 0)
        best = h.get("best_streak", 0)
        if streak == 0 and best == 0:
            continue

        if streak > best:
            status = "new_best"
            days_to_tie = 0
        elif streak == best and best > 0:
            status = "tied_best"
            days_to_tie = 0
        else:
            status = "chasing_best"
            days_to_tie = best - streak

        results.append({
            "name": h.get("name", "?"),
            "streak": streak,
            "best_streak": best,
            "status": status,
            "days_to_tie": days_to_tie,
        })

    status_order = {"new_best": 0, "tied_best": 0, "chasing_best": 1}
    results.sort(key=lambda r: (status_order[r["status"]], r["days_to_tie"]))
    return results


def format_habit_pb_progress(results: List[Dict[str, Any]]) -> str:
    """Turns compute_habit_pb_progress()'s output into a friendly
    multi-line summary, one line per habit."""
    if not results:
        return "No habit history yet - complete a habit to start tracking your personal bests."

    lines = ["Habit personal bests:"]
    for r in results:
        if r["status"] == "new_best":
            lines.append(f"- {r['name']}: {r['streak']} days - a new personal best!")
        elif r["status"] == "tied_best":
            lines.append(f"- {r['name']}: {r['streak']} days - tied your personal best")
        elif r["days_to_tie"] == 1:
            lines.append(
                f"- {r['name']}: {r['streak']} days, 1 day from tying your "
                f"best of {r['best_streak']}"
            )
        else:
            lines.append(
                f"- {r['name']}: {r['streak']} days, {r['days_to_tie']} days from "
                f"tying your best of {r['best_streak']}"
            )
    return "\n".join(lines)
