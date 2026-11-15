"""
Hermes Life OS - Metric series
================================
The one place the newer cross-domain modules (experiments, tripwires) read
logged numbers from. `load_daily()` collapses the raw memory entries into
{date: {metric: daily average}}; `values()` slices one metric over a range of
days; `state_value()` reads a few live planner counts (overdue tasks, inbox
size, overdue follow-ups) that tripwires can watch too. Local arithmetic only,
no storage of its own and no network call.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

import clock

# Logged metrics (from analytics.extract_metric) a module may track.
LOGGED = ("mood", "energy", "stress", "sleep", "hydration", "meeting_hours", "readiness", "spending",
          "social_quality", "caffeine", "reading_min")
# Live planner counts, read as they are right now.
STATE = ("overdue_tasks", "open_tasks", "inbox_items", "overdue_follow_ups")
METRICS = LOGGED + STATE
# For these a lower value is the better direction.
LOWER_IS_BETTER = {"stress", "spending", "caffeine", "meeting_hours", "overdue_tasks", "open_tasks",
                   "inbox_items", "overdue_follow_ups"}
HISTORY_DAYS = 400


def check_metric(value: Any, allow_state: bool = True) -> str:
    key = value.strip().lower().replace(" ", "_") if isinstance(value, str) else ""
    pool = METRICS if allow_state else LOGGED
    if key not in pool:
        raise ValueError(f"the metric must be one of {', '.join(pool)}.")
    return key


def load_daily() -> Dict[str, Dict[str, float]]:
    """{date: {metric: average}} for the last HISTORY_DAYS days of memory."""
    import analytics
    import storage
    return analytics.daily_averages(storage.get_recent_memory(days=HISTORY_DAYS))


def values(daily: Dict[str, Dict[str, float]], metric: str, first: str, last: str) -> Dict[str, float]:
    """{date: value} for `metric` on the days from `first` to `last` (inclusive)
    that have a reading."""
    return {d: row[metric] for d, row in daily.items()
            if first <= d <= last and isinstance(row, dict) and isinstance(row.get(metric), (int, float))}


def day_minus(day: str, n: int) -> str:
    return (clock.parse_day(day) - timedelta(days=n)).isoformat()


def state_value(name: str) -> Optional[int]:
    """The live count behind a STATE metric, None when it cannot be read."""
    today = clock.today_str()
    try:
        if name in ("overdue_tasks", "open_tasks"):
            import tasks
            open_rows = [t for t in tasks._rows(tasks._load()) if not t.get("done")]
            if name == "open_tasks":
                return len(open_rows)
            return sum(1 for t in open_rows if isinstance(t.get("due"), str) and t["due"] < today)
        if name == "inbox_items":
            import inbox
            return len(inbox._load()) if hasattr(inbox, "_load") else None
        if name == "overdue_follow_ups":
            import waiting
            return sum(1 for r in waiting.open_items() if str(r.get("chase")) < today)
    except Exception:  # noqa: BLE001
        return None
    return None
