"""
Hermes Life OS - Time-of-Day Insights
=========================================
Groups already-logged metrics (mood, energy, stress, etc.) into four
buckets - Morning, Afternoon, Evening, Night - by the hour each entry
was logged, to answer questions like "am I happier in the mornings?".
Pure local arithmetic over raw memory entries, no new tracking or
storage of its own, and no network call.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from analytics import extract_metric, TRACKABLE_METRICS
from storage import get_recent_memory

# Lower is better for these metrics (same convention as day_of_week.py).
_LOWER_IS_BETTER = {"stress"}

_BUCKETS = (
    (5, 11, "Morning"),
    (12, 16, "Afternoon"),
    (17, 21, "Evening"),
)


def _time_bucket(hour: int) -> str:
    """Morning 05:00-11:59, Afternoon 12:00-16:59, Evening 17:00-21:59,
    Night 22:00-04:59 (wraps past midnight)."""
    for start, end, name in _BUCKETS:
        if start <= hour <= end:
            return name
    return "Night"


def _entry_hour(entry: Dict[str, Any]) -> Optional[int]:
    ts = entry.get("timestamp", "")
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").hour
    except ValueError:
        return None


def compute_time_of_day_patterns(days: int = 90, metric: Optional[str] = None) -> Dict[str, Any]:
    """Buckets every raw entry with a usable metric and timestamp into
    Morning/Afternoon/Evening/Night by hour logged, for one metric or
    every metric in TRACKABLE_METRICS if `metric` is None. Unlike
    day_of_week.py (which averages per calendar day first), this works
    directly off individual entries, since several entries for the
    same metric can land in different time buckets on the same day.

    Returns {"days", "metrics": {metric: {"bucket_averages": {name: avg},
    "sample_counts": {name: int}, "best_time": name, "worst_time": name}}}.
    A metric is omitted if it has no logged data with a valid timestamp.
    """
    entries = get_recent_memory(days)
    metrics_to_check = {metric} if metric else set(TRACKABLE_METRICS)

    per_metric_by_bucket: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for entry in entries:
        extracted = extract_metric(entry)
        if not extracted:
            continue
        m, value = extracted
        if m not in metrics_to_check:
            continue
        hour = _entry_hour(entry)
        if hour is None:
            continue
        bucket = _time_bucket(hour)
        per_metric_by_bucket[m][bucket].append(value)

    results: Dict[str, Any] = {}
    for m, by_bucket in per_metric_by_bucket.items():
        if not by_bucket:
            continue
        bucket_averages = {b: round(sum(vals) / len(vals), 2) for b, vals in by_bucket.items()}
        sample_counts = {b: len(vals) for b, vals in by_bucket.items()}

        lower_is_better = m in _LOWER_IS_BETTER
        best = min(bucket_averages, key=bucket_averages.get) if lower_is_better \
            else max(bucket_averages, key=bucket_averages.get)
        worst = max(bucket_averages, key=bucket_averages.get) if lower_is_better \
            else min(bucket_averages, key=bucket_averages.get)

        results[m] = {
            "bucket_averages": bucket_averages,
            "sample_counts": sample_counts,
            "best_time": best,
            "worst_time": worst,
        }

    return {"days": days, "metrics": results}


def format_time_of_day_insights(result: Dict[str, Any]) -> List[str]:
    """Turns compute_time_of_day_patterns()'s output into human-readable
    one-line insights, one per metric that had at least two distinct
    time buckets logged."""
    lines = []
    for metric, data in result.get("metrics", {}).items():
        if len(data["bucket_averages"]) < 2:
            continue
        best = data["best_time"]
        worst = data["worst_time"]
        lines.append(
            f"{metric.capitalize()}: best in the {best} ({data['bucket_averages'][best]}), "
            f"worst in the {worst} ({data['bucket_averages'][worst]})."
        )
    return lines
