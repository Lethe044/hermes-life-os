"""
Hermes Life OS - Scheduler
============================
A lightweight, dependency-free cron-style scheduler that triggers
briefing modes at configured times, matching the "Daily Rhythm" table
in skills/life-os/SKILL.md:

    07:00           morning briefing
    12:00           midday check-in
    18:00           evening reflection
    Monday 08:00    weekly review

The scheduling logic (`due_entries`, `ScheduleEntry`) is pure and has
no dependency on the OpenAI client, rich console, or network access,
so it can be fully unit tested. The actual "do the work" and "deliver
the result" steps are injected as callables (`runner` / `notifier`),
keeping this module decoupled from demo_life_os.py and notifications.py.

Usage (see demo/run_scheduler.py for the wired-up production entry point):

    from scheduler import ScheduleEntry, run_scheduler

    schedule = [
        ScheduleEntry("07:00", "morning"),
        ScheduleEntry("12:00", "checkin"),
        ScheduleEntry("18:00", "evening"),
        ScheduleEntry("08:00", "weekly", days=["Monday"]),
    ]

    run_scheduler(schedule, runner=my_runner, notifier=my_notifier)
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

DEFAULT_SCHEDULE_DEF = [
    ("07:00", "morning", None),
    ("12:00", "checkin", None),
    ("18:00", "evening", None),
    ("08:00", "weekly", ["Monday"]),
    ("20:00", "nudge_check", None),
    ("20:30", "backup", None),
]


@dataclass
class ScheduleEntry:
    """A single scheduled trigger.

    time_str: "HH:MM" 24-hour, matched against the local machine clock.
    mode: the briefing mode to run (must be a key in DEMO_SCENARIOS).
    days: optional list of weekday names (e.g. ["Monday"]) restricting
          this entry to specific days. None means every day.
    """
    time_str: str
    mode: str
    days: Optional[List[str]] = None

    @property
    def id(self) -> str:
        days_key = ",".join(self.days) if self.days else "daily"
        return f"{self.mode}@{self.time_str}[{days_key}]"


def default_schedule() -> List[ScheduleEntry]:
    return [ScheduleEntry(t, m, d) for t, m, d in DEFAULT_SCHEDULE_DEF]


def _matches_day(entry: ScheduleEntry, now: datetime) -> bool:
    if not entry.days:
        return True
    return now.strftime("%A") in entry.days


def due_entries(
    schedule: List[ScheduleEntry],
    now: datetime,
    last_run: Dict[str, str],
) -> List[ScheduleEntry]:
    """
    Return schedule entries that should fire at `now`.

    An entry is due when its time_str matches now's HH:MM, its day
    restriction (if any) matches now's weekday, and it hasn't already
    fired today (tracked via `last_run`: entry.id -> "YYYY-MM-DD").
    This makes the function safe to call every poll interval without
    double-firing within the same minute or across restarts within
    the same day (as long as last_run is persisted/passed back in).
    """
    now_hhmm = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    due = []
    for entry in schedule:
        if entry.time_str != now_hhmm:
            continue
        if not _matches_day(entry, now):
            continue
        if last_run.get(entry.id) == today:
            continue
        due.append(entry)
    return due


def run_scheduler(
    schedule: Optional[List[ScheduleEntry]] = None,
    runner: Optional[Callable[[str], str]] = None,
    notifier: Optional[Callable[[str, str], None]] = None,
    poll_seconds: int = 30,
    max_iterations: Optional[int] = None,
    clock: Optional[Callable[[], datetime]] = None,
    sleeper: Optional[Callable[[float], None]] = None,
    dynamic_source: Optional[Callable[[datetime], List[Tuple[str, str, str]]]] = None,
) -> Dict[str, str]:
    """
    Blocking loop that polls the clock every `poll_seconds` and fires
    due schedule entries via `runner`, delivering the result via
    `notifier`. Returns the final last_run map (mostly useful for tests).

    - runner(mode) -> str: executes the briefing (e.g. calls run_life_os
      and returns the delivered content) for the given mode.
    - notifier(mode, content) -> None: delivers the result (e.g. via
      notifications.send_notification).
    - max_iterations: if set, the loop stops after this many polls
      instead of running forever (used by tests and for dry-runs).
    - clock/sleeper: injectable for deterministic testing.
    - dynamic_source(now) -> [(key, title, message), ...]: optional hook
      for things that aren't a fixed (time, mode) pair, such as
      user-defined reminders (see reminders.scheduler_source). Called
      once per poll; each returned item is delivered through `notifier`
      at most once per day per `key`. A failing source or notifier is
      reported on stderr and never stops the loop. These deliveries are
      tracked separately and are NOT part of the returned last_run map.
    """
    schedule = schedule if schedule is not None else default_schedule()
    clock = clock or datetime.now
    sleeper = sleeper or time.sleep
    last_run: Dict[str, str] = {}
    dynamic_last_run: Dict[str, str] = {}

    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        now = clock()
        for entry in due_entries(schedule, now, last_run):
            last_run[entry.id] = now.strftime("%Y-%m-%d")
            content = ""
            if runner is not None:
                try:
                    content = runner(entry.mode)
                except Exception as e:
                    content = f"[scheduler] runner failed for mode '{entry.mode}': {e}"
            if notifier is not None and content:
                title = f"Hermes Life OS - {entry.mode.title()}"
                notifier(title, content)

        if dynamic_source is not None:
            today = now.strftime("%Y-%m-%d")
            try:
                items = dynamic_source(now)
            except Exception as e:  # noqa: BLE001 - a broken source must not kill the loop
                print(f"[scheduler] dynamic source failed: {e}", file=sys.stderr)
                items = []
            for key, title, message in items:
                if dynamic_last_run.get(key) == today:
                    continue
                dynamic_last_run[key] = today
                if notifier is not None and message:
                    try:
                        notifier(title, message)
                    except Exception as e:  # noqa: BLE001
                        print(f"[scheduler] notifier failed for '{key}': {e}", file=sys.stderr)
        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            sleeper(poll_seconds)

    return last_run
