"""
Hermes Life OS - Correlation Utilities
===========================================
Shared same-calendar-day binary-vs-metric comparison logic, factored
out of habit_correlation.py, substance_correlation.py,
social_correlation.py, and workout_correlation.py, which had all
grown nearly identical "average metric X on days condition Y held
versus days it didn't" implementations. Each of those modules now
builds its own event/status data (from whichever load_*() function or
memory-entry type is relevant to it) and calls one of the two
functions here to do the actual comparison, then remaps the generic
result keys to its own historical, more readable key names.

No new tracking or storage of its own, no network call.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from analytics import extract_metric
from storage import get_recent_memory


def entry_date(entry: Dict[str, Any]) -> Optional[str]:
    """The calendar date (YYYY-MM-DD) a memory entry's timestamp falls
    on, or None if the entry has no parseable timestamp."""
    ts = entry.get("timestamp", "")
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
    except ValueError:
        return None


def metric_by_date(days: int, metric: str) -> Dict[str, List[float]]:
    """Every value of `metric` (a metric name recognized by
    analytics.extract_metric, e.g. "mood" or "sleep") logged in the
    last `days` days, grouped by calendar date."""
    entries = get_recent_memory(days)
    result: Dict[str, List[float]] = {}
    for e in entries:
        extracted = extract_metric(e)
        if extracted and extracted[0] == metric:
            date = entry_date(e)
            if date:
                result.setdefault(date, []).append(extracted[1])
    return result


def _split_and_average(status_by_date: Dict[str, bool],
                        by_date: Dict[str, List[float]]) -> Dict[str, Any]:
    true_vals: List[float] = []
    false_vals: List[float] = []
    for date, status in status_by_date.items():
        if date not in by_date:
            continue
        day_avg = sum(by_date[date]) / len(by_date[date])
        (true_vals if status else false_vals).append(day_avg)

    avg_true = round(sum(true_vals) / len(true_vals), 2) if true_vals else None
    avg_false = round(sum(false_vals) / len(false_vals), 2) if false_vals else None
    diff = round(avg_true - avg_false, 2) if (avg_true is not None and avg_false is not None) else None

    return {
        "days_true": len(true_vals), "days_false": len(false_vals),
        "avg_metric_true": avg_true, "avg_metric_false": avg_false, "diff": diff,
    }


def compute_metric_impact_by_presence(event_dates: Set[str], metric: str, days: int) -> Dict[str, Any]:
    """For every date with a logged `metric` value in the last `days`
    days, splits it into "event happened that date" (in `event_dates`)
    versus "it didn't" - i.e. absence of the event is inferred, not
    required to be separately logged. This is the right fit when the
    "didn't happen" side has no explicit record of its own (a day with
    no workout logged simply has no workout entry at all).

    Returns {"days", "days_true", "days_false", "avg_metric_true",
    "avg_metric_false", "diff"}.
    """
    by_date = metric_by_date(days, metric)
    status_by_date = {date: (date in event_dates) for date in by_date}
    result = _split_and_average(status_by_date, by_date)
    result["days"] = days
    return result


def compute_metric_impact_by_status(status_by_date: Dict[str, bool], metric: str, days: int) -> Dict[str, Any]:
    """Like compute_metric_impact_by_presence(), but for cases where
    "didn't happen" needs its own explicit record rather than being
    inferred from absence - e.g. a habit that was logged as missed is
    different from a habit that simply wasn't checked in on at all,
    and only the former should count as a "false" data point. Dates
    not present in `status_by_date` are excluded from both sides.

    Returns {"days", "days_true", "days_false", "avg_metric_true",
    "avg_metric_false", "diff"}.
    """
    by_date = metric_by_date(days, metric)
    result = _split_and_average(status_by_date, by_date)
    result["days"] = days
    return result
