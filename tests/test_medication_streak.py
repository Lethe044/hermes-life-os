"""Tests for demo/medication_streak.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def medication_streak(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "medication_streak"):
        if mod in sys.modules:
            del sys.modules[mod]
    import medication_streak as ms
    importlib.reload(ms)
    import storage
    storage.set_active_profile(None)
    return ms


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeMedicationStreak:
    def test_no_logs_returns_zeroed_result(self, medication_streak):
        result = medication_streak.compute_medication_streak("Vitamin D")
        assert result["total_logs"] == 0
        assert result["current_streak"] == 0

    def test_name_matching_case_insensitive(self, medication_streak):
        import storage
        storage.save_medication([{"date": _days_ago(0), "name": "Vitamin D", "taken": True}])
        result = medication_streak.compute_medication_streak("vitamin d")
        assert result["total_logs"] == 1

    def test_current_streak_consecutive_taken_days(self, medication_streak):
        import storage
        storage.save_medication([
            {"date": _days_ago(0), "name": "Vitamin D", "taken": True},
            {"date": _days_ago(1), "name": "Vitamin D", "taken": True},
            {"date": _days_ago(2), "name": "Vitamin D", "taken": True},
        ])
        result = medication_streak.compute_medication_streak("Vitamin D")
        assert result["current_streak"] == 3

    def test_current_streak_broken_by_missed_dose(self, medication_streak):
        import storage
        storage.save_medication([
            {"date": _days_ago(0), "name": "Vitamin D", "taken": True},
            {"date": _days_ago(1), "name": "Vitamin D", "taken": False},
            {"date": _days_ago(2), "name": "Vitamin D", "taken": True},
        ])
        result = medication_streak.compute_medication_streak("Vitamin D")
        assert result["current_streak"] == 1

    def test_current_streak_broken_by_missing_day(self, medication_streak):
        import storage
        storage.save_medication([
            {"date": _days_ago(0), "name": "Vitamin D", "taken": True},
            {"date": _days_ago(2), "name": "Vitamin D", "taken": True},
        ])
        result = medication_streak.compute_medication_streak("Vitamin D")
        assert result["current_streak"] == 1

    def test_longest_streak_tracks_past_run(self, medication_streak):
        import storage
        storage.save_medication([
            {"date": _days_ago(d), "name": "Vitamin D", "taken": True} for d in range(10, 15)
        ] + [{"date": _days_ago(0), "name": "Vitamin D", "taken": True}])
        result = medication_streak.compute_medication_streak("Vitamin D")
        assert result["longest_streak"] == 5
        assert result["current_streak"] == 1

    def test_different_medication_not_mixed_in(self, medication_streak):
        import storage
        storage.save_medication([{"date": _days_ago(0), "name": "Iron", "taken": True}])
        result = medication_streak.compute_medication_streak("Vitamin D")
        assert result["total_logs"] == 0


class TestFormatMedicationStreak:
    def test_no_logs_message(self, medication_streak):
        result = {"med_name": "Vitamin D", "total_logs": 0, "current_streak": 0, "longest_streak": 0}
        text = medication_streak.format_medication_streak(result)
        assert "No logs found" in text

    def test_with_data_shows_streaks(self, medication_streak):
        result = {"med_name": "Vitamin D", "total_logs": 5, "current_streak": 3, "longest_streak": 5}
        text = medication_streak.format_medication_streak(result)
        assert "current streak 3 day(s)" in text
        assert "longest streak 5 day(s)" in text
