"""Tests for demo/habit_overview.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def habit_overview(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "habit_milestones", "habit_pb", "habit_consistency", "habit_overview"):
        if mod in sys.modules:
            del sys.modules[mod]
    import habit_overview as ho
    importlib.reload(ho)
    import storage
    storage.set_active_profile(None)
    return ho


class TestComputeHabitOverview:
    def test_no_data_returns_empty_sections(self, habit_overview):
        result = habit_overview.compute_habit_overview(90)
        assert result["milestones"] == []
        assert result["personal_bests"] == []
        assert result["consistency"] == []

    def test_with_habit_data_populates_milestones_and_pbs(self, habit_overview):
        import storage
        storage.save_habits([{"name": "meditate", "streak": 5, "best_streak": 5}])
        result = habit_overview.compute_habit_overview(90)
        assert len(result["milestones"]) == 1
        assert len(result["personal_bests"]) == 1

    def test_days_param_passed_to_consistency(self, habit_overview):
        import storage
        storage.write_memory({"type": "habit_completion", "habit": "meditate", "completed": True})
        result = habit_overview.compute_habit_overview(90)
        assert len(result["consistency"]) == 1


class TestFormatHabitOverview:
    def test_all_empty_sections_message(self, habit_overview):
        result = {"milestones": [], "personal_bests": [], "consistency": []}
        text = habit_overview.format_habit_overview(result)
        assert "No habit data yet" in text

    def test_combines_available_sections(self, habit_overview):
        import storage
        storage.save_habits([{"name": "meditate", "streak": 5, "best_streak": 5}])
        result = habit_overview.compute_habit_overview(90)
        text = habit_overview.format_habit_overview(result)
        assert "milestone" in text
        assert "personal best" in text

    def test_missing_section_omitted(self, habit_overview):
        from habit_milestones import compute_habit_milestones
        from habit_pb import compute_habit_pb_progress
        result = {"milestones": compute_habit_milestones(),
                  "personal_bests": compute_habit_pb_progress(), "consistency": []}
        text = habit_overview.format_habit_overview(result)
        # No habits at all, so milestones/personal_bests are also empty here;
        # this asserts the function doesn't crash and still returns the
        # "no data" message when every section is empty.
        assert "No habit data yet" in text
