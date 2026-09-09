"""
Hermes Life OS - Habit Overview
===================================
A single combined dashboard over the existing habit-analytics modules
(habit_milestones.py, habit_pb.py, habit_consistency.py) - one call
instead of three when the user just wants "how are my habits doing"
rather than one specific angle. Pure composition, no new tracking or
storage of its own, no network call.
"""

from __future__ import annotations

from typing import Any, Dict

from habit_consistency import compute_habit_consistency
from habit_milestones import compute_habit_milestones
from habit_pb import compute_habit_pb_progress


def compute_habit_overview(days: int = 90) -> Dict[str, Any]:
    """Returns {"milestones", "personal_bests", "consistency"} by
    calling each of the three underlying habit-analytics functions -
    see their own docstrings for what each list contains.
    """
    return {
        "milestones": compute_habit_milestones(),
        "personal_bests": compute_habit_pb_progress(),
        "consistency": compute_habit_consistency(days),
    }


def format_habit_overview(result: Dict[str, Any]) -> str:
    """Turns compute_habit_overview()'s output into one combined
    multi-section summary, reusing each module's own formatter so the
    per-metric wording stays consistent with calling that tool
    directly. Sections with nothing to show are omitted entirely.
    """
    from habit_consistency import format_habit_consistency
    from habit_milestones import format_habit_milestones
    from habit_pb import format_habit_pb_progress

    sections = []
    if result["milestones"]:
        sections.append(format_habit_milestones(result["milestones"]))
    if result["personal_bests"]:
        sections.append(format_habit_pb_progress(result["personal_bests"]))
    if result["consistency"]:
        sections.append(format_habit_consistency(result["consistency"]))

    if not sections:
        return "No habit data yet - update a habit to start building your overview."

    return "\n\n".join(sections)
