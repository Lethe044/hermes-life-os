"""
Hermes Life OS - Insights Digest
====================================
A single "tell me something interesting" capstone over every existing
same-calendar-day correlation check (workout, social, reading vs mood;
substance vs sleep; each tracked habit vs mood) - instead of the
person having to know which of the six-plus separate correlation
tools to call, or call all of them just to see if anything stands out.
Only differences at or above `threshold` (in absolute value) are
surfaced; everything else is silently fine, which is the point - a
digest that repeats "not enough data" six times isn't useful. Pure
composition over the existing correlation modules, no new tracking of
its own, no network call.
"""

from __future__ import annotations

from typing import Any, Dict, List

from habit_correlation import compute_habit_mood_impact, format_habit_mood_impact
from reading_correlation import compute_reading_mood_impact, format_reading_mood_impact
from social_correlation import compute_social_mood_impact, format_social_mood_impact
from storage import load_habits, load_substance
from substance_correlation import compute_substance_sleep_impact, format_substance_sleep_impact
from workout_correlation import compute_workout_mood_impact, format_workout_mood_impact


def compute_insights_digest(days: int = 90, threshold: float = 1.0) -> Dict[str, Any]:
    """Runs every available correlation check and keeps only the ones
    with enough data and a difference of at least `threshold` (on
    whichever 0-10-ish scale that check uses). Returns {"days",
    "threshold", "findings": [{"label", "diff", "detail"}, ...]}
    sorted by the size of the difference, largest first.
    """
    findings: List[Dict[str, Any]] = []

    blanket_checks = [
        ("Workout vs mood", compute_workout_mood_impact(days), "mood_diff", format_workout_mood_impact),
        ("Social vs mood", compute_social_mood_impact(days), "mood_diff", format_social_mood_impact),
        ("Reading vs mood", compute_reading_mood_impact(days), "mood_diff", format_reading_mood_impact),
    ]
    for label, result, diff_key, formatter in blanket_checks:
        diff = result.get(diff_key)
        if diff is not None and abs(diff) >= threshold:
            findings.append({"label": label, "diff": diff, "detail": formatter(result)})

    for habit in load_habits():
        habit_name = habit.get("name", "")
        if not habit_name:
            continue
        result = compute_habit_mood_impact(habit_name, days)
        if result["mood_diff"] is not None and abs(result["mood_diff"]) >= threshold:
            findings.append({
                "label": f"'{habit_name}' vs mood", "diff": result["mood_diff"],
                "detail": format_habit_mood_impact(result),
            })

    distinct_substances = {s.get("substance", "") for s in load_substance() if s.get("substance")}
    for substance in distinct_substances:
        result = compute_substance_sleep_impact(substance, days)
        if result["sleep_diff"] is not None and abs(result["sleep_diff"]) >= threshold:
            findings.append({
                "label": f"'{substance}' vs sleep", "diff": result["sleep_diff"],
                "detail": format_substance_sleep_impact(result),
            })

    findings.sort(key=lambda f: -abs(f["diff"]))
    return {"days": days, "threshold": threshold, "findings": findings}


def format_insights_digest(result: Dict[str, Any]) -> str:
    """Turns compute_insights_digest()'s output into a friendly
    multi-line digest, one finding per line."""
    if not result["findings"]:
        return (f"Nothing stood out in the last {result['days']} days (no difference of "
                 f"{result['threshold']}+ points found) - either things are steady, or there "
                 f"isn't enough overlapping data yet to tell.")

    lines = [f"Here's what stood out in the last {result['days']} days:"]
    for f in result["findings"]:
        lines.append(f"- {f['label']}: {f['detail']}")
    return "\n".join(lines)
