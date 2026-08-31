"""
Hermes Life OS - Weather Correlation
========================================
Correlates daily weather (temperature, precipitation) with your
tracked mood/energy/sleep/etc, using Open-Meteo's free, keyless weather
API (https://open-meteo.com) - no signup, no API key, no cost, no rate
limit that a personal-use pace would ever hit.

Two API calls: geocoding (turn a free-text place name into
latitude/longitude) and the historical weather archive (daily mean
temperature and precipitation for a date range).

This is the only tracker in Hermes that makes a network request - every
other tracker is 100% local. It only ever does so when explicitly asked
for via the get_weather_correlation tool, never automatically or in the
background, and never sends any of your tracked data anywhere - only
the place name you provide leaves your machine, to resolve coordinates
and fetch public historical weather.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from analytics import daily_averages, pearson_correlation
from storage import get_recent_memory

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

WEATHER_METRIC_LABELS = {
    "temp": "temperature",
    "precipitation": "precipitation",
}


class WeatherError(RuntimeError):
    pass


def geocode_location(location: str, timeout: int = 10) -> Dict[str, Any]:
    """Resolves a free-text place name (e.g. 'Istanbul' or 'Austin, TX')
    to latitude/longitude via Open-Meteo's free geocoding API. Returns
    {"name", "latitude", "longitude", "country"}. Raises WeatherError if
    nothing matches or the request fails - never lets a network error
    or malformed response propagate as a raw exception to callers."""
    params = urllib.parse.urlencode({"name": location, "count": 1})
    url = f"{GEOCODE_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise WeatherError(f"Could not look up location '{location}': {e}") from e

    results = data.get("results") or []
    if not results:
        raise WeatherError(f"No location found matching '{location}'.")
    top = results[0]
    return {
        "name": top.get("name", location),
        "latitude": top["latitude"],
        "longitude": top["longitude"],
        "country": top.get("country", ""),
    }


def fetch_daily_weather(latitude: float, longitude: float, start_date: str, end_date: str,
                         timeout: int = 15) -> Dict[str, Dict[str, float]]:
    """Fetches daily mean temperature (deg C) and precipitation (mm) for
    a date range via Open-Meteo's free historical archive API. Returns
    {date: {"temp": float, "precipitation": float}} - a day is omitted
    entirely if neither value is available for it. Raises WeatherError
    on any request/parsing failure or an empty result."""
    params = urllib.parse.urlencode({
        "latitude": latitude, "longitude": longitude,
        "start_date": start_date, "end_date": end_date,
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "auto",
    })
    url = f"{ARCHIVE_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise WeatherError(f"Could not fetch weather data: {e}") from e

    daily = data.get("daily") or {}
    dates = daily.get("time", [])
    temps = daily.get("temperature_2m_mean", [])
    precip = daily.get("precipitation_sum", [])
    if not dates:
        raise WeatherError("No weather data returned for that location/date range.")

    result: Dict[str, Dict[str, float]] = {}
    for i, date in enumerate(dates):
        entry: Dict[str, float] = {}
        if i < len(temps) and temps[i] is not None:
            entry["temp"] = temps[i]
        if i < len(precip) and precip[i] is not None:
            entry["precipitation"] = precip[i]
        if entry:
            result[date] = entry
    return result


def _align(weather_by_date: Dict[str, Dict[str, float]], weather_metric: str,
           tracked_daily: Dict[str, Dict[str, float]]) -> Dict[str, Tuple[List[float], List[float]]]:
    """For every tracked metric, builds paired (weather_value,
    tracked_value) lists over the dates where both actually have data -
    the same "only overlapping days count" approach analytics.py's own
    compute_correlations() uses."""
    tracked_metrics = sorted({m for day in tracked_daily.values() for m in day})
    result: Dict[str, Tuple[List[float], List[float]]] = {}
    for tracked_metric in tracked_metrics:
        xs: List[float] = []
        ys: List[float] = []
        for date, day_metrics in tracked_daily.items():
            if tracked_metric not in day_metrics:
                continue
            weather_day = weather_by_date.get(date)
            if not weather_day or weather_metric not in weather_day:
                continue
            xs.append(weather_day[weather_metric])
            ys.append(day_metrics[tracked_metric])
        if xs:
            result[tracked_metric] = (xs, ys)
    return result


def compute_weather_correlation(location: str, days: int = 30, min_abs_r: float = 0.3,
                                 min_days: int = 4) -> Dict[str, Any]:
    """Fetches weather for `location` over the last `days` days and
    correlates temperature/precipitation against every tracked metric
    using the same Pearson approach as analytics.compute_correlations().
    Returns {"location": {...}, "days": int, "correlations": [...]} -
    correlations is sorted strongest-first and may be empty if nothing
    crosses min_abs_r or there isn't enough overlapping data. Raises
    WeatherError if the location can't be resolved or the weather API
    call fails - callers (e.g. tools.py) are expected to catch this and
    show a friendly message rather than crash."""
    place = geocode_location(location)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    weather_by_date = fetch_daily_weather(
        place["latitude"], place["longitude"],
        start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
    )

    entries = get_recent_memory(days)
    tracked_daily = daily_averages(entries)

    correlations: List[Dict[str, Any]] = []
    for weather_metric in ("temp", "precipitation"):
        aligned = _align(weather_by_date, weather_metric, tracked_daily)
        for tracked_metric, (xs, ys) in aligned.items():
            if len(xs) < min_days:
                continue
            r = pearson_correlation(xs, ys)
            if r is None or abs(r) < min_abs_r:
                continue
            correlations.append({
                "weather_metric": weather_metric,
                "tracked_metric": tracked_metric,
                "r": round(r, 3),
                "n_days": len(xs),
                "direction": "positive" if r > 0 else "negative",
            })

    correlations.sort(key=lambda c: -abs(c["r"]))
    return {"location": place, "days": days, "correlations": correlations}


def format_weather_insights(result: Dict[str, Any], limit: int = 3) -> List[str]:
    """Turns compute_weather_correlation()'s output into human-readable
    insight strings, same style as analytics.format_correlation_insights()."""
    place_name = result["location"].get("name", "your location")
    out = []
    for c in result["correlations"][:limit]:
        weather_label = WEATHER_METRIC_LABELS.get(c["weather_metric"], c["weather_metric"])
        rel = "tend to rise together" if c["direction"] == "positive" else "tend to move in opposite directions"
        out.append(
            f"In {place_name}, {weather_label} and {c['tracked_metric']} {rel} "
            f"(r={c['r']}, based on {c['n_days']} days)."
        )
    return out
