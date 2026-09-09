"""
Hermes Life OS - Substance-Sleep Impact
============================================
Compares average sleep hours on days a substance was logged versus
days it wasn't, using data already in substance.json (via
load_substance) alongside sleep entries in the shared memory log. Pure
local arithmetic, no new tracking of its own, no network call.

Note: this compares sleep logged on the *same calendar date* as the
substance entry, not the following night - since log_sleep's "date" is
whatever day the person logged it (typically the morning after
waking), a same-day comparison is the closest available proxy without
guessing which night a sleep entry actually refers to.
"""

from __future__ import annotations

from typing import Any, Dict

from analytics import extract_metric
from storage import get_recent_memory, load_substance


def compute_substance_sleep_impact(substance: str, days: int = 90) -> Dict[str, Any]:
    """Returns {"substance", "days", "days_with_substance",
    "days_without_substance", "avg_sleep_with", "avg_sleep_without",
    "sleep_diff"} over the last `days` days. "sleep_diff" is
    avg_sleep_with - avg_sleep_without, or None if either side has no
    data. Only calendar days that have both a sleep entry and a clear
    with/without status are counted on either side.
    """
    substance_dates = {
        s.get("date", "") for s in load_substance()
        if s.get("substance", "").lower() == substance.lower()
    }

    entries = get_recent_memory(days)
    sleep_by_date: Dict[str, list] = {}
    for e in entries:
        extracted = extract_metric(e)
        if extracted and extracted[0] == "sleep":
            date = _entry_date(e)
            if date:
                sleep_by_date.setdefault(date, []).append(extracted[1])

    with_hours = []
    without_hours = []
    for date, hours_list in sleep_by_date.items():
        day_avg = sum(hours_list) / len(hours_list)
        (with_hours if date in substance_dates else without_hours).append(day_avg)

    avg_with = round(sum(with_hours) / len(with_hours), 2) if with_hours else None
    avg_without = round(sum(without_hours) / len(without_hours), 2) if without_hours else None
    sleep_diff = round(avg_with - avg_without, 2) if (avg_with is not None and avg_without is not None) else None

    return {
        "substance": substance,
        "days": days,
        "days_with_substance": len(with_hours),
        "days_without_substance": len(without_hours),
        "avg_sleep_with": avg_with,
        "avg_sleep_without": avg_without,
        "sleep_diff": sleep_diff,
    }


def _entry_date(entry: Dict[str, Any]):
    from datetime import datetime
    ts = entry.get("timestamp", "")
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
    except ValueError:
        return None


def format_substance_sleep_impact(result: Dict[str, Any]) -> str:
    """Turns compute_substance_sleep_impact()'s output into a friendly
    multi-line summary."""
    if result["sleep_diff"] is None:
        return (f"Not enough overlapping sleep and '{result['substance']}' logging in the last "
                 f"{result['days']} days to compare.")

    direction = "less" if result["sleep_diff"] < 0 else ("more" if result["sleep_diff"] > 0 else "the same")
    return (
        f"On days '{result['substance']}' was logged ({result['days_with_substance']} day(s)), "
        f"average sleep was {result['avg_sleep_with']}h. On other days "
        f"({result['days_without_substance']} day(s)), average sleep was {result['avg_sleep_without']}h - "
        f"{abs(result['sleep_diff'])}h {direction} sleep on days it was logged."
    )
