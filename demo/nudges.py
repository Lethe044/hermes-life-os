"""
Hermes Life OS - Proactive Nudges
====================================
Turns the analysis Hermes already does (anomaly detection, goal
progress, correlations) into short, actionable nudge messages -
without needing an LLM call. This is deliberately deterministic and
network-free so it can run on every scheduler tick cheaply and be
fully unit tested: it only reads what's already been logged and
reasons over it with plain statistics (see analytics.py).

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

GOAL_REGRESSION_THRESHOLD = 50.0  # below this, a linked goal is worth flagging


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

    correlations = compute_correlations(entries)
    nudges.extend(format_correlation_insights(correlations, limit=1))

    return nudges[:max_nudges]
