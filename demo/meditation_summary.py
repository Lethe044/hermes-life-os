"""
Hermes Life OS - Meditation Summary
=======================================
Summarizes recent meditation sessions logged via log_meditation -
totals, average duration, and how consistently sessions were logged
(percentage of days in the window with at least one session). Pure
local arithmetic over data already in mental.json (via load_mental),
no new tracking or storage of its own, no network call.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from storage import load_mental


def compute_meditation_summary(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "total_sessions", "total_minutes",
    "avg_duration", "days_with_session", "consistency_pct"} over the
    last `days` days.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    sessions = [m for m in load_mental()
                if m.get("type") == "meditation" and m.get("date", "") >= cutoff]

    if not sessions:
        return {"days": days, "total_sessions": 0, "total_minutes": 0,
                "avg_duration": 0.0, "days_with_session": 0, "consistency_pct": 0.0}

    total_minutes = sum(s.get("duration", 0) for s in sessions)
    days_with_session = len({s.get("date", "") for s in sessions})

    return {
        "days": days,
        "total_sessions": len(sessions),
        "total_minutes": total_minutes,
        "avg_duration": round(total_minutes / len(sessions), 1),
        "days_with_session": days_with_session,
        "consistency_pct": round(100.0 * days_with_session / days, 1) if days else 0.0,
    }


def format_meditation_summary(result: Dict[str, Any]) -> str:
    """Turns compute_meditation_summary()'s output into a friendly
    multi-line summary."""
    if result["total_sessions"] == 0:
        return f"No meditation sessions logged in the last {result['days']} days."

    return (
        f"{result['total_sessions']} meditation session(s) over the last {result['days']} days "
        f"({result['total_minutes']} min total, {result['avg_duration']} min average).\n"
        f"Meditated on {result['days_with_session']}/{result['days']} days "
        f"({result['consistency_pct']}% of the window)."
    )
