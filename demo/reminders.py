"""
Hermes Life OS - Reminders
===========================
User-defined reminder/rule management: "remind me to stretch every day
at 9am", "remind me to call mom on Sundays", "remind me on 2026-11-02 to
renew my passport", "remind me in 20 minutes to check the oven".
Reminders are created, listed, edited, snoozed, paused/resumed and
deleted here, and delivered: `due_reminders()` / `scheduler_source()`
plug into scheduler.run_scheduler()'s `dynamic_source` hook (wired up in
run_scheduler.py), so a timed reminder fires through the same
notification channel as the daily briefings.

Stored in reminders.json (via load_reminders/save_reminders) as a list
of {"id", "text", "time", "days", "created"} dicts. Optional keys, only
present when used: "date" ("YYYY-MM-DD", a one-off reminder that applies
on that date only and ignores "days"), "enabled": False (paused; a
missing key means enabled, so reminders saved by older versions keep
working) and "snoozed_until" ("YYYY-MM-DDTHH:MM", local time).

Times are normalized to 24-hour "HH:MM" when they can be understood
("9am", "9:30pm", "7:05"); anything else is stored as given but, being
unparseable, will never fire. A reminder with no time is a day-level
note: it shows up in get_todays_reminders but is never pushed. All times
are the local machine clock, like scheduler.py. No network call is made
by this module itself.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from storage import load_reminders, save_reminders

VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)?\s*$", re.IGNORECASE)

MAX_SNOOZE_MINUTES = 24 * 60
_SNOOZE_FORMAT = "%Y-%m-%dT%H:%M"


def normalize_time(value: Any) -> Optional[str]:
    """Turns a clock-time hint into 24-hour "HH:MM", or None if it isn't
    a recognizable time. Accepts "9:00", "09:00", "17:30", "9am",
    "9:30pm", "12am" (midnight), "12pm" (noon). A bare number with no
    colon and no am/pm ("9") is ambiguous and rejected."""
    if value is None:
        return None
    m = _TIME_RE.match(str(value))
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) is not None else 0
    suffix = (m.group(3) or "").lower()
    if m.group(2) is None and not suffix:
        return None
    if minute > 59:
        return None
    if suffix:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    elif hour > 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def normalize_date(value: Any) -> Optional[str]:
    """Validates a "YYYY-MM-DD" date and returns it in that form. None or
    a blank string means "no date" and returns None. Anything else that is
    not a real calendar date raises ValueError."""
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(f"'{text}' is not a valid date - use YYYY-MM-DD, e.g. 2026-11-02.") from None


def _normalize_days(days: Optional[List[str]]) -> List[str]:
    normalized = []
    for d in (days or []):
        d_lower = str(d).lower()[:3]
        if d_lower in VALID_DAYS and d_lower not in normalized:
            normalized.append(d_lower)
    return normalized


def _store_time(time_str: Optional[str]) -> Optional[str]:
    """What to persist for a user-supplied time hint: the normalized
    "HH:MM" when understood, the stripped original when not, None when
    blank/absent."""
    if time_str is None:
        return None
    if not str(time_str).strip():
        return None
    return normalize_time(time_str) or str(time_str).strip()


def _check_minutes(minutes: Any) -> int:
    """Validates a minutes count for remind_me_in / snooze (1 minute to
    24 hours). Raises ValueError otherwise."""
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        raise ValueError("minutes must be a whole number.") from None
    if not 1 <= value <= MAX_SNOOZE_MINUTES:
        raise ValueError(f"minutes must be between 1 and {MAX_SNOOZE_MINUTES} (24 hours).")
    return value


def _target_after(now: datetime, minutes: int) -> datetime:
    """`now` plus `minutes`, rounded UP to the next whole minute so the
    reminder never fires before it was asked to."""
    target = now + timedelta(minutes=minutes)
    if target.second or target.microsecond:
        target = target.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return target


def create_reminder(text: str, time_str: Optional[str] = None,
                     days: Optional[List[str]] = None,
                     date: Optional[str] = None) -> Dict[str, Any]:
    """Saves a new reminder and returns the created entry. `time_str`
    is normalized to "HH:MM" when it is a recognizable time (see
    normalize_time); otherwise it is stored as given and the reminder
    will never fire. `days` is an optional list of 3-letter day codes
    (mon..sun, case-insensitive); unrecognized codes are dropped
    silently rather than rejecting the whole reminder, and an
    empty/omitted list means "every day". `date` ("YYYY-MM-DD") makes it a
    one-off reminder for that date only (`days` is then ignored and
    stored empty); an invalid date raises ValueError and saves nothing.
    """
    normalized_date = normalize_date(date)
    entry = {
        "id": uuid.uuid4().hex[:8],
        "text": text,
        "time": _store_time(time_str),
        "days": [] if normalized_date else _normalize_days(days),
        "created": time.strftime("%Y-%m-%d"),
    }
    if normalized_date:
        entry["date"] = normalized_date
    reminders = load_reminders()
    reminders.append(entry)
    save_reminders(reminders)
    return entry


def remind_me_in(text: str, minutes: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    """One-off reminder `minutes` from now ("remind me in 20 minutes to
    check the oven"), rounded up to the next whole minute. Handles
    crossing midnight (the reminder gets tomorrow's date). Raises
    ValueError for blank text or minutes outside 1..1440. It is delivered
    like any timed reminder, so the scheduler must be running."""
    if not str(text).strip():
        raise ValueError("Please say what to be reminded about.")
    minutes = _check_minutes(minutes)
    target = _target_after(now or datetime.now(), minutes)
    return create_reminder(str(text).strip(), target.strftime("%H:%M"),
                           date=target.strftime("%Y-%m-%d"))


def list_reminders() -> List[Dict[str, Any]]:
    """Returns every saved reminder, oldest first."""
    return load_reminders()


def delete_reminder(reminder_id: str) -> bool:
    """Removes a reminder by id. Returns True if found and removed,
    False if no reminder with that id existed."""
    reminders = load_reminders()
    remaining = [r for r in reminders if r.get("id") != reminder_id]
    if len(remaining) == len(reminders):
        return False
    save_reminders(remaining)
    return True


def update_reminder(reminder_id: str, text: Optional[str] = None,
                    time_str: Optional[str] = None,
                    days: Optional[List[str]] = None,
                    date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Edits a reminder in place. Every argument left as None is left
    unchanged. `time_str=""` clears the time (turning it into an
    untimed, day-level note) and `days=[]` means "every day". `date`
    ("YYYY-MM-DD") turns it into a one-off for that date (clearing
    `days`); `date=""` removes the date, making it recurring again. Giving
    a non-empty `days` to a one-off makes it recurring on those days.
    Returns the updated entry, or None if no reminder has that id. Raises
    ValueError - changing nothing - if `text` is blank or `date` is not a
    valid YYYY-MM-DD date."""
    if text is not None and not str(text).strip():
        raise ValueError("Reminder text cannot be empty.")
    clear_date = date is not None and not str(date).strip()
    new_date = None if clear_date else normalize_date(date)  # may raise

    reminders = load_reminders()
    for r in reminders:
        if r.get("id") != reminder_id:
            continue
        if text is not None:
            r["text"] = str(text).strip()
        if time_str is not None:
            r["time"] = _store_time(time_str)
        if days is not None:
            r["days"] = _normalize_days(days)
            if r["days"] and new_date is None:
                r.pop("date", None)  # explicit weekdays make it recurring
        if clear_date:
            r.pop("date", None)
        if new_date is not None:
            r["date"] = new_date
            r["days"] = []
        save_reminders(reminders)
        return r
    return None


def set_reminder_enabled(reminder_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
    """Pauses (enabled=False) or resumes (enabled=True) a reminder
    without deleting it. Returns the updated entry, or None if no
    reminder has that id."""
    reminders = load_reminders()
    for r in reminders:
        if r.get("id") != reminder_id:
            continue
        if enabled:
            r.pop("enabled", None)
        else:
            r["enabled"] = False
        save_reminders(reminders)
        return r
    return None


def snooze_reminder(reminder_id: str, minutes: Any = 10,
                    now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Delays a reminder: it will fire again `minutes` from now (default
    10, rounded up to the next whole minute), and its normal time is
    suppressed until then. Works on any reminder, including untimed
    day-level notes. Returns the updated entry, or None if no reminder has
    that id. Raises ValueError for minutes outside 1..1440."""
    minutes = _check_minutes(minutes)
    reminders = load_reminders()
    for r in reminders:
        if r.get("id") != reminder_id:
            continue
        r["snoozed_until"] = _target_after(now or datetime.now(), minutes).strftime(_SNOOZE_FORMAT)
        save_reminders(reminders)
        return r
    return None


def clear_past_reminders(now: Optional[datetime] = None) -> int:
    """Deletes one-off reminders whose date is before today (they can
    never fire again). Returns how many were removed. Recurring and
    still-upcoming reminders are untouched."""
    today = (now or datetime.now()).strftime("%Y-%m-%d")
    reminders = load_reminders()
    remaining = [r for r in reminders if not (r.get("date") and r["date"] < today)]
    removed = len(reminders) - len(remaining)
    if removed:
        save_reminders(remaining)
    return removed


def is_enabled(reminder: Dict[str, Any]) -> bool:
    return reminder.get("enabled", True) is not False


def _applies_today(reminder: Dict[str, Any], now: datetime) -> bool:
    date = reminder.get("date")
    if date:
        return date == now.strftime("%Y-%m-%d")
    days = reminder.get("days") or []
    return not days or _WEEKDAY_CODES[now.weekday()] in days


def _snoozed_until(reminder: Dict[str, Any]) -> Optional[datetime]:
    value = reminder.get("snoozed_until")
    if not value:
        return None
    try:
        return datetime.strptime(str(value), _SNOOZE_FORMAT)
    except ValueError:
        return None


def get_todays_reminders(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Active (not paused) reminders that apply on `now`'s date (local
    time by default) - one-offs dated today plus recurring ones whose
    weekday matches - timed ones first in clock order, then untimed
    day-level notes."""
    now = now or datetime.now()
    todays = [r for r in load_reminders() if is_enabled(r) and _applies_today(r, now)]
    return sorted(todays, key=lambda r: (normalize_time(r.get("time")) is None,
                                         normalize_time(r.get("time")) or "",
                                         str(r.get("text", "")).lower()))


def _due_items(now: datetime, grace_minutes: int) -> List[Tuple[Dict[str, Any], str]]:
    """(reminder, key suffix) for everything due at `now`. A reminder that
    is snoozed fires at its snooze time instead of its normal time, and
    only then; the suffix differs so the scheduler's once-per-day dedupe
    lets the snoozed delivery through after the original one."""
    now_minute = now.replace(second=0, microsecond=0)
    items = []
    for r in load_reminders():
        if not is_enabled(r):
            continue

        snooze = _snoozed_until(r)
        if snooze is not None and now_minute < snooze:
            continue  # snoozed: the normal time is suppressed until the snooze time
        if snooze is not None:
            late = (now_minute - snooze).total_seconds() / 60
            if 0 <= late <= grace_minutes:
                items.append((r, f"snooze:{r['snoozed_until']}"))
                continue

        if not _applies_today(r, now):
            continue
        hhmm = normalize_time(r.get("time"))
        if hhmm is None:
            continue
        reminder_minutes = int(hhmm[:2]) * 60 + int(hhmm[3:])
        if 0 <= now.hour * 60 + now.minute - reminder_minutes <= grace_minutes:
            items.append((r, f"{r['date']}T{hhmm}" if r.get("date") else hhmm))
    return items


def due_reminders(now: datetime, grace_minutes: int = 2) -> List[Dict[str, Any]]:
    """Active reminders that should fire at `now`: either their
    normalized time falls in the window [now - grace_minutes, now] on a
    date they apply to, or a snooze they were given has just expired.
    The small grace window means a slow poll or a brief stall can't
    silently skip a reminder; the scheduler dedupes so each one is
    delivered at most once per day per time. Reminders with no (or
    unparseable) time never fire on their own, and a snoozed reminder does
    not fire at its normal time until the snooze is over."""
    return [r for r, _ in _due_items(now, grace_minutes)]


def scheduler_source(now: datetime) -> List[Tuple[str, str, str]]:
    """Adapter for scheduler.run_scheduler(dynamic_source=...): returns
    (dedupe_key, notification_title, message) for each reminder due at
    `now`. The key includes the reminder's current time (and date, or
    snooze time), so editing a reminder to a later time the same day, or
    snoozing it, lets it fire again."""
    return [
        (f"reminder:{r['id']}@{suffix}", "Hermes Life OS - Reminder", str(r.get("text", "")))
        for r, suffix in _due_items(now, 2)
    ]


def _when_label(r: Dict[str, Any]) -> str:
    when_bits = []
    if r.get("date"):
        when_bits.append(r["date"])
    if r.get("time"):
        when_bits.append(r["time"])
    if not r.get("date") and r.get("days"):
        when_bits.append("/".join(r["days"]))
    return f" ({', '.join(when_bits)})" if when_bits else " (every day)"


def _status_labels(r: Dict[str, Any], now: datetime) -> str:
    labels = ""
    if r.get("date") and r["date"] < now.strftime("%Y-%m-%d"):
        labels += " [past]"
    snooze = _snoozed_until(r)
    if snooze is not None and snooze > now:
        labels += f" [snoozed until {snooze.strftime('%Y-%m-%d %H:%M')}]"
    if not is_enabled(r):
        labels += " [paused]"
    return labels


def format_reminder_list(reminders: List[Dict[str, Any]], now: Optional[datetime] = None) -> str:
    """Turns list_reminders()'s output into a friendly multi-line
    summary. Paused, snoozed and past one-off reminders are marked."""
    if not reminders:
        return "No reminders set yet."

    now = now or datetime.now()
    lines = ["Reminders:"]
    for r in reminders:
        lines.append(f"- [{r.get('id', '?')}] {r.get('text', '')}{_when_label(r)}{_status_labels(r, now)}")
    return "\n".join(lines)


def format_todays_reminders(reminders: List[Dict[str, Any]], now: Optional[datetime] = None) -> str:
    """Turns get_todays_reminders()'s output into a friendly summary."""
    if not reminders:
        return "No reminders for today."
    now = now or datetime.now()
    lines = ["Reminders for today:"]
    for r in reminders:
        hhmm = normalize_time(r.get("time"))
        when = hhmm if hhmm else "any time"
        snooze = _snoozed_until(r)
        extra = f" [snoozed until {snooze.strftime('%H:%M')}]" if snooze is not None and snooze > now else ""
        lines.append(f"- {when}: {r.get('text', '')} [{r.get('id', '?')}]{extra}")
    return "\n".join(lines)
