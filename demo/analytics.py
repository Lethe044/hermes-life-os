"""
Hermes Life OS - Analytics
===========================
Real statistical correlation analysis across life-dimension metrics
(mood, sleep, stress, energy, hydration), replacing the previous
"correlation analysis active" placeholder with actual Pearson
correlation coefficients computed from daily-aggregated memory data.

This module has zero external dependencies (pure stdlib) so it can be
imported anywhere in the project without adding numpy/scipy as a
requirement.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

# Maps a memory entry "type" to (metric_name, extractor_fn)
_ENERGY_MAP = {"low": 1.0, "medium": 2.0, "high": 3.0}


def _extract_metric(entry: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    """Return (metric_name, numeric_value) for a memory entry, or None
    if the entry doesn't carry a metric we can correlate."""
    t = entry.get("type", "")
    if t == "mood":
        val = entry.get("score")
        return ("mood", float(val)) if val is not None else None
    if t == "energy":
        level = entry.get("level")
        if level in _ENERGY_MAP:
            return ("energy", _ENERGY_MAP[level])
        return None
    if t == "stress":
        val = entry.get("score")
        return ("stress", float(val)) if val is not None else None
    if t == "sleep":
        val = entry.get("hours")
        return ("sleep", float(val)) if val is not None else None
    if t == "hydration":
        val = entry.get("glasses")
        return ("hydration", float(val)) if val is not None else None
    return None


def _entry_date(entry: Dict[str, Any]) -> Optional[str]:
    ts = entry.get("timestamp", "")
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
    except Exception:
        return None


def build_daily_series(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[float]]]:
    """Group raw memory entries into {date: {metric: [values...]}}."""
    series: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for entry in entries:
        date = _entry_date(entry)
        if not date:
            continue
        extracted = _extract_metric(entry)
        if not extracted:
            continue
        metric, value = extracted
        series[date][metric].append(value)
    return series


