"""
Hermes Life OS - Recommendations
====================================
A lightweight, fully local, rule-based suggestion engine. Turns
patterns already visible in the correlation engine, simple thresholds
on recent averages, and near-milestone habit streaks into concrete,
actionable suggestions - e.g. "sleep's been under 6.5h lately, an
earlier bedtime tonight might help" or "you're 2 days from a 30-day
streak on 'meditate' - keep it going!".

No LLM call, no network request - just transparent rules over data
that's already being tracked, so every suggestion can point to exactly
the numbers that produced it (see each suggestion's "value"/"metric"
fields). Not a medical or therapeutic recommendation system - purely a
reflection of your own patterns, phrased as a nudge.
"""

from __future__ import annotations

from typing import Any, Dict, List

from analytics import (
    compute_correlations,
    compute_lagged_correlations,
    daily_averages,
    format_correlation_insights,
    format_lagged_insights,
)
from storage import get_recent_memory, load_habits

# metric -> (threshold, direction, message). direction "below" fires
# when the recent average is under the threshold (e.g. sleep, hydration);
# "above" fires when it's over (e.g. stress).
THRESHOLDS = {
    "sleep":     (6.5, "below", "Average sleep has been under {value}h lately - an earlier bedtime tonight might help."),
    "hydration": (5.0, "below", "Hydration's been running low ({value}/day) - keep a water bottle nearby today."),
    "stress":    (7.0, "above", "Stress has been running high ({value}/10) - a short walk or a few minutes of quiet time might help."),
}

STREAK_MILESTONES = (7, 30, 100)


def _threshold_suggestions(daily: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    suggestions = []
    for metric, (threshold, direction, message) in THRESHOLDS.items():
        values = [day[metric] for day in daily.values() if metric in day]
        if not values:
            continue
        avg = round(sum(values) / len(values), 1)
        fires = avg < threshold if direction == "below" else avg > threshold
        if fires:
            suggestions.append({
                "type": "threshold",
                "metric": metric,
                "value": avg,
                "message": message.format(value=avg),
            })
    return suggestions


def _correlation_suggestions(entries: List[Dict[str, Any]], limit: int = 2) -> List[Dict[str, Any]]:
    same_day = compute_correlations(entries)
    lagged = compute_lagged_correlations(entries)
    suggestions = []
    for text in format_correlation_insights(same_day, limit=limit):
        suggestions.append({"type": "correlation", "message": text})
    for text in format_lagged_insights(lagged, limit=limit):
        suggestions.append({"type": "lagged_correlation", "message": text})
    return suggestions


def _streak_suggestions(habits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    suggestions = []
    for habit in habits:
        streak = habit.get("streak", 0)
        name = habit.get("name", "habit")
        for milestone in STREAK_MILESTONES:
            days_left = milestone - streak
            if 0 < days_left <= 2:
                day_word = "day" if days_left == 1 else "days"
                suggestions.append({
                    "type": "streak",
                    "habit": name,
                    "days_left": days_left,
                    "message": f"You're {days_left} {day_word} from a {milestone}-day streak "
                               f"on '{name}' - keep it going!",
                })
                break  # only the nearest upcoming milestone per habit
    return suggestions


def get_recommendations(days: int = 14) -> List[Dict[str, Any]]:
    """Returns a list of suggestion dicts (each with at least "type" and
    "message"), combining threshold-based nudges, correlation-derived
    insights, and near-milestone habit streaks. Order: thresholds first
    (most directly actionable), then correlations, then streaks. Returns
    an empty list rather than an error when there's not enough data -
    "no suggestions yet" is a valid, expected state for a new profile."""
    entries = get_recent_memory(days)
    daily = daily_averages(entries)
    habits = load_habits()

    suggestions: List[Dict[str, Any]] = []
    suggestions += _threshold_suggestions(daily)
    suggestions += _correlation_suggestions(entries)
    suggestions += _streak_suggestions(habits)
    return suggestions
