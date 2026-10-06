"""
Hermes Life OS - Reminders
===========================
User-defined reminder/rule management: "remind me to stretch every day
at 9am", "remind me to call mom on Sundays". This module is deliberately
scoped to CRUD only - creating, listing and deleting saved reminders -
and does not itself trigger notifications or wire into scheduler.py's
run_scheduler() loop. scheduler.py's own DEFAULT_SCHEDULE_DEF entries
remain the only things that actually fire today; reminders created here
are a user-visible, queryable list of intentions, a foundation a later
round can connect to real delivery (notifications.py already has the
send_* machinery) once that integration can be exercised safely.

Stored in reminders.json (via load_reminders/save_reminders) as a list
of {"id", "text", "time", "days", "created"} dicts. No network call.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from storage import load_reminders, save_reminders

VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def create_reminder(text: str, time_str: Optional[str] = None,
                     days: Optional[List[str]] = None) -> Dict[str, Any]:
    """Saves a new reminder and returns the created entry. `time_str`
    is a free-form "HH:MM"-style hint (not validated against a clock -
    this module doesn't schedule anything itself, so it's stored as
    given). `days` is an optional list of 3-letter day codes (mon..sun,
    case-insensitive); unrecognized codes are dropped silently rather
    than rejecting the whole reminder, and an empty/omitted list means
    "every day".
    """
    normalized_days = []
    for d in (days or []):
        d_lower = str(d).lower()[:3]
        if d_lower in VALID_DAYS:
            normalized_days.append(d_lower)

    entry = {
        "id": uuid.uuid4().hex[:8],
        "text": text,
        "time": time_str,
        "days": normalized_days,
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


def format_reminder_list(reminders: List[Dict[str, Any]]) -> str:
    """Turns list_reminders()'s output into a friendly multi-line
    summary."""
    if not reminders:
        return "No reminders set yet."

    lines = ["Reminders:"]
    for r in reminders:
        when_bits = []
        if r.get("time"):
            when_bits.append(r["time"])
        if r.get("days"):
            when_bits.append("/".join(r["days"]))
        when = f" ({', '.join(when_bits)})" if when_bits else " (every day)"
        lines.append(f"- [{r.get('id', '?')}] {r.get('text', '')}{when}")
    return "\n".join(lines)
