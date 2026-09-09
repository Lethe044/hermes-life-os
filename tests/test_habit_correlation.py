"""Tests for demo/habit_correlation.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def habit_correlation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "habit_correlation"):
        if mod in sys.modules:
            del sys.modules[mod]
    import habit_correlation as hcorr
    importlib.reload(hcorr)
    import storage
    storage.set_active_profile(None)
    return hcorr


def _ts(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestComputeHabitMoodImpact:
    def test_no_data_returns_none_diff(self, habit_correlation):
        result = habit_correlation.compute_habit_mood_impact("meditate", 90)
        assert result["mood_diff"] is None

    def test_habit_without_matching_mood_excluded(self, habit_correlation):
        import storage
        storage.write_memory({"type": "habit_completion", "habit": "meditate",
                               "completed": True, "timestamp": _ts(1)})
        result = habit_correlation.compute_habit_mood_impact("meditate", 90)
        assert result["days_completed"] == 0
        assert result["mood_diff"] is None

    def test_completed_vs_missed_averages(self, habit_correlation):
        import storage
        storage.write_memory({"type": "habit_completion", "habit": "meditate",
                               "completed": True, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "habit_completion", "habit": "meditate",
                               "completed": False, "timestamp": _ts(2)})
        storage.write_memory({"type": "mood", "score": 3, "timestamp": _ts(2)})
        result = habit_correlation.compute_habit_mood_impact("meditate", 90)
        assert result["avg_mood_completed"] == 9.0
        assert result["avg_mood_missed"] == 3.0
        assert result["mood_diff"] == 6.0

    def test_habit_name_matching_case_insensitive(self, habit_correlation):
        import storage
        storage.write_memory({"type": "habit_completion", "habit": "Meditate",
                               "completed": True, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 8, "timestamp": _ts(1)})
        result = habit_correlation.compute_habit_mood_impact("meditate", 90)
        assert result["days_completed"] == 1

    def test_different_habit_not_mixed_in(self, habit_correlation):
        import storage
        storage.write_memory({"type": "habit_completion", "habit": "reading",
                               "completed": True, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 8, "timestamp": _ts(1)})
        result = habit_correlation.compute_habit_mood_impact("meditate", 90)
        assert result["days_completed"] == 0

    def test_multiple_mood_entries_same_day_averaged(self, habit_correlation):
        import storage
        storage.write_memory({"type": "habit_completion", "habit": "meditate",
                               "completed": True, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 10, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 6, "timestamp": _ts(1)})
        result = habit_correlation.compute_habit_mood_impact("meditate", 90)
        assert result["avg_mood_completed"] == 8.0


class TestFormatHabitMoodImpact:
    def test_no_data_message(self, habit_correlation):
        result = {"habit_name": "meditate", "days": 90, "days_completed": 0, "days_missed": 0,
                  "avg_mood_completed": None, "avg_mood_missed": None, "mood_diff": None}
        text = habit_correlation.format_habit_mood_impact(result)
        assert "Not enough overlapping" in text

    def test_positive_diff_shows_higher(self, habit_correlation):
        result = {"habit_name": "meditate", "days": 90, "days_completed": 3, "days_missed": 2,
                  "avg_mood_completed": 9.0, "avg_mood_missed": 3.0, "mood_diff": 6.0}
        text = habit_correlation.format_habit_mood_impact(result)
        assert "higher on completed days" in text

    def test_negative_diff_shows_lower(self, habit_correlation):
        result = {"habit_name": "meditate", "days": 90, "days_completed": 3, "days_missed": 2,
                  "avg_mood_completed": 3.0, "avg_mood_missed": 9.0, "mood_diff": -6.0}
        text = habit_correlation.format_habit_mood_impact(result)
        assert "lower on completed days" in text
