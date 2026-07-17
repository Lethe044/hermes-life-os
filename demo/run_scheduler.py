#!/usr/bin/env python3
"""
Hermes Life OS - Scheduler Entry Point
==========================================
Wires scheduler.run_scheduler() up to the real briefing generation
(demo_life_os.run_life_os) and real delivery (notifications.send_notification),
implementing the "Daily Rhythm" cron table from skills/life-os/SKILL.md:

    07:00           morning briefing
    12:00           midday check-in
    18:00           evening reflection
    Monday 08:00    weekly review

Usage:
    set OPENROUTER_API_KEY=sk-or-...
    set HERMES_NOTIFY_CHANNEL=telegram   (optional; defaults to console)
    python run_scheduler.py

Runs forever, polling once a minute, until interrupted (Ctrl+C).
"""

from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scheduler import default_schedule, run_scheduler
from notifications import send_notification


def make_runner(api_key: str, model: str):
    """Build a runner(mode) -> str that executes a real briefing and
    captures its rendered output as plain text for delivery."""
    from demo_life_os import DEMO_SCENARIOS, run_life_os, seed_demo_memory

    def runner(mode: str) -> str:
        seed_demo_memory()
        scenario = DEMO_SCENARIOS.get(mode)
        if scenario is None:
            return f"Unknown mode '{mode}', skipping."
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_life_os(scenario, api_key, model, max_turns=25)
        return buf.getvalue() or f"{mode} briefing ran with no captured output."

    return runner


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Set OPENROUTER_API_KEY first (see demo_life_os.py --help).")
        sys.exit(1)

    model = os.environ.get("HERMES_MODEL", "anthropic/claude-3.5-sonnet")
    schedule = default_schedule()

    print("Hermes Life OS scheduler starting. Schedule:")
    for entry in schedule:
        days = ",".join(entry.days) if entry.days else "daily"
        print(f"  {entry.time_str}  {entry.mode:<10}  ({days})")
    print("Press Ctrl+C to stop.\n")

    runner = make_runner(api_key, model)

    def notifier(title: str, content: str) -> None:
        send_notification(title, content)

    try:
        run_scheduler(schedule, runner=runner, notifier=notifier, poll_seconds=60)
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


if __name__ == "__main__":
    main()
