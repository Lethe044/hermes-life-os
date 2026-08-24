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
    20:00           proactive nudge check (LLM-free, silent if nothing stands out)
    20:30           automatic backup (LLM-free, silent on success)

Usage:
    Set one provider's key (or run a local Ollama server - no key needed):
        set ANTHROPIC_API_KEY=sk-ant-...
        set OPENAI_API_KEY=sk-...
        set OPENROUTER_API_KEY=sk-or-...
    Optionally pin the provider explicitly:
        set LIFE_OS_PROVIDER=anthropic
    Optionally run against a named profile instead of the default one:
        set LIFE_OS_PROFILE=alex
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


def make_runner(client, model: str):
    """Build a runner(mode) -> str that executes a real briefing and
    captures its rendered output as plain text for delivery."""
    from demo_life_os import DEMO_SCENARIOS, run_life_os, seed_demo_memory
    from nudges import generate_nudges

    def runner(mode: str) -> str:
        if mode == "nudge_check":
            # deterministic, no LLM call - empty string means "nothing
            # notable", which run_scheduler() treats as "don't notify"
            nudges = generate_nudges()
            return "\n".join(nudges) if nudges else ""

        if mode == "backup":
            # deterministic, no LLM call - silent on success (empty
            # string means "don't notify"), only speaks up on failure
            # so a broken backup can't go unnoticed indefinitely.
            from backup import run_backup

            try:
                out_path = run_backup()
                return "" if out_path else "Backup failed: no path returned."
            except Exception as exc:  # noqa: BLE001 - surface any failure via notifier
                return f"Backup failed: {exc}"

        seed_demo_memory()
        scenario = DEMO_SCENARIOS.get(mode)
        if scenario is None:
            return f"Unknown mode '{mode}', skipping."
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_life_os(scenario, client, model, max_turns=25)
        return buf.getvalue() or f"{mode} briefing ran with no captured output."

    return runner


def main():
    import storage
    from llm_providers import ProviderError, resolve_provider, default_model_for, get_client

    storage.set_active_profile(os.environ.get("LIFE_OS_PROFILE"))

    try:
        provider = resolve_provider(os.environ.get("LIFE_OS_PROVIDER"))
        client = get_client(provider)
    except ProviderError as e:
        print(e)
        sys.exit(1)

    model = os.environ.get("HERMES_MODEL") or default_model_for(provider)
    schedule = default_schedule()

    print(f"Hermes Life OS scheduler starting. Provider: {provider}  Model: {model}")
    print(f"Profile: {storage.ACTIVE_PROFILE}")
    print("Schedule:")
    for entry in schedule:
        days = ",".join(entry.days) if entry.days else "daily"
        print(f"  {entry.time_str}  {entry.mode:<10}  ({days})")
    print("Press Ctrl+C to stop.\n")

    runner = make_runner(client, model)

    def notifier(title: str, content: str) -> None:
        send_notification(title, content)

    try:
        run_scheduler(schedule, runner=runner, notifier=notifier, poll_seconds=60)
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


if __name__ == "__main__":
    main()
