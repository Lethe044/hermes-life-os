"""Tests for demo/workout_summary.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def workout_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "workout_summary"):
        if mod in sys.modules:
            del sys.modules[mod]
    import workout_summary as ws
    importlib.reload(ws)
    import storage
    storage.set_active_profile(None)
    return ws


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeWorkoutSummary:
    def test_no_workouts_returns_zeroed_result(self, workout_summary):
        result = workout_summary.compute_workout_summary(30)
        assert result["total_workouts"] == 0
        assert result["current_streak"] == 0
        assert result["most_common_type"] is None

    def test_totals_and_average(self, workout_summary):
        import storage
        storage.save_fitness([
            {"date": _days_ago(1), "type": "run", "duration": 30},
            {"date": _days_ago(2), "type": "run", "duration": 20},
        ])
        result = workout_summary.compute_workout_summary(30)
        assert result["total_workouts"] == 2
        assert result["total_minutes"] == 50
        assert result["avg_duration"] == 25.0

    def test_by_type_breakdown_and_most_common(self, workout_summary):
        import storage
        storage.save_fitness([
            {"date": _days_ago(1), "type": "run", "duration": 30},
            {"date": _days_ago(2), "type": "run", "duration": 30},
            {"date": _days_ago(3), "type": "yoga", "duration": 45},
        ])
        result = workout_summary.compute_workout_summary(30)
        assert result["by_type"] == {"run": 2, "yoga": 1}
        assert result["most_common_type"] == "run"

    def test_workouts_outside_window_excluded_from_totals(self, workout_summary):
        import storage
        storage.save_fitness([{"date": _days_ago(100), "type": "run", "duration": 30}])
        result = workout_summary.compute_workout_summary(30)
        assert result["total_workouts"] == 0

    def test_current_streak_consecutive_days(self, workout_summary):
        import storage
        storage.save_fitness([
            {"date": _days_ago(0), "type": "run", "duration": 30},
            {"date": _days_ago(1), "type": "run", "duration": 30},
            {"date": _days_ago(2), "type": "run", "duration": 30},
        ])
        result = workout_summary.compute_workout_summary(30)
        assert result["current_streak"] == 3

    def test_current_streak_broken_by_gap(self, workout_summary):
        import storage
        storage.save_fitness([
            {"date": _days_ago(0), "type": "run", "duration": 30},
            {"date": _days_ago(2), "type": "run", "duration": 30},
        ])
        result = workout_summary.compute_workout_summary(30)
        assert result["current_streak"] == 1

    def test_current_streak_uses_full_history_not_just_window(self, workout_summary):
        import storage
        # Streak started before the 30-day window but is still ongoing.
        storage.save_fitness([
            {"date": _days_ago(d), "type": "run", "duration": 20} for d in range(0, 35)
        ])
        result = workout_summary.compute_workout_summary(30)
        assert result["current_streak"] == 35


class TestFormatWorkoutSummary:
    def test_no_workouts_message(self, workout_summary):
        result = {"days": 30, "total_workouts": 0, "total_minutes": 0,
                  "avg_duration": 0.0, "by_type": {}, "most_common_type": None,
                  "current_streak": 0}
        text = workout_summary.format_workout_summary(result)
        assert "No workouts logged" in text

    def test_with_data_shows_totals_and_type(self, workout_summary):
        result = {"days": 30, "total_workouts": 3, "total_minutes": 90,
                  "avg_duration": 30.0, "by_type": {"run": 2, "yoga": 1},
                  "most_common_type": "run", "current_streak": 2}
        text = workout_summary.format_workout_summary(result)
        assert "3 workout(s)" in text
        assert "run: 2" in text
        assert "streak: 2 day(s)" in text

    def test_zero_streak_omits_streak_line(self, workout_summary):
        result = {"days": 30, "total_workouts": 1, "total_minutes": 30,
                  "avg_duration": 30.0, "by_type": {"run": 1},
                  "most_common_type": "run", "current_streak": 0}
        text = workout_summary.format_workout_summary(result)
        assert "streak" not in text
