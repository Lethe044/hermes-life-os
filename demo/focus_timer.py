"""
Hermes Life OS - Focus Timer
================================
A simple terminal Pomodoro-style countdown that logs a focus session
automatically when it completes, via the same logging path
`log_focus_session` uses in chat - so this isn't "a Pomodoro app AND a
separate logger", just one command that runs the timer and records it.

Usage:
    hermes-life-os-focus                       # 25 minutes, unnamed
    hermes-life-os-focus 50 --task "writing"
    hermes-life-os-focus 25 --task "deep work" --break 5

Ctrl+C during the countdown stops it early and does NOT log a session
(an abandoned session isn't a completed one) - a break in progress can
also be Ctrl+C'd without affecting the already-logged focus session.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage


def _countdown(seconds: int, label: str) -> None:
    """Prints a live, self-overwriting countdown line to the terminal.
    Raises KeyboardInterrupt upward on Ctrl+C rather than swallowing it
    - callers decide what an early stop means (e.g. "don't log this")."""
    for remaining in range(seconds, 0, -1):
        mins, secs = divmod(remaining, 60)
        print(f"\r{label}: {mins:02d}:{secs:02d} remaining ", end="", flush=True)
        time.sleep(1)
    print(f"\r{label}: done!" + " " * 20)


def run_focus_session(minutes: int, task: str = "", log: bool = True) -> bool:
    """Runs the countdown for `minutes`. Returns True if it completed
    naturally, False if interrupted early (Ctrl+C). Logs the session
    via tools.dispatch_tool("log_focus_session", ...) on completion
    when `log` is True - reuses the exact same logging path a
    chat-based "start a focus session" request would use, so a
    completed timer and a chat-logged session are indistinguishable in
    your data afterward."""
    label = f"Focus: {task}" if task else "Focus session"
    try:
        _countdown(minutes * 60, label)
    except KeyboardInterrupt:
        print("\nSession stopped early - not logged.")
        return False

    if log:
        from tools import dispatch_tool
        result = dispatch_tool("log_focus_session", {
            "duration_min": minutes,
            "task": task or "focus session",
            "completed": True,
        })
        print(result)
    return True


def run_break(minutes: int) -> None:
    """Runs a break countdown. Never logged (breaks aren't focus
    sessions) - Ctrl+C here just ends the break early with no other
    side effects."""
    try:
        _countdown(minutes * 60, "Break")
    except KeyboardInterrupt:
        print("\nBreak stopped early.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a focus/Pomodoro timer that logs itself when it completes")
    parser.add_argument("minutes", type=int, nargs="?", default=25,
                        help="Focus duration in minutes. Default 25.")
    parser.add_argument("--task", default="", help="What you're focusing on.")
    parser.add_argument("--break", dest="break_minutes", type=int, default=0,
                        help="Optional break countdown to run immediately after completion. Default: none.")
    parser.add_argument("--no-log", action="store_true", help="Don't log the session when it completes.")
    parser.add_argument("--profile", default=None, help="Profile to log to. Default: active/default.")
    args = parser.parse_args()

    storage.set_active_profile(args.profile)
    completed = run_focus_session(args.minutes, args.task, log=not args.no_log)

    if completed and args.break_minutes > 0:
        run_break(args.break_minutes)


if __name__ == "__main__":
    main()
