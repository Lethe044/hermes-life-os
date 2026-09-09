"""
Hermes Life OS - Reading Pace
=================================
For a given book title, computes reading pace (pages/day average
across days it was actually read) and, if a total_pages was ever
provided via log_reading, estimates the remaining days to finish at
that pace. Pure local arithmetic over data already in reading.json
(via load_reading), no new tracking of its own beyond the optional
total_pages field log_reading already accepts, no network call.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from storage import load_reading


def compute_reading_pace(title: str) -> Dict[str, Any]:
    """Returns {"title", "total_sessions", "total_pages_read",
    "days_active", "pages_per_day", "total_pages", "pages_remaining",
    "estimated_days_remaining", "estimated_finish_date"} for every
    logged session matching `title` (case-insensitive). "total_pages"
    is the most recent non-null value ever supplied for this title,
    or None if it was never given - in that case the estimate fields
    are also None, since there's nothing to count down to.
    """
    sessions = [r for r in load_reading() if r.get("title", "").lower() == title.lower()]

    if not sessions:
        return {"title": title, "total_sessions": 0, "total_pages_read": 0,
                "days_active": 0, "pages_per_day": 0.0, "total_pages": None,
                "pages_remaining": None, "estimated_days_remaining": None,
                "estimated_finish_date": None}

    total_pages_read = sum(s.get("pages", 0) for s in sessions)
    days_active = len({s.get("date", "") for s in sessions})
    pages_per_day = round(total_pages_read / days_active, 1) if days_active else 0.0

    total_pages = None
    for s in reversed(sessions):
        if s.get("total_pages") is not None:
            total_pages = s["total_pages"]
            break

    pages_remaining = None
    estimated_days_remaining = None
    estimated_finish_date = None
    if total_pages is not None:
        pages_remaining = max(total_pages - total_pages_read, 0)
        if pages_per_day > 0:
            estimated_days_remaining = _ceil_div(pages_remaining, pages_per_day)
            estimated_finish_date = (
                datetime.utcnow() + timedelta(days=estimated_days_remaining)
            ).strftime("%Y-%m-%d")

    return {
        "title": title,
        "total_sessions": len(sessions),
        "total_pages_read": total_pages_read,
        "days_active": days_active,
        "pages_per_day": pages_per_day,
        "total_pages": total_pages,
        "pages_remaining": pages_remaining,
        "estimated_days_remaining": estimated_days_remaining,
        "estimated_finish_date": estimated_finish_date,
    }


def _ceil_div(numerator: float, denominator: float) -> int:
    import math
    return int(math.ceil(numerator / denominator))


def format_reading_pace(result: Dict[str, Any]) -> str:
    """Turns compute_reading_pace()'s output into a friendly multi-line
    summary."""
    if result["total_sessions"] == 0:
        return f"No reading logged for '{result['title']}' yet."

    lines = [
        f"'{result['title']}': {result['total_pages_read']} page(s) read across "
        f"{result['total_sessions']} session(s) over {result['days_active']} day(s) "
        f"({result['pages_per_day']} pages/day average)."
    ]
    if result["total_pages"] is None:
        lines.append("No total page count on file - log a total_pages to get a finish estimate.")
    elif result["pages_remaining"] == 0:
        lines.append("Looks finished!")
    elif result["estimated_days_remaining"] is None:
        lines.append(f"{result['pages_remaining']} page(s) remaining of {result['total_pages']}.")
    else:
        lines.append(
            f"{result['pages_remaining']} page(s) remaining of {result['total_pages']} - "
            f"about {result['estimated_days_remaining']} day(s) left at this pace "
            f"(around {result['estimated_finish_date']})."
        )
    return "\n".join(lines)
