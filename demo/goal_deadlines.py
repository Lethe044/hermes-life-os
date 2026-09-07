"""
Hermes Life OS - Goal Deadlines
===================================
Tracks an optional "deadline" (YYYY-MM-DD) field on goals stored via
update_goal, and reports how many days remain (or how overdue) each
deadline-bearing goal is - pure date arithmetic over data already in
goals.json (via load_goals), no new tracking or storage of its own.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from storage import load_goals


def compute_goal_deadlines(today: str = "") -> List[Dict[str, Any]]:
    """Returns a list of {"name", "progress", "deadline", "days_remaining",
    "overdue"} for every goal that has a "deadline" field set, sorted by
    days_remaining ascending (most urgent first, overdue goals first of
    all since their days_remaining is negative). Goals without a
    deadline are excluded. `today` defaults to the real current date
    and only exists as a parameter to make testing deterministic."""
    today_dt = datetime.strptime(today, "%Y-%m-%d") if today else datetime.now()
    goals = load_goals()
    results = []
    for g in goals:
        deadline = g.get("deadline")
        if not deadline:
            continue
        try:
            deadline_dt = datetime.strptime(deadline, "%Y-%m-%d")
        except ValueError:
            continue
        days_remaining = (deadline_dt - today_dt).days
        results.append({
            "name": g.get("name", "?"),
            "progress": g.get("progress", 0),
            "deadline": deadline,
            "days_remaining": days_remaining,
            "overdue": days_remaining < 0,
        })
    results.sort(key=lambda r: r["days_remaining"])
    return results


def format_goal_deadlines(results: List[Dict[str, Any]]) -> str:
    """Turns compute_goal_deadlines()'s output into a friendly
    multi-line summary, one line per goal, overdue ones called out."""
    if not results:
        return "No goals have a deadline set yet."

    lines = ["Goal deadlines:"]
    for r in results:
        if r["overdue"]:
            lines.append(
                f"- {r['name']}: overdue by {abs(r['days_remaining'])} day(s) "
                f"(deadline was {r['deadline']}, {r['progress']}% done)"
            )
        elif r["days_remaining"] == 0:
            lines.append(f"- {r['name']}: due today! ({r['progress']}% done)")
        else:
            lines.append(
                f"- {r['name']}: {r['days_remaining']} day(s) left "
                f"(deadline {r['deadline']}, {r['progress']}% done)"
            )
    return "\n".join(lines)
