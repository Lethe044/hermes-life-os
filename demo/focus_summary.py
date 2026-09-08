"""
Hermes Life OS - Focus Summary
==================================
Summarizes recent focus sessions logged via log_focus_session - totals,
average duration/quality, completion rate, total distractions, and the
most common task. Pure local arithmetic over data already in
focus.json (via load_focus), no new tracking or storage of its own,
no network call.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict

from storage import load_focus


def compute_focus_summary(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "total_sessions", "total_minutes", "avg_duration",
    "avg_quality", "completed_sessions", "completion_pct",
    "total_distractions", "most_common_task"} over the last `days` days.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    sessions = [f for f in load_focus() if f.get("date", "") >= cutoff]

    if not sessions:
        return {"days": days, "total_sessions": 0, "total_minutes": 0,
                "avg_duration": 0.0, "avg_quality": 0.0, "completed_sessions": 0,
                "completion_pct": 0.0, "total_distractions": 0, "most_common_task": None}

    total_minutes = sum(s.get("duration", 0) for s in sessions)
    total_quality = sum(s.get("quality", 0) for s in sessions)
    completed = sum(1 for s in sessions if s.get("completed", True))
    total_distractions = sum(s.get("distractions", 0) for s in sessions)
    tasks = Counter(s.get("task", "") for s in sessions if s.get("task"))
    most_common_task = tasks.most_common(1)[0][0] if tasks else None

    return {
        "days": days,
        "total_sessions": len(sessions),
        "total_minutes": total_minutes,
        "avg_duration": round(total_minutes / len(sessions), 1),
        "avg_quality": round(total_quality / len(sessions), 1),
        "completed_sessions": completed,
        "completion_pct": round(100.0 * completed / len(sessions), 1),
        "total_distractions": total_distractions,
        "most_common_task": most_common_task,
    }


def format_focus_summary(result: Dict[str, Any]) -> str:
    """Turns compute_focus_summary()'s output into a friendly
    multi-line summary."""
    if result["total_sessions"] == 0:
        return f"No focus sessions logged in the last {result['days']} days."

    lines = [
        f"{result['total_sessions']} focus session(s) over the last {result['days']} days "
        f"({result['total_minutes']} min total, {result['avg_duration']} min average).",
        f"Average quality: {result['avg_quality']}/10. Completed {result['completed_sessions']}/"
        f"{result['total_sessions']} ({result['completion_pct']}%). "
        f"Total distractions: {result['total_distractions']}.",
    ]
    if result["most_common_task"]:
        lines.append(f"Most common task: {result['most_common_task']}.")
    return "\n".join(lines)
