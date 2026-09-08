"""
Hermes Life OS - Stress Summary
===================================
Summarizes recent stress logging - average score, a first-half vs.
second-half trend within the window, the most common triggers, and how
many days crossed a "high stress" threshold. Pure local arithmetic
over data already in mental.json (via load_mental), no new tracking or
storage of its own, no network call.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict

from storage import load_mental

HIGH_STRESS_THRESHOLD = 7


def compute_stress_summary(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "total_entries", "avg_score", "trend",
    "high_stress_days", "top_triggers": [(trigger, count), ...]} over
    the last `days` days. "trend" is one of "improving" (second half
    of the window averaged noticeably lower than the first half),
    "worsening" (noticeably higher), or "steady" - "noticeably" means
    at least a 1.0-point difference on the 0-10 scale, to avoid
    flip-flopping on tiny amounts of data.
    """
    cutoff_dt = datetime.utcnow() - timedelta(days=days)
    cutoff = cutoff_dt.strftime("%Y-%m-%d")
    entries = [m for m in load_mental() if m.get("score") is not None and m.get("date", "") >= cutoff]

    if not entries:
        return {"days": days, "total_entries": 0, "avg_score": 0.0, "trend": "steady",
                "high_stress_days": 0, "top_triggers": []}

    entries.sort(key=lambda e: e.get("date", ""))
    scores = [e["score"] for e in entries]
    avg_score = sum(scores) / len(scores)
    high_stress_days = len({e["date"] for e in entries if e["score"] >= HIGH_STRESS_THRESHOLD})

    midpoint = len(entries) // 2
    first_half = scores[:midpoint] or scores
    second_half = scores[midpoint:] or scores
    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)
    diff = second_avg - first_avg
    if diff <= -1.0:
        trend = "improving"
    elif diff >= 1.0:
        trend = "worsening"
    else:
        trend = "steady"

    triggers = Counter(e.get("trigger", "") for e in entries if e.get("trigger"))
    top_triggers = triggers.most_common(5)

    return {
        "days": days,
        "total_entries": len(entries),
        "avg_score": round(avg_score, 1),
        "trend": trend,
        "high_stress_days": high_stress_days,
        "top_triggers": top_triggers,
    }


def format_stress_summary(result: Dict[str, Any]) -> str:
    """Turns compute_stress_summary()'s output into a friendly
    multi-line summary."""
    if result["total_entries"] == 0:
        return f"No stress logged in the last {result['days']} days."

    lines = [
        f"Average stress {result['avg_score']}/10 over the last {result['days']} days "
        f"({result['total_entries']} entries), trend: {result['trend']}.",
    ]
    if result["high_stress_days"] > 0:
        lines.append(f"High-stress days (score >= {HIGH_STRESS_THRESHOLD}): {result['high_stress_days']}.")
    if result["top_triggers"]:
        triggers_str = ", ".join(f"{t} ({c})" for t, c in result["top_triggers"])
        lines.append(f"Top triggers: {triggers_str}.")
    return "\n".join(lines)
