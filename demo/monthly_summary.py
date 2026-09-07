"""
Hermes Life OS - Month-over-Month Comparison
================================================
Compares average metrics between this calendar month (so far) and the
same span of days last calendar month - "how is this month going
compared to last month?" - as opposed to compare_periods()'s rolling
N-day windows. Reuses compare_periods() for the actual averaging/delta
math; this module only handles resolving the two calendar-month date
ranges. No new tracking or storage of its own, no network call.
"""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Any, Dict, Tuple

from analytics import compare_periods
from storage import get_memory_by_date_range


def _month_bounds(year: int, month: int) -> Tuple[str, str]:
    """First and last calendar day of the given month, as YYYY-MM-DD."""
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _previous_month(year: int, month: int) -> Tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def compute_monthly_comparison(today: str = "") -> Dict[str, Any]:
    """Compares this-month-so-far against the same day-count span at
    the start of last month (so a comparison run on the 10th compares
    days 1-10 of each month, not the whole of last month against a
    partial current month). `today` defaults to the real current date
    and only exists as a parameter to make testing deterministic.

    Returns {"current_month", "previous_month", "days_compared",
    "comparison": compare_periods()'s output}.
    """
    today_dt = datetime.strptime(today, "%Y-%m-%d") if today else datetime.now()
    current_start, _ = _month_bounds(today_dt.year, today_dt.month)
    current_end = today_dt.strftime("%Y-%m-%d")
    days_compared = today_dt.day

    prev_year, prev_month = _previous_month(today_dt.year, today_dt.month)
    prev_last_day = calendar.monthrange(prev_year, prev_month)[1]
    prev_end_day = min(days_compared, prev_last_day)
    previous_start = f"{prev_year:04d}-{prev_month:02d}-01"
    previous_end = f"{prev_year:04d}-{prev_month:02d}-{prev_end_day:02d}"

    current_entries = get_memory_by_date_range(current_start, current_end)
    previous_entries = get_memory_by_date_range(previous_start, previous_end)
    comparison = compare_periods(current_entries, previous_entries)

    return {
        "current_month": today_dt.strftime("%Y-%m"),
        "previous_month": f"{prev_year:04d}-{prev_month:02d}",
        "days_compared": days_compared,
        "comparison": comparison,
    }


def format_monthly_comparison(result: Dict[str, Any]) -> str:
    """Turns compute_monthly_comparison()'s output into a friendly
    multi-line summary."""
    comparison = result["comparison"]
    if not comparison:
        return (f"Not enough overlapping data to compare {result['current_month']} "
                 f"against {result['previous_month']} yet.")

    lines = [
        f"{result['current_month']} (first {result['days_compared']} day(s)) vs "
        f"{result['previous_month']} (same span):"
    ]
    for metric, stats in comparison.items():
        arrow = "up" if stats["delta"] > 0 else ("down" if stats["delta"] < 0 else "flat")
        lines.append(
            f"- {metric}: {stats['current']} vs {stats['previous']} "
            f"({arrow} {abs(stats['pct_change'])}%)"
        )
    return "\n".join(lines)
