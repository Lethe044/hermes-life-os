"""Tests for demo/habit_consistency.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def habit_consistency(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "habit_consistency"):
        if mod in sys.modules:
            del sys.modules[mod]
    import habit_consistency as hc
    importlib.reload(hc)
    import storage
    storage.set_active_profile(None)
    return hc


def _write_checkin(storage, habit: str, completed: bool, days_ago: int = 1):
    dt = datetime.utcnow() - timedelta(days=days_ago)
    storage.write_memory({
        "type": "habit_completion", "content": habit, "habit": habit,
        "completed": completed, "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


class TestComputeHabitConsistency:
    def test_no_checkins_returns_empty(self, habit_consistency):
        assert habit_consistency.compute_habit_consistency(90) == []

    def test_single_habit_all_completed(self, habit_consistency):
        import storage
        _write_checkin(storage, "meditate", True, 1)
        _write_checkin(storage, "meditate", True, 2)
        result = habit_consistency.compute_habit_consistency(90)
        assert result[0]["consistency_pct"] == 100.0
        assert result[0]["total_checkins"] == 2

    def test_mixed_completion(self, habit_consistency):
        import storage
        _write_checkin(storage, "meditate", True, 1)
        _write_checkin(storage, "meditate", False, 2)
        result = habit_consistency.compute_habit_consistency(90)
        assert result[0]["consistency_pct"] == 50.0

    def test_multiple_habits_sorted_by_consistency(self, habit_consistency):
        import storage
        _write_checkin(storage, "great_habit", True, 1)
        _write_checkin(storage, "bad_habit", False, 1)
        result = habit_consistency.compute_habit_consistency(90)
        assert result[0]["name"] == "great_habit"
        assert result[1]["name"] == "bad_habit"

    def test_non_habit_completion_entries_excluded(self, habit_consistency):
        import storage
        storage.write_memory({"type": "mood", "content": "ok", "score": 5})
        result = habit_consistency.compute_habit_consistency(90)
        assert result == []

    def test_outside_window_excluded(self, habit_consistency):
        import storage
        _write_checkin(storage, "meditate", True, 200)
        result = habit_consistency.compute_habit_consistency(90)
        assert result == []


class TestFormatHabitConsistency:
    def test_empty_list_message(self, habit_consistency):
        text = habit_consistency.format_habit_consistency([])
        assert "No habit check-ins recorded" in text

    def test_with_data_shows_percentage(self, habit_consistency):
        results = [{"name": "meditate", "total_checkins": 4, "completed_checkins": 3,
                     "consistency_pct": 75.0}]
        text = habit_consistency.format_habit_consistency(results)
        assert "meditate: 75.0% (3/4 check-ins)" in text
