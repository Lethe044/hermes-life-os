"""
Hermes Life OS - Reminders
===========================
User-defined reminder/rule management: "remind me to stretch every day
at 9am", "remind me to call mom on Sundays". Reminders are created,
listed, edited, paused/resumed and deleted here, and - as of v1.37.0 -
actually delivered: `due_reminders()` / `scheduler_source()` plug into
scheduler.run_scheduler()'s `dynamic_source` hook (wired up in
run_scheduler.py), so a timed reminder fires through the same
notification channel as the daily briefings.

Stored in reminders.json (via load_reminders/save_reminders) as a list
of {"id", "text", "time", "days", "created"} dicts, plus an optional
"enabled": False once a reminder has been paused (a missing key means
enabled, so reminders saved by older versions keep working). Times are
normalized to 24-hour "HH:MM" when they can be understood ("9am",
"9:30pm", "7:05"); anything else is stored as given but, being
unparseable, will never fire. A reminder with no time is a day-level
note: it shows up in get_todays_reminders but is never pushed. No
network call is made by this module itself.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from storage import load_reminders, save_reminders

VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)?\s*$", re.IGNORECASE)


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


def create_reminder(text: str, time_str: Optional[str] = None,
                     days: Optional[List[str]] = None) -> Dict[str, Any]:
    """Saves a new reminder and returns the created entry. `time_str`
    is normalized to "HH:MM" when it is a recognizable time (see
    normalize_time); otherwise it is stored as given and the reminder
    will never fire. `days` is an optional list of 3-letter day codes
    (mon..sun, case-insensitive); unrecognized codes are dropped
    silently rather than rejecting the whole reminder, and an
    empty/omitted list means "every day".
    """
    entry = {
        "id": uuid.uuid4().hex[:8],
        "text": text,
        "time": _store_time(time_str),
        "days": _normalize_days(days),
        "created": time.strftime("%Y-%m-%d"),
    }
    reminders = load_reminders()
    reminders.append(entry)
    save_reminders(reminders)
    return entry


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
                    days: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Edits a reminder in place. Every argument left as None is left
    unchanged. `time_str=""` clears the time (turning it into an
    untimed, day-level note) and `days=[]` means "every day". Returns
    the updated entry, or None if no reminder has that id. Raises
    ValueError if `text` is given but blank."""
    if text is not None and not str(text).strip():
        raise ValueError("Reminder text cannot be empty.")

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


def is_enabled(reminder: Dict[str, Any]) -> bool:
    return reminder.get("enabled", True) is not False


def _applies_today(reminder: Dict[str, Any], now: datetime) -> bool:
    days = reminder.get("days") or []
    return not days or _WEEKDAY_CODES[now.weekday()] in days


def get_todays_reminders(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Active (not paused) reminders that apply on `now`'s weekday
    (local time by default), timed ones first in clock order, then
    untimed day-level notes."""
    now = now or datetime.now()
    todays = [r for r in load_reminders() if is_enabled(r) and _applies_today(r, now)]
    return sorted(todays, key=lambda r: (normalize_time(r.get("time")) is None,
                                         normalize_time(r.get("time")) or "",
                                         str(r.get("text", "")).lower()))


def due_reminders(now: datetime, grace_minutes: int = 2) -> List[Dict[str, Any]]:
    """Active reminders whose normalized time falls in the window
    [now - grace_minutes, now] on a day they apply to. The small grace
    window means a slow poll or a brief stall can't silently skip a
    reminder; the scheduler dedupes so each one is delivered at most
    once per day. Reminders with no (or unparseable) time never fire."""
    now_minutes = now.hour * 60 + now.minute
    due = []
    for r in load_reminders():
        if not is_enabled(r) or not _applies_today(r, now):
            continue
        hhmm = normalize_time(r.get("time"))
        if hhmm is None:
            continue
        reminder_minutes = int(hhmm[:2]) * 60 + int(hhmm[3:])
        if 0 <= now_minutes - reminder_minutes <= grace_minutes:
            due.append(r)
    return due


def scheduler_source(now: datetime) -> List[Tuple[str, str, str]]:
    """Adapter for scheduler.run_scheduler(dynamic_source=...): returns
    (dedupe_key, notification_title, message) for each reminder due at
    `now`. The key includes the reminder's current time, so editing a
    reminder to a later time the same day lets it fire again."""
    return [
        (f"reminder:{r['id']}@{normalize_time(r.get('time'))}",
         "Hermes Life OS - Reminder",
         str(r.get("text", "")))
        for r in due_reminders(now)
    ]


def _when_label(r: Dict[str, Any]) -> str:
    when_bits = []
    if r.get("time"):
        when_bits.append(r["time"])
    if r.get("days"):
        when_bits.append("/".join(r["days"]))
    return f" ({', '.join(when_bits)})" if when_bits else " (every day)"


def format_reminder_list(reminders: List[Dict[str, Any]]) -> str:
    """Turns list_reminders()'s output into a friendly multi-line
    summary. Paused reminders are marked."""
    if not reminders:
        return "No reminders set yet."

    lines = ["Reminders:"]
    for r in reminders:
        paused = " [paused]" if not is_enabled(r) else ""
        lines.append(f"- [{r.get('id', '?')}] {r.get('text', '')}{_when_label(r)}{paused}")
    return "\n".join(lines)


def format_todays_reminders(reminders: List[Dict[str, Any]]) -> str:
    """Turns get_todays_reminders()'s output into a friendly summary."""
    if not reminders:
        return "No reminders for today."
    lines = ["Reminders for today:"]
    for r in reminders:
        hhmm = normalize_time(r.get("time"))
        when = hhmm if hhmm else "any time"
        lines.append(f"- {when}: {r.get('text', '')} [{r.get('id', '?')}]")
    return "\n".join(lines)