def daily_averages(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Collapse same-day, same-metric values into a single daily average.
    Returns {date: {metric: avg_value}}."""
    raw = build_daily_series(entries)
    out: Dict[str, Dict[str, float]] = {}
    for date, metrics in raw.items():
        out[date] = {m: sum(vals) / len(vals) for m, vals in metrics.items()}
    return out


# ---------------------------------------------------------------------------
# Pearson correlation (pure stdlib)
# ---------------------------------------------------------------------------

def pearson_correlation(x: List[float], y: List[float]) -> Optional[float]:
    """Pearson correlation coefficient r for two equal-length numeric series.
    Returns None if fewer than 2 points or if either series has zero variance."""
    n = len(x)
    if n < 2 or n != len(y):
        return None

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)

    if var_x == 0 or var_y == 0:
        return None

    r = cov / ((var_x ** 0.5) * (var_y ** 0.5))
    # Clamp for floating point drift
    return max(-1.0, min(1.0, r))


def _strength_label(r: float) -> str:
    a = abs(r)
    if a >= 0.7:
        return "strong"
    if a >= 0.4:
        return "moderate"
    return "weak"


# Human-readable phrasing for known metric pairs. Falls back to a generic
# template when a pair isn't explicitly listed.
_PAIR_NOTES = {
    ("sleep", "mood"): "sleep and mood tend to move together",
    ("sleep", "energy"): "sleep and energy tend to move together",
    ("sleep", "stress"): "sleep and stress are linked",
    ("stress", "mood"): "stress and mood are linked",
    ("hydration", "energy"): "hydration and energy tend to move together",
    ("hydration", "mood"): "hydration and mood are linked",
}


def compute_correlations(
    entries: List[Dict[str, Any]],
    min_days: int = 4,
    min_abs_r: float = 0.4,
) -> List[Dict[str, Any]]:
    """
    Compute pairwise Pearson correlations between all tracked metrics
    (mood, sleep, stress, energy, hydration) using daily-averaged values.

    Only pairs with at least `min_days` overlapping days and
    |r| >= min_abs_r are returned, sorted by absolute strength (desc).

    Each result: {
        "metric_a": str, "metric_b": str, "r": float,
        "n_days": int, "strength": "strong"|"moderate"|"weak",
        "direction": "positive"|"negative", "note": str,
    }
    """
    daily = daily_averages(entries)
    if not daily:
        return []

    metrics = sorted({m for day in daily.values() for m in day.keys()})
    results: List[Dict[str, Any]] = []

    for i in range(len(metrics)):
        for j in range(i + 1, len(metrics)):
            a, b = metrics[i], metrics[j]
            paired_dates = [
                d for d, vals in daily.items() if a in vals and b in vals
            ]
            if len(paired_dates) < min_days:
                continue

            xs = [daily[d][a] for d in paired_dates]
            ys = [daily[d][b] for d in paired_dates]
            r = pearson_correlation(xs, ys)
            if r is None or abs(r) < min_abs_r:
                continue

            note_key = (a, b) if (a, b) in _PAIR_NOTES else (b, a)
            note = _PAIR_NOTES.get(note_key, f"{a} and {b} appear related")

            results.append({
                "metric_a": a,
                "metric_b": b,
                "r": round(r, 3),
                "n_days": len(paired_dates),
                "strength": _strength_label(r),
                "direction": "positive" if r > 0 else "negative",
                "note": note,
            })

    results.sort(key=lambda item: abs(item["r"]), reverse=True)
    return results


def format_correlation_insights(correlations: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    """Turn compute_correlations() output into human-readable insight strings."""
    out = []
    for c in correlations[:limit]:
        rel = "rise together" if c["direction"] == "positive" else "move in opposite directions"
        out.append(
            f"{c['strength'].capitalize()} correlation detected: {c['metric_a']} and "
            f"{c['metric_b']} {rel} (r={c['r']}, based on {c['n_days']} days). "
            f"{c['note'].capitalize()}."
        )
    return out


# ---------------------------------------------------------------------------
# Goal <-> metric linkage
# ---------------------------------------------------------------------------

TRACKABLE_METRICS = ("mood", "energy", "stress", "sleep", "hydration")


def compute_goal_progress(goal: Dict[str, Any], entries: List[Dict[str, Any]]) -> Optional[float]:
    """
    For a metric-linked goal (has "metric" and "target" fields), compute
    real progress (0-100) from actual logged data instead of a manual
    number. Returns None if the goal isn't metric-linked, or if there's
    no data yet for that metric in `entries` (caller should leave the
    existing/manual progress value untouched in that case).

    direction: "at_least" (e.g. sleep >= 7h) or "at_most" (e.g. stress <= 4).
    Progress is the average of the metric over `entries` relative to target,
    clamped to [0, 100].
    """
    metric = goal.get("metric")
    target = goal.get("target")
    if not metric or metric not in TRACKABLE_METRICS or target is None:
        return None

    daily = daily_averages(entries)
    values = [day.get(metric) for day in daily.values() if metric in day]
    if not values:
        return None

    avg = sum(values) / len(values)
    direction = goal.get("direction", "at_least")

    if direction == "at_most":
        if avg <= target:
            return 100.0
        if target <= 0:
            return 0.0
        return round(max(0.0, min(100.0, 100.0 * target / avg)), 1)
    else:  # at_least
        if target <= 0:
            return 100.0 if avg >= target else 0.0
        return round(max(0.0, min(100.0, 100.0 * avg / target)), 1)


# ---------------------------------------------------------------------------
# Period-over-period comparison (this week vs. last week, etc.)
# ---------------------------------------------------------------------------

def compare_periods(
    current_entries: List[Dict[str, Any]],
    previous_entries: List[Dict[str, Any]],
) -> Dict[str, Dict[str, float]]:
    """
    Compare the average of each tracked metric between two sets of
    entries (e.g. this week vs. last week). Returns, per metric that
    has data in *both* periods:
        {"current": avg, "previous": avg, "delta": current-previous,
         "pct_change": percent change from previous to current}
    Metrics missing from either period are simply omitted - a partial
    result is still useful, so this never raises for missing data.
    """
    current_daily = daily_averages(current_entries)
    previous_daily = daily_averages(previous_entries)

    def _metric_avg(daily: Dict[str, Dict[str, float]], metric: str) -> Optional[float]:
        values = [day.get(metric) for day in daily.values() if metric in day]
        return sum(values) / len(values) if values else None

    result: Dict[str, Dict[str, float]] = {}
    for metric in TRACKABLE_METRICS:
        cur = _metric_avg(current_daily, metric)
        prev = _metric_avg(previous_daily, metric)
        if cur is None or prev is None:
            continue
        delta = cur - prev
        pct_change = (delta / prev * 100.0) if prev != 0 else (100.0 if delta != 0 else 0.0)
        result[metric] = {
            "current": round(cur, 2),
            "previous": round(prev, 2),
            "delta": round(delta, 2),
            "pct_change": round(pct_change, 1),
        }
    return result
