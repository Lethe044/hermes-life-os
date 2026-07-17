"""
Hermes Life OS - Pattern Detection
====================================
Analyzes recent memory for trends across mood, energy, sleep, hydration,
stress, dreams, and habit streaks, and surfaces real statistical
correlations via analytics.py.

Extracted from the original monolithic demo_life_os.py.
"""

from __future__ import annotations

from typing import Any, Dict

from storage import get_recent_memory, load_habits
from analytics import compute_correlations, format_correlation_insights

# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

def detect_patterns() -> Dict[str, Any]:
    recent = get_recent_memory(days=14)
    patterns: Dict[str, Any] = {
        "mood_trend": None, "energy_trend": None,
        "sleep_trend": None, "hydration_trend": None,
        "nutrition_trend": None, "stress_trend": None,
        "habit_streaks": {}, "wins": [], "struggles": [],
        "correlations": [], "insights": [],
    }

    mood_scores, energy_levels, stress_scores = [], [], []
    sleep_hours, water_glasses = [], []

    for entry in recent:
        t = entry.get("type", "")
        if t == "mood":
            mood_scores.append(entry.get("score", 0))
        elif t == "energy":
            energy_levels.append(entry.get("level", "medium"))
        elif t == "stress":
            stress_scores.append(entry.get("score", 0))
        elif t == "sleep":
            sleep_hours.append(entry.get("hours", 0))
        elif t == "hydration":
            water_glasses.append(entry.get("glasses", 0))
        elif t == "win":
            patterns["wins"].append(entry.get("description", ""))
        elif t == "struggle":
            if not entry.get("resolved"):
                patterns["struggles"].append(entry.get("description", ""))

    # Mood trend
    if mood_scores:
        avg = sum(mood_scores) / len(mood_scores)
        patterns["mood_trend"] = (
            f"strong (avg {avg:.1f}/10)" if avg >= 7 else
            f"steady (avg {avg:.1f}/10)" if avg >= 5 else
            f"challenging (avg {avg:.1f}/10)"
        )
        if len(mood_scores) >= 3 and all(s < 6 for s in mood_scores[-3:]):
            patterns["insights"].append(
                "Three consecutive tough days detected. This pattern is worth addressing."
            )

    # Energy trend
    if energy_levels:
        low = energy_levels.count("low")
        high = energy_levels.count("high")
        patterns["energy_trend"] = (
            "mostly high" if high > low else
            "running low lately" if low > high else "mixed"
        )

    # Sleep trend
    if sleep_hours:
        avg_sleep = sum(sleep_hours) / len(sleep_hours)
        patterns["sleep_trend"] = (
            f"well-rested (avg {avg_sleep:.1f}h)" if avg_sleep >= 7.5 else
            f"slightly short (avg {avg_sleep:.1f}h)" if avg_sleep >= 6 else
            f"sleep-deprived (avg {avg_sleep:.1f}h)"
        )
        if avg_sleep < 6.5:
            patterns["insights"].append(
                f"Averaging only {avg_sleep:.1f}h sleep. This is likely affecting your mood and focus."
            )

    # Hydration trend
    if water_glasses:
        avg_water = sum(water_glasses) / len(water_glasses)
        patterns["hydration_trend"] = (
            f"well hydrated (avg {avg_water:.1f} glasses)" if avg_water >= 8 else
            f"slightly low (avg {avg_water:.1f} glasses)" if avg_water >= 5 else
            f"dehydrated (avg {avg_water:.1f} glasses)"
        )

    # Stress trend
    if stress_scores:
        avg_stress = sum(stress_scores) / len(stress_scores)
        patterns["stress_trend"] = (
            f"low stress (avg {avg_stress:.1f}/10)" if avg_stress < 4 else
            f"moderate stress (avg {avg_stress:.1f}/10)" if avg_stress < 7 else
            f"high stress (avg {avg_stress:.1f}/10)"
        )
        if avg_stress >= 7:
            patterns["insights"].append(
                f"Stress levels averaging {avg_stress:.1f}/10. Consider reviewing workload and recovery habits."
            )

    # Correlations - real Pearson correlation across tracked metrics,
    # computed on daily-averaged values (see analytics.py)
    correlations = compute_correlations(recent)
    patterns["correlation_details"] = correlations
    patterns["correlations"].extend(format_correlation_insights(correlations))

    # Dream patterns
    dream_entries = [r for r in recent if r.get("type") == "dream"]
    if dream_entries:
        all_symbols = []
        tones = []
        for d in dream_entries:
            all_symbols.extend(d.get("symbols", []))
            tones.append(d.get("tone", "neutral"))
        negative_tones = tones.count("negative")
        if negative_tones >= 3:
            patterns["insights"].append(
                f"You've had {negative_tones} negative dreams recently. "
                f"This often correlates with stress or poor sleep."
            )
        recurring = [s for s in set(all_symbols) if all_symbols.count(s) >= 2]
        if recurring:
            patterns["insights"].append(
                f"Recurring dream symbols: {', '.join(recurring[:3])}. "
                f"These patterns may reflect your current emotional state."
            )

    # Habit streaks
    for habit in load_habits():
        name = habit.get("name", "")
        streak = habit.get("streak", 0)
        if streak >= 7:
            patterns["insights"].append(
                f"'{name}' is at {streak} days - this is becoming a real part of your identity."
            )
        elif streak == 0 and habit.get("last_done"):
            patterns["insights"].append(
                f"'{name}' streak is at zero. Easy to restart - just one day."
            )

    return patterns

