"""
Hermes Life OS - Life Score
==============================
A single 0-100 composite score blending the day's tracked metrics into
one at-a-glance wellbeing indicator. Not a medical or clinical measure
- just a transparent, simple weighted blend of whatever you've actually
logged, so "how am I doing overall today" is answerable at a glance
instead of mentally combining five different numbers yourself.

How it works: each contributing metric is normalized to a 0-100 "higher
is better" scale (stress is inverted, since lower stress is better),
then combined as a weighted average using only the metrics actually
logged that day - a day with only a mood entry still gets a score,
just based on less data (and get_life_score's `components` field always
shows exactly which metrics fed the number, so it's never a black box).
compute_life_score() returns None for a day with nothing logged at all,
rather than a misleading default score.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from analytics import daily_averages
from storage import get_memory_by_date_range, get_recent_memory


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# metric -> (weight, normalize_fn). normalize_fn maps the metric's raw
# average value for a day to a 0-100 "higher is better" scale. Weights
# don't need to sum to 1 - they're relative, and only the metrics
# present on a given day are used (then re-normalized), so a day with
# fewer logged metrics is never penalized for missing data.
_METRIC_WEIGHTS = {
    "mood":      (1.0, lambda v: _clamp((v / 10) * 100)),
    "sleep":     (1.0, lambda v: _clamp((v / 8) * 100)),          # 8h -> 100
    "hydration": (0.6, lambda v: _clamp((v / 8) * 100)),          # 8 glasses -> 100
    "stress":    (1.0, lambda v: _clamp(100 - (v / 10) * 100)),   # inverted: lower stress -> higher score
    "energy":    (0.8, lambda v: _clamp((v / 3) * 100)),          # 1=low..3=high
    "focus":     (0.6, lambda v: _clamp((v / 10) * 100)),         # quality, 1-10
    "social_quality": (0.5, lambda v: _clamp((v / 10) * 100)),
}

_LABELS = [
    (85, "Thriving"),
    (70, "Doing well"),
    (55, "Steady"),
    (40, "Rough day"),
    (0,  "Tough day"),
]


def _label_for(score: float) -> str:
    for threshold, label in _LABELS:
        if score >= threshold:
            return label
    return _LABELS[-1][1]


def compute_life_score_for_date(date: str) -> Optional[Dict]:
    """Computes the Life Score for one specific YYYY-MM-DD date using
    whatever metrics were logged that day. Returns None if nothing
    scoreable was logged (rather than a misleading default score)."""
    entries = get_memory_by_date_range(date, date)
    averages = daily_averages(entries).get(date, {})
    return _score_from_averages(averages)


def _score_from_averages(averages: Dict[str, float]) -> Optional[Dict]:
    components: Dict[str, float] = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for metric, (weight, normalize) in _METRIC_WEIGHTS.items():
        if metric not in averages:
            continue
        normalized = normalize(averages[metric])
        components[metric] = round(normalized, 1)
        weighted_sum += normalized * weight
        weight_total += weight

    if weight_total == 0:
        return None

    score = round(weighted_sum / weight_total)
    return {"score": score, "label": _label_for(score), "components": components}


def compute_life_score() -> Optional[Dict]:
    """Today's Life Score. Returns None if nothing has been logged today."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return compute_life_score_for_date(today)


def compute_life_score_trend(days: int = 7) -> List[Dict]:
    """Life Score for each of the last `days` days that has enough data
    to score, oldest first - e.g. for a sparkline/trend line. Days with
    nothing logged are simply omitted (not padded with zeros), so the
    trend only reflects days you actually have data for."""
    entries = get_recent_memory(days)
    averages_by_date = daily_averages(entries)
    trend = []
    for date in sorted(averages_by_date.keys()):
        result = _score_from_averages(averages_by_date[date])
        if result is not None:
            trend.append({"date": date, **result})
    return trend
