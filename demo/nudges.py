"""
Hermes Life OS - Proactive Nudges
====================================
Turns the analysis Hermes already does (anomaly detection, goal
progress, correlations) into short, actionable nudge messages -
without needing an LLM call. This is deliberately deterministic and
network-free so it can run on every scheduler tick cheaply and be
fully unit tested: it only reads what's already been logged and
reasons over it with plain statistics (see analytics.py).

Covers anomalies, goal progress, budgets that are over (or nearly
used up) for the month, a backup that has gone stale, and correlations.

Used by run_scheduler.py's "nudge_check" schedule entry to proactively
notify about something worth knowing, instead of waiting for the user
to ask.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from storage import get_recent_memory, load_goals
from analytics import detect_anomalies, compute_goal_progress, compute_correlations, format_correlation_insights
from budgets import budget_alerts
from backup import backup_alert

GOAL_REGRESSION_THRESHOLD = 50.0  # below this, a linked goal is worth flagging
MAX_PLANNER_NUDGES = 3            # task/renewal/people/savings/debt/countdown/supply/block/objective/trip nudges per run
MAX_BUDGET_NUDGES = 2             # budget warnings per run, so they can't crowd out everything else


def _planner_nudges() -> List[str]:
    """Overdue tasks, a subscription renewing within 3 days, a birthday, an
    overdue catch-up, a savings goal or a debt whose deadline is close, a countdown
    that is almost here, a supply that is about to run out, a time block that starts
    in a few minutes, an objective that ends unfinished or a trip with things left
    to pack. Each source is
    independent: one that fails (or has nothing) never blocks the others or the
    rest of the nudges."""
    out: List[str] = []
    try:
        import tasks
        msg = tasks.overdue_nudge()
        if msg:
            out.append(msg)
    except Exception:  # noqa: BLE001
        pass
    try:
        import subscriptions
        msg = subscriptions.renewal_nudge(3)
        if msg:
            out.append(msg)
    except Exception:  # noqa: BLE001
        pass
    try:
        import people
        out.extend(people.nudges(2))
    except Exception:  # noqa: BLE001
        pass
    try:
        import savings
        out.extend(savings.nudges(1))
    except Exception:  # noqa: BLE001
        pass
    for module, count in (("debts", 1), ("countdowns", 1), ("supplies", 1), ("timeblocks", 1), ("okrs", 1),
                          ("trips", 1)):
        try:
            out.extend(__import__(module).nudges(count))
        except Exception:  # noqa: BLE001
            pass
    return out[:MAX_PLANNER_NUDGES]


def generate_nudges(window_days: int = 7, max_nudges: int = 4) -> List[str]:
    """
    Returns a short list of plain-language nudge strings worth
    proactively surfacing, or an empty list if nothing stands out (the
    caller should treat an empty list as "nothing to say" and skip
    sending a notification, not as an error).
    """
    entries = get_recent_memory(days=window_days)
    nudges: List[str] = []

    for a in detect_anomalies(entries)[:2]:
        nudges.append(
            f"Your {a['metric']} on {a['date']} ({a['value']}) was unusually "
            f"{a['direction']} your recent average of {a['mean']}."
        )

    for goal in load_goals():
        if not goal.get("metric"):
            continue
        goal_window = goal.get("window_days", window_days)
        goal_entries = get_recent_memory(days=goal_window)
        progress = compute_goal_progress(goal, goal_entries)
        if progress is not None and progress < GOAL_REGRESSION_THRESHOLD:
            nudges.append(
                f"Goal '{goal['name']}' is at {progress}% - {goal['metric']} "
                f"{goal.get('direction', 'at_least').replace('_', ' ')} "
                f"{goal.get('target')}, last {goal_window} days."
            )

    nudges.extend(budget_alerts()[:MAX_BUDGET_NUDGES])

    nudges.extend(_planner_nudges())

    stale_backup = backup_alert()
    if stale_backup:
        nudges.append(stale_backup)

    correlations = compute_correlations(entries)
    nudges.extend(format_correlation_insights(correlations, limit=1))

    return nudges[:max_nudges]
