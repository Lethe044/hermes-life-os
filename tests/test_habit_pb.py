"""Tests for demo/habit_pb.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def habit_pb(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "habit_pb"):
        if mod in sys.modules:
            del sys.modules[mod]
    import habit_pb as hp
    importlib.reload(hp)
    import storage
    storage.set_active_profile(None)
    return hp


class TestComputeHabitPbProgress:
    def test_no_habits_returns_empty(self, habit_pb):
        assert habit_pb.compute_habit_pb_progress() == []

    def test_habit_with_zero_streak_and_zero_best_excluded(self, habit_pb):
        import storage
        storage.save_habits([{"name": "New habit", "streak": 0, "best_streak": 0}])
        assert habit_pb.compute_habit_pb_progress() == []

    def test_current_streak_below_best_is_chasing(self, habit_pb):
        import storage
        storage.save_habits([{"name": "Meditate", "streak": 3, "best_streak": 10}])
        result = habit_pb.compute_habit_pb_progress()
        assert result[0]["status"] == "chasing_best"
        assert result[0]["days_to_tie"] == 7

    def test_current_streak_equal_to_best_is_tied(self, habit_pb):
        import storage
        storage.save_habits([{"name": "Meditate", "streak": 10, "best_streak": 10}])
        result = habit_pb.compute_habit_pb_progress()
        assert result[0]["status"] == "tied_best"
        assert result[0]["days_to_tie"] == 0

    def test_current_streak_above_best_is_new_best(self, habit_pb):
        import storage
        storage.save_habits([{"name": "Meditate", "streak": 12, "best_streak": 10}])
        result = habit_pb.compute_habit_pb_progress()
        assert result[0]["status"] == "new_best"
        assert result[0]["days_to_tie"] == 0

    def test_new_best_and_tied_sort_before_chasing(self, habit_pb):
        import storage
        storage.save_habits([
            {"name": "Chasing", "streak": 2, "best_streak": 10},
            {"name": "AtBest", "streak": 10, "best_streak": 10},
        ])
        result = habit_pb.compute_habit_pb_progress()
        assert result[0]["name"] == "AtBest"
        assert result[1]["name"] == "Chasing"

    def test_closer_chasing_habits_sort_first(self, habit_pb):
        import storage
        storage.save_habits([
            {"name": "Far", "streak": 1, "best_streak": 10},
            {"name": "Near", "streak": 8, "best_streak": 10},
        ])
        result = habit_pb.compute_habit_pb_progress()
        assert [r["name"] for r in result] == ["Near", "Far"]


class TestFormatHabitPbProgress:
    def test_empty_list_message(self, habit_pb):
        assert "No habit history" in habit_pb.format_habit_pb_progress([])

    def test_new_best_message(self, habit_pb):
        results = [{"name": "Meditate", "streak": 12, "best_streak": 10,
                     "status": "new_best", "days_to_tie": 0}]
        text = habit_pb.format_habit_pb_progress(results)
        assert "new personal best" in text

    def test_tied_best_message(self, habit_pb):
        results = [{"name": "Meditate", "streak": 10, "best_streak": 10,
                     "status": "tied_best", "days_to_tie": 0}]
        text = habit_pb.format_habit_pb_progress(results)
        assert "tied your personal best" in text

    def test_chasing_singular_day(self, habit_pb):
        results = [{"name": "Meditate", "streak": 9, "best_streak": 10,
                     "status": "chasing_best", "days_to_tie": 1}]
        text = habit_pb.format_habit_pb_progress(results)
        assert "1 day from tying your best of 10" in text

    def test_chasing_plural_days(self, habit_pb):
        results = [{"name": "Meditate", "streak": 5, "best_streak": 10,
                     "status": "chasing_best", "days_to_tie": 5}]
        text = habit_pb.format_habit_pb_progress(results)
        assert "5 days from tying your best of 10" in text
