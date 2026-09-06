"""
Hermes Life OS - Sleep Debt Calculator
==========================================
Tracks cumulative "sleep debt" - the running shortfall between a
target sleep duration and what you actually logged - and suggests a
bedtime to help pay it down gradually. Purely arithmetic over data
already logged via log_sleep; no new tracking or storage of its own.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from analytics import daily_averages
from storage import get_recent_memory

DEFAULT_TARGET_HOURS = 8.0


def compute_sleep_debt(days: int = 14, target_hours: float = DEFAULT_TARGET_HOURS) -> Dict[str, Any]:
    """Sums (target - actual) sleep hours over the last `days` days
    that actually have a logged sleep value - a day with no sleep
    entry contributes nothing (Hermes can't know what happened on an
    unlogged day, so it isn't counted as debt). A negative total means
    a sleep *surplus* over the target, not debt.

    Returns {"days", "target_hours", "logged_days", "total_debt_hours",
    "avg_debt_per_day"}."""
    entries = get_recent_memory(days)
    daily = daily_averages(entries)

    debt = 0.0
    logged_days = 0
    for day_metrics in daily.values():
        if "sleep" not in day_metrics:
            continue
        debt += target_hours - day_metrics["sleep"]
        logged_days += 1

    avg_debt_per_day = debt / logged_days if logged_days else 0.0
    return {
        "days": days,
        "target_hours": target_hours,
        "logged_days": logged_days,
        "total_debt_hours": round(debt, 1),
        "avg_debt_per_day": round(avg_debt_per_day, 2),
    }


def suggested_bedtime(wake_time: str, target_hours: float = DEFAULT_TARGET_HOURS,
                       debt_hours: float = 0.0, max_extra_hours: float = 1.0) -> str:
    """Suggests tonight's bedtime given a wake-up time (HH:MM, 24h
    clock) and the target sleep duration, nudged up to `max_extra_hours`
    earlier to help pay down existing sleep debt - gradually (a quarter
    of the debt per night), not by recommending something unrealistic
    in a single night. Returns HH:MM. Handles wrap-past-midnight
    naturally (e.g. waking at 06:00 correctly suggests a bedtime the
    evening before)."""
    wake_dt = datetime.strptime(wake_time, "%H:%M")
    extra = min(max(debt_hours, 0) * 0.25, max_extra_hours)
    total_sleep_hours = target_hours + extra
    bedtime_dt = wake_dt - timedelta(hours=total_sleep_hours)
    return bedtime_dt.strftime("%H:%M")


def format_sleep_debt_summary(result: Dict[str, Any]) -> str:
    """Turns compute_sleep_debt()'s output into a friendly one-line
    summary - phrased as a surplus when debt is zero or negative,
    since "-2.0h of debt" reads oddly compared to "2.0h ahead"."""
    if result["logged_days"] == 0:
        return f"No sleep logged in the last {result['days']} days - log some sleep to see your debt."

    debt = result["total_debt_hours"]
    if debt <= 0:
        return (f"No sleep debt over the last {result['days']} days - you're averaging "
                 f"{-result['avg_debt_per_day']:.1f}h/night above your {result['target_hours']}h target.")
    return (f"Sleep debt over the last {result['days']} days: {debt}h total "
             f"({result['avg_debt_per_day']}h/night short of your {result['target_hours']}h target).")
