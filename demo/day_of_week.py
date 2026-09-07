"""
Hermes Life OS - Day-of-Week Insights
=========================================
Groups already-logged metrics (mood, energy, stress, sleep, etc.) by
weekday to answer questions like "what's my best day of the week?" -
pure local arithmetic over data already gathered via daily_averages,
no new tracking or storage of its own, and no network call.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from analytics import daily_averages, TRACKABLE_METRICS
from storage import get_recent_memory

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Metrics where a *lower* average is the better outcome (the opposite
# of mood/energy/sleep, where higher is better) - used to decide
# whether "best day" should look for the max or the min average.
_LOWER_IS_BETTER = {"stress"}


def compute_day_of_week_patterns(days: int = 90, metric: Optional[str] = None) -> Dict[str, Any]:
    """Buckets daily_averages() by weekday (Monday=0) for one metric, or
    every metric in TRACKABLE_METRICS if `metric` is None that has at
    least one logged day. For each metric returns per-weekday averages
    plus the best/worst weekday (worst/best flipped for metrics where
    lower is better, e.g. stress).

    Returns {"days", "metrics": {metric: {"weekday_averages": {name: avg},
    "sample_counts": {name: int}, "best_day": name, "worst_day": name}}}.
    A metric is omitted from "metrics" if it has no logged data at all
    in the window.
    """
    entries = get_recent_memory(days)
    daily = daily_averages(entries)

    metrics_to_check = [metric] if metric else list(TRACKABLE_METRICS)

    per_metric_by_weekday: Dict[str, Dict[int, List[float]]] = {
        m: defaultdict(list) for m in metrics_to_check
    }
    for date_str, values in daily.items():
        try:
            weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
        except ValueError:
            continue
        for m in metrics_to_check:
            if m in values:
                per_metric_by_weekday[m][weekday].append(values[m])

    results: Dict[str, Any] = {}
    for m, by_weekday in per_metric_by_weekday.items():
        if not by_weekday:
            continue
        weekday_averages = {}
        sample_counts = {}
        for weekday_idx, vals in by_weekday.items():
            name = _WEEKDAY_NAMES[weekday_idx]
            weekday_averages[name] = round(sum(vals) / len(vals), 2)
            sample_counts[name] = len(vals)

        lower_is_better = m in _LOWER_IS_BETTER
        best_name = min(weekday_averages, key=weekday_averages.get) if lower_is_better \
            else max(weekday_averages, key=weekday_averages.get)
        worst_name = max(weekday_averages, key=weekday_averages.get) if lower_is_better \
            else min(weekday_averages, key=weekday_averages.get)

        results[m] = {
            "weekday_averages": weekday_averages,
            "sample_counts": sample_counts,
            "best_day": best_name,
            "worst_day": worst_name,
        }

    return {"days": days, "metrics": results}


def format_day_of_week_insights(result: Dict[str, Any]) -> List[str]:
    """Turns compute_day_of_week_patterns()'s output into human-readable
    one-line insights, one per metric that had at least two distinct
    weekdays logged (a single weekday can't have a "best vs worst").
    """
    lines = []
    for metric, data in result.get("metrics", {}).items():
        if len(data["weekday_averages"]) < 2:
            continue
        best = data["best_day"]
        worst = data["worst_day"]
        best_val = data["weekday_averages"][best]
        worst_val = data["weekday_averages"][worst]
        lines.append(
            f"{metric.capitalize()}: best on {best}s ({best_val}), "
            f"worst on {worst}s ({worst_val})."
        )
    return lines
