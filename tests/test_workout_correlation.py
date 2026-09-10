"""Tests for demo/workout_correlation.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def workout_correlation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "workout_correlation"):
        if mod in sys.modules:
            del sys.modules[mod]
    import workout_correlation as wc
    importlib.reload(wc)
    import storage
    storage.set_active_profile(None)
    return wc


def _ts(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestComputeWorkoutMoodImpact:
    def test_no_data_returns_none_diff(self, workout_correlation):
        result = workout_correlation.compute_workout_mood_impact(90)
        assert result["mood_diff"] is None

    def test_with_vs_without_averages(self, workout_correlation):
        import storage
        storage.save_fitness([{"date": _date(1), "type": "run", "duration": 30}])
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 4, "timestamp": _ts(2)})
        result = workout_correlation.compute_workout_mood_impact(90)
        assert result["avg_mood_with_workout"] == 9.0
        assert result["avg_mood_without_workout"] == 4.0
        assert result["mood_diff"] == 5.0

    def test_day_without_mood_entry_excluded(self, workout_correlation):
        import storage
        storage.save_fitness([{"date": _date(1), "type": "run", "duration": 30}])
        result = workout_correlation.compute_workout_mood_impact(90)
        assert result["days_with_workout"] == 0


class TestFormatWorkoutMoodImpact:
    def test_no_data_message(self, workout_correlation):
        result = {"days": 90, "days_with_workout": 0, "days_without_workout": 0,
                  "avg_mood_with_workout": None, "avg_mood_without_workout": None, "mood_diff": None}
        text = workout_correlation.format_workout_mood_impact(result)
        assert "Not enough overlapping" in text

    def test_higher_direction(self, workout_correlation):
        result = {"days": 90, "days_with_workout": 2, "days_without_workout": 2,
                  "avg_mood_with_workout": 9.0, "avg_mood_without_workout": 4.0, "mood_diff": 5.0}
        text = workout_correlation.format_workout_mood_impact(result)
        assert "higher on workout days" in text

    def test_lower_direction(self, workout_correlation):
        result = {"days": 90, "days_with_workout": 2, "days_without_workout": 2,
                  "avg_mood_with_workout": 3.0, "avg_mood_without_workout": 8.0, "mood_diff": -5.0}
        text = workout_correlation.format_workout_mood_impact(result)
        assert "lower on workout days" in text
