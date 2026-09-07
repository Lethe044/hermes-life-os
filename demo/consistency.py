"""
Hermes Life OS - Logging Consistency Score
==============================================
Measures how consistently you've been logging - overall and per
tracked metric - over a recent window: the percentage of days that
have at least one entry. Pure local arithmetic over data already
gathered via daily_averages, no new tracking or storage of its own.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from analytics import daily_averages, TRACKABLE_METRICS
from storage import get_recent_memory


def compute_logging_consistency(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "days_with_any_entry", "overall_pct",
    "per_metric_pct": {metric: pct}} over the last `days` days. Days
    are counted from today going back `days` full days (inclusive of
    today). A metric with zero logged days across the window is
    omitted from "per_metric_pct" rather than shown as 0%, since an
    unused tracker isn't really "inconsistent", it's just unused.
    """
    entries = get_recent_memory(days)
    daily = daily_averages(entries)

    days_with_any_entry = len(daily)
    overall_pct = round(100.0 * days_with_any_entry / days, 1) if days else 0.0

    per_metric_days: Dict[str, int] = {m: 0 for m in TRACKABLE_METRICS}
    for metrics_on_day in daily.values():
        for metric in metrics_on_day:
            if metric in per_metric_days:
                per_metric_days[metric] += 1

    per_metric_pct = {
        m: round(100.0 * count / days, 1)
        for m, count in per_metric_days.items()
        if count > 0
    }

    return {
        "days": days,
        "days_with_any_entry": days_with_any_entry,
        "overall_pct": overall_pct,
        "per_metric_pct": per_metric_pct,
    }


def format_logging_consistency(result: Dict[str, Any]) -> str:
    """Turns compute_logging_consistency()'s output into a friendly
    multi-line summary."""
    if result["days_with_any_entry"] == 0:
        return f"No entries logged in the last {result['days']} days - start logging to see your consistency."

    lines = [
        f"Logged something on {result['days_with_any_entry']}/{result['days']} days "
        f"({result['overall_pct']}%) over the last {result['days']} days."
    ]
    if result["per_metric_pct"]:
        lines.append("By metric:")
        for metric, pct in sorted(result["per_metric_pct"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- {metric}: {pct}%")
    return "\n".join(lines)
