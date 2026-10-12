"""
Hermes Life OS - Clock
========================
The one place that answers "what day is it for the user right now?".

Every tracker (meals, sleep, spending, medication, ...) stamps each entry
with a calendar `date`. Those dates are the user's LOCAL calendar day, so
everything that reads them back - streaks, "last N days" windows, the
current budget month - has to use the same local day. Before v1.39.0 the
writers used the local clock while about a dozen readers used UTC, so
for several hours a day (00:00-03:00 in UTC+3, the whole evening in the
Americas, most of the day in UTC+14) a dose logged "today" did not count
towards today's streak, and an expense logged just after midnight on the
1st landed in the previous month's budget.

The memory journal (memory.jsonl) is different on purpose: its entries
carry a UTC `timestamp`, and the modules that read it (life score,
achievements, heatmap, correlations, "on this day") keep working in UTC.
Only the dated trackers use this module.

Night owls: set LIFE_OS_DAY_START_HOUR (0-12, default 0) to the hour your
day really starts. With LIFE_OS_DAY_START_HOUR=4, something logged at
01:30 counts for the previous calendar day, because to you it still is
yesterday night. Invalid values are ignored (treated as 0) and flagged by
hermes-life-os-doctor.

Tests simulate any time of day by monkeypatching `clock.now`; everything
else here is derived from it at call time.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Optional

DAY_START_ENV = "LIFE_OS_DAY_START_HOUR"
MAX_DAY_START_HOUR = 12


def now() -> datetime:
    """The real wall clock: naive local time. The only place the system
    clock is read for day-level logic."""
    return datetime.now()


def day_start_problem() -> Optional[str]:
    """A message describing what is wrong with LIFE_OS_DAY_START_HOUR, or
    None if it is unset or valid."""
    raw = os.environ.get(DAY_START_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return f"{DAY_START_ENV}={raw!r} is not a whole number, so it is being ignored (day starts at 00:00)."
    if not 0 <= value <= MAX_DAY_START_HOUR:
        return (f"{DAY_START_ENV}={value} is outside 0-{MAX_DAY_START_HOUR}, so it is being ignored "
                f"(day starts at 00:00).")
    return None


def day_start_hour() -> int:
    """The hour the user's day starts (0-12). 0 unless
    LIFE_OS_DAY_START_HOUR holds a valid whole number."""
    raw = os.environ.get(DAY_START_ENV, "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if 0 <= value <= MAX_DAY_START_HOUR else 0


def effective_now() -> datetime:
    """`now()` shifted back by the day-start hour, so its calendar date is
    the user's current "day" (and its year/month/day are the right ones
    for budgets and streaks)."""
    return now() - timedelta(hours=day_start_hour())


def today() -> date:
    """The user's current day."""
    return effective_now().date()


def today_str() -> str:
    """The user's current day as YYYY-MM-DD - what every tracker stamps
    onto a new entry."""
    return effective_now().strftime("%Y-%m-%d")


def days_ago_str(days: int) -> str:
    """The user's day `days` days before today, as YYYY-MM-DD (the cutoff
    for "the last N days" windows)."""
    return (effective_now() - timedelta(days=days)).strftime("%Y-%m-%d")


MAX_BACKDATE_DAYS = 365


def resolve_entry_date(value) -> str:
    """The date (YYYY-MM-DD) a new log entry should carry. `value` is the
    optional `date` a user gave when logging something afterwards ("I forgot
    to log yesterday's lunch"): None or blank means today. Raises ValueError
    with a user-readable message if it is not a real YYYY-MM-DD date, lies in
    the future, or is more than MAX_BACKDATE_DAYS days back. A date like
    "2026-1-5" is accepted and normalized to "2026-01-05"."""
    if value is None:
        return today_str()
    if not isinstance(value, str):
        raise ValueError("date must be written as YYYY-MM-DD, for example 2026-10-09.")
    text = value.strip()
    if not text:
        return today_str()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"'{text}' is not a valid date - write it as YYYY-MM-DD, "
                         f"for example 2026-10-09.") from None
    current = today()
    if parsed > current:
        raise ValueError(f"I can't log an entry for {parsed.isoformat()}: that date is in the future "
                         f"(today is {current.isoformat()}).")
    if parsed < current - timedelta(days=MAX_BACKDATE_DAYS):
        raise ValueError(f"I can't log an entry for {parsed.isoformat()}: it is more than "
                         f"{MAX_BACKDATE_DAYS} days ago.")
    return parsed.isoformat()


def month_str() -> str:
    """The user's current month as YYYY-MM."""
    return effective_now().strftime("%Y-%m")
