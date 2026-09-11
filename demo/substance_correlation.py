"""
Hermes Life OS - Substance-Sleep Impact
============================================
Compares average sleep hours on days a substance was logged versus
days it wasn't, using data already in substance.json (via
load_substance). Built on correlation_utils.py's shared
same-calendar-day comparison logic. No new tracking of its own, no
network call.

Note: this compares sleep logged on the *same calendar date* as the
substance entry, not the following night - since log_sleep's "date" is
whatever day the person logged it (typically the morning after
waking), a same-day comparison is the closest available proxy without
guessing which night a sleep entry actually refers to.
"""

from __future__ import annotations

from typing import Any, Dict

from correlation_utils import compute_metric_impact_by_presence
from storage import load_substance


def compute_substance_sleep_impact(substance: str, days: int = 90) -> Dict[str, Any]:
    """Returns {"substance", "days", "days_with_substance",
    "days_without_substance", "avg_sleep_with", "avg_sleep_without",
    "sleep_diff"} over the last `days` days. "sleep_diff" is
    avg_sleep_with - avg_sleep_without, or None if either side has no
    data.
    """
    substance_dates = {
        s.get("date", "") for s in load_substance()
        if s.get("substance", "").lower() == substance.lower()
    }
    r = compute_metric_impact_by_presence(substance_dates, "sleep", days)
    return {
        "substance": substance,
        "days": r["days"],
        "days_with_substance": r["days_true"],
        "days_without_substance": r["days_false"],
        "avg_sleep_with": r["avg_metric_true"],
        "avg_sleep_without": r["avg_metric_false"],
        "sleep_diff": r["diff"],
    }


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
