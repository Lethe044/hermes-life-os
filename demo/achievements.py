"""
Hermes Life OS - Achievements
=================================
Badges for logging streaks and milestones - a lightweight gamification
layer on top of data that's already being tracked. Nothing here writes
new data; evaluate_achievements() is a read-only analysis over
habits.json and memory.jsonl, recomputed fresh every call - so there's
no separate "achievements state" that can drift out of sync with the
underlying logs. Edit or delete a memory entry and badge progress
reflects that immediately, the next time it's checked.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from storage import load_habits, get_all_memory

STREAK_MILESTONES = [7, 30, 100]

# (memory entry "type", badge name, description, icon, target count)
COUNT_BADGES = [
    ("workout", "Getting Active", "Log your first workout.", "\U0001F3CB", 1),
    ("workout", "Fitness Regular", "Log 50 workouts.", "\U0001F4AA", 50),
    ("meditation", "First Breath", "Log your first meditation session.", "\U0001F9D8", 1),
    ("meditation", "Mindful", "Log 30 meditation sessions.", "\U0001F9D8", 30),
    ("mood", "Checking In", "Log your first mood check-in.", "\U0001F642", 1),
    ("mood", "Self-Aware", "Log 50 mood check-ins.", "\U0001F642", 50),
    ("gratitude", "Grateful", "Log 10 gratitude entries.", "\U0001F64F", 10),
    ("social", "Connected", "Log 10 social interactions.", "\U0001F91D", 10),
    ("dream", "Dream Journal", "Log 10 dreams.", "\U0001F4AD", 10),
    ("focus", "Deep Worker", "Log 25 focus sessions.", "\U0001F3AF", 25),
]


def consecutive_day_streak(dates: List[str]) -> int:
    """Longest streak of consecutive calendar days ending today (or
    yesterday - a one-day grace period so a streak doesn't reset to 0
    just because today hasn't happened yet) from a list of YYYY-MM-DD
    date strings."""
    if not dates:
        return 0
    date_set = set(dates)
    today = datetime.utcnow().date()
    anchor = today if today.strftime("%Y-%m-%d") in date_set else today - timedelta(days=1)
    if anchor.strftime("%Y-%m-%d") not in date_set:
        return 0
    streak = 0
    cursor = anchor
    while cursor.strftime("%Y-%m-%d") in date_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _entry_type_counts(entries: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for e in entries:
        t = e.get("type", "")
        counts[t] = counts.get(t, 0) + 1
    return counts


# Backward-compatible alias - this was originally a private (leading
# underscore) helper before heatmap.py started reusing it too.
_consecutive_day_streak = consecutive_day_streak


def _badge(id_: str, name: str, description: str, icon: str,
           current: float, target: float) -> Dict:
    earned = current >= target
    progress_pct = 100.0 if target <= 0 else min(100.0, (current / target) * 100)
    return {
        "id": id_,
        "name": name,
        "description": description,
        "icon": icon,
        "earned": earned,
        "progress": min(current, target),
        "target": target,
        "progress_pct": progress_pct,
    }


def evaluate_achievements() -> List[Dict]:
    """Every streak-milestone and count-based badge, earned or not.
    Each item: id, name, description, icon, earned (bool), progress
    (current value, capped at target), target, progress_pct (0-100).
    Order: per-habit streaks, then the overall logging streak, then
    count-based milestone badges."""
    results: List[Dict] = []

    for habit in load_habits():
        best = habit.get("best_streak", habit.get("streak", 0))
        habit_name = habit.get("name", "habit")
        for milestone in STREAK_MILESTONES:
            results.append(_badge(
                f"habit-streak-{habit_name}-{milestone}",
                f"{habit_name.title()}: {milestone}-Day Streak",
                f"Keep '{habit_name}' going for {milestone} days in a row.",
                "\U0001F525", best, milestone,
            ))

    entries = get_all_memory()
    dates = [e.get("timestamp", "")[:10] for e in entries if e.get("timestamp")]
    current_streak = consecutive_day_streak(dates)
    for milestone in STREAK_MILESTONES:
        results.append(_badge(
            f"logging-streak-{milestone}",
            f"{milestone}-Day Logging Streak",
            f"Log something every day for {milestone} days in a row.",
            "\U0001F4C6", current_streak, milestone,
        ))

    counts = _entry_type_counts(entries)
    for entry_type, name, description, icon, target in COUNT_BADGES:
        results.append(_badge(
            f"count-{entry_type}-{target}", name, description, icon,
            counts.get(entry_type, 0), target,
        ))

    return results
