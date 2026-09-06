"""
Hermes Life OS - Moon Phase Correlation
===========================================
Correlates lunar phase with your tracked mood/energy/sleep - purely
via local astronomical calculation, no network call, no API key, no
external data of any kind (unlike weather.py, which fetches real
weather data over the internet). Every phase number here is computed
on your own machine from a well-known reference new moon date.

Offered in the same evidence-based spirit as every other correlation
Hermes computes: not because lunar effects on mood are scientifically
established (the balance of rigorous research says they aren't), but
because it's a harmless, fun pattern to check against your own data -
if Hermes finds nothing, that itself is the honest, useful answer.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List

from analytics import daily_averages, pearson_correlation
from storage import get_recent_memory

SYNODIC_MONTH_DAYS = 29.530588853
# A well-documented reference new moon (2000-01-06 18:14 UTC) - every
# other phase is computed relative to this one fixed point.
_REFERENCE_NEW_MOON = datetime(2000, 1, 6, 18, 14)

_PHASE_NAMES = [
    (0.0625, "New Moon"),
    (0.1875, "Waxing Crescent"),
    (0.3125, "First Quarter"),
    (0.4375, "Waxing Gibbous"),
    (0.5625, "Full Moon"),
    (0.6875, "Waning Gibbous"),
    (0.8125, "Last Quarter"),
    (0.9375, "Waning Crescent"),
]


def moon_phase_fraction(date: datetime) -> float:
    """The moon's phase as a fraction of the synodic month: 0.0 = new
    moon, 0.5 = full moon, approaching 1.0 = new moon again. Accurate
    to within roughly a day - more than enough for a "does phase
    correlate with mood" check, though not precise enough for, say,
    eclipse prediction."""
    days_since = (date - _REFERENCE_NEW_MOON).total_seconds() / 86400
    return (days_since % SYNODIC_MONTH_DAYS) / SYNODIC_MONTH_DAYS


def moon_phase_name(fraction: float) -> str:
    for threshold, name in _PHASE_NAMES:
        if fraction < threshold:
            return name
    return "New Moon"


def moon_illumination(fraction: float) -> float:
    """Approximate illuminated fraction (0.0 = new moon, 1.0 = full
    moon), via a standard cosine model - good enough for a friendly
    "X% illuminated" display, not intended for precision astronomy."""
    return (1 - math.cos(2 * math.pi * fraction)) / 2


def compute_moon_correlation(days: int = 90, min_abs_r: float = 0.3, min_days: int = 4) -> Dict[str, Any]:
    """Correlates each tracked metric's daily average against that
    day's moon illumination, over the last `days` days. Returns
    {"days", "today_phase", "today_illumination", "correlations"} -
    correlations sorted strongest-first, possibly empty if nothing
    crosses min_abs_r or there isn't enough data."""
    entries = get_recent_memory(days)
    daily = daily_averages(entries)

    illumination_by_date: Dict[str, float] = {}
    for date_str in daily.keys():
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        illumination_by_date[date_str] = moon_illumination(moon_phase_fraction(d))

    tracked_metrics = sorted({m for day in daily.values() for m in day})
    correlations: List[Dict[str, Any]] = []
    for metric in tracked_metrics:
        xs: List[float] = []
        ys: List[float] = []
        for date, day_metrics in daily.items():
            if metric not in day_metrics or date not in illumination_by_date:
                continue
            xs.append(illumination_by_date[date])
            ys.append(day_metrics[metric])
        if len(xs) < min_days:
            continue
        r = pearson_correlation(xs, ys)
        if r is None or abs(r) < min_abs_r:
            continue
        correlations.append({
            "metric": metric, "r": round(r, 3), "n_days": len(xs),
            "direction": "positive" if r > 0 else "negative",
        })

    correlations.sort(key=lambda c: -abs(c["r"]))
    today_fraction = moon_phase_fraction(datetime.utcnow())
    return {
        "days": days,
        "today_phase": moon_phase_name(today_fraction),
        "today_illumination_pct": round(moon_illumination(today_fraction) * 100),
        "correlations": correlations,
    }


def format_moon_insights(result: Dict[str, Any], limit: int = 3) -> List[str]:
    """Turns compute_moon_correlation()'s output into human-readable
    insight strings, same style as analytics.format_correlation_insights()
    and weather.format_weather_insights()."""
    out = []
    for c in result["correlations"][:limit]:
        rel = "tend to rise together" if c["direction"] == "positive" else "tend to move in opposite directions"
        out.append(
            f"Moon illumination and {c['metric']} {rel} (r={c['r']}, based on {c['n_days']} days)."
        )
    return out
