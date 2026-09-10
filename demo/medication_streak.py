"""
Hermes Life OS - Medication Streak
======================================
For a given medication/supplement name, computes the current and
longest consecutive-day streak of it being taken, using data already
in medication.json (via load_medication) - a different angle than
get_medication_adherence, which only reports an overall percentage for
the lookback window rather than a day-by-day streak. Pure local
arithmetic, no new tracking of its own, no network call.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict


from storage import load_medication


def compute_medication_streak(med_name: str) -> Dict[str, Any]:
    """Returns {"med_name", "total_logs", "current_streak",
    "longest_streak"} using the full logged history for `med_name`
    (case-insensitive match). A day counts as "taken" if taken=True on
    at least one entry logged that date; a day with no entry at all
    breaks the streak, same as a day explicitly logged as not taken.
    """
    logs = [m for m in load_medication() if m.get("name", "").lower() == med_name.lower()]

    if not logs:
        return {"med_name": med_name, "total_logs": 0, "current_streak": 0, "longest_streak": 0}

    taken_dates = {m.get("date", "") for m in logs if m.get("taken", True)}

    current_streak = 0
    cursor = datetime.utcnow().date()
    while cursor.strftime("%Y-%m-%d") in taken_dates:
        current_streak += 1
        cursor -= timedelta(days=1)

    longest_streak = 0
    running = 0
    for offset in range(400, -1, -1):
        date_str = (datetime.utcnow() - timedelta(days=offset)).strftime("%Y-%m-%d")
        if date_str in taken_dates:
            running += 1
            longest_streak = max(longest_streak, running)
        else:
            running = 0

    return {
        "med_name": med_name,
        "total_logs": len(logs),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
    }


def format_medication_streak(result: Dict[str, Any]) -> str:
    """Turns compute_medication_streak()'s output into a friendly
    one-line summary."""
    if result["total_logs"] == 0:
        return f"No logs found for '{result['med_name']}'."

    return (
        f"'{result['med_name']}': current streak {result['current_streak']} day(s), "
        f"longest streak {result['longest_streak']} day(s) ({result['total_logs']} total log(s))."
    )
