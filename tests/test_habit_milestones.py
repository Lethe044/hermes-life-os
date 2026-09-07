"""Tests for demo/habit_milestones.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def habit_milestones(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "habit_milestones"):
        if mod in sys.modules:
            del sys.modules[mod]
    import habit_milestones as hm
    importlib.reload(hm)
    import storage
    storage.set_active_profile(None)
    return hm


class TestNextMilestone:
    def test_below_first_milestone(self, habit_milestones):
        assert habit_milestones._next_milestone(3) == 7

    def test_exactly_at_a_milestone_targets_next_one(self, habit_milestones):
        assert habit_milestones._next_milestone(7) == 14

    def test_between_milestones(self, habit_milestones):
        assert habit_milestones._next_milestone(40) == 50

    def test_past_largest_predefined_milestone_doubles(self, habit_milestones):
        assert habit_milestones._next_milestone(1000) == 2000
        assert habit_milestones._next_milestone(1500) == 2000
        assert habit_milestones._next_milestone(2500) == 4000


class TestComputeHabitMilestones:
    def test_no_habits_returns_empty(self, habit_milestones):
        assert habit_milestones.compute_habit_milestones() == []

    def test_zero_streak_habit_excluded(self, habit_milestones):
        import storage
        storage.save_habits([{"name": "Meditate", "streak": 0, "best_streak": 5}])
        assert habit_milestones.compute_habit_milestones() == []

    def test_active_streak_habit_included(self, habit_milestones):
        import storage
        storage.save_habits([{"name": "Meditate", "streak": 5, "best_streak": 5}])
        result = habit_milestones.compute_habit_milestones()
        assert len(result) == 1
        assert result[0]["name"] == "Meditate"
        assert result[0]["next_milestone"] == 7
        assert result[0]["days_remaining"] == 2

    def test_sorted_by_days_remaining_ascending(self, habit_milestones):
        import storage
        storage.save_habits([
            {"name": "Far", "streak": 1, "best_streak": 1},   # 6 days from 7
            {"name": "Near", "streak": 6, "best_streak": 6},  # 1 day from 7
        ])
        result = habit_milestones.compute_habit_milestones()
        assert [r["name"] for r in result] == ["Near", "Far"]

    def test_best_streak_defaults_to_streak_when_missing(self, habit_milestones):
        import storage
        storage.save_habits([{"name": "Read", "streak": 3}])
        result = habit_milestones.compute_habit_milestones()
        assert result[0]["best_streak"] == 3


class TestFormatHabitMilestones:
    def test_empty_list_message(self, habit_milestones):
        result = habit_milestones.format_habit_milestones([])
        assert "No active habit streaks" in result

    def test_singular_day_phrasing(self, habit_milestones):
        results = [{"name": "Meditate", "streak": 6, "best_streak": 6,
                     "next_milestone": 7, "days_remaining": 1}]
        text = habit_milestones.format_habit_milestones(results)
        assert "1 day from a 7-day milestone!" in text

    def test_plural_day_phrasing(self, habit_milestones):
        results = [{"name": "Meditate", "streak": 3, "best_streak": 3,
                     "next_milestone": 7, "days_remaining": 4}]
        text = habit_milestones.format_habit_milestones(results)
        assert "4 days from a 7-day milestone" in text
