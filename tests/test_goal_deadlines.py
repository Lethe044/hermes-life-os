"""Tests for demo/goal_deadlines.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def goal_deadlines(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "goal_deadlines"):
        if mod in sys.modules:
            del sys.modules[mod]
    import goal_deadlines as gd
    importlib.reload(gd)
    import storage
    storage.set_active_profile(None)
    return gd


class TestComputeGoalDeadlines:
    def test_no_goals_returns_empty(self, goal_deadlines):
        assert goal_deadlines.compute_goal_deadlines() == []

    def test_goal_without_deadline_excluded(self, goal_deadlines):
        import storage
        storage.save_goals([{"name": "Read more", "progress": 20}])
        assert goal_deadlines.compute_goal_deadlines() == []

    def test_goal_with_invalid_deadline_excluded(self, goal_deadlines):
        import storage
        storage.save_goals([{"name": "Bad date", "progress": 0, "deadline": "not-a-date"}])
        assert goal_deadlines.compute_goal_deadlines() == []

    def test_future_deadline_days_remaining(self, goal_deadlines):
        import storage
        storage.save_goals([{"name": "Marathon", "progress": 50, "deadline": "2025-06-10"}])
        result = goal_deadlines.compute_goal_deadlines(today="2025-06-01")
        assert len(result) == 1
        assert result[0]["days_remaining"] == 9
        assert result[0]["overdue"] is False

    def test_overdue_deadline_flagged(self, goal_deadlines):
        import storage
        storage.save_goals([{"name": "Taxes", "progress": 10, "deadline": "2025-04-01"}])
        result = goal_deadlines.compute_goal_deadlines(today="2025-04-15")
        assert result[0]["overdue"] is True
        assert result[0]["days_remaining"] == -14

    def test_due_today(self, goal_deadlines):
        import storage
        storage.save_goals([{"name": "Deadline day", "progress": 90, "deadline": "2025-05-01"}])
        result = goal_deadlines.compute_goal_deadlines(today="2025-05-01")
        assert result[0]["days_remaining"] == 0
        assert result[0]["overdue"] is False

    def test_sorted_most_urgent_first(self, goal_deadlines):
        import storage
        storage.save_goals([
            {"name": "Later", "progress": 0, "deadline": "2025-12-01"},
            {"name": "Overdue", "progress": 0, "deadline": "2025-01-01"},
            {"name": "Soon", "progress": 0, "deadline": "2025-06-05"},
        ])
        result = goal_deadlines.compute_goal_deadlines(today="2025-06-01")
        assert [r["name"] for r in result] == ["Overdue", "Soon", "Later"]


class TestFormatGoalDeadlines:
    def test_empty_list_message(self, goal_deadlines):
        result = goal_deadlines.format_goal_deadlines([])
        assert "No goals have a deadline" in result

    def test_overdue_message(self, goal_deadlines):
        results = [{"name": "Taxes", "progress": 10, "deadline": "2025-04-01",
                     "days_remaining": -14, "overdue": True}]
        text = goal_deadlines.format_goal_deadlines(results)
        assert "overdue by 14 day(s)" in text

    def test_due_today_message(self, goal_deadlines):
        results = [{"name": "Deadline day", "progress": 90, "deadline": "2025-05-01",
                     "days_remaining": 0, "overdue": False}]
        text = goal_deadlines.format_goal_deadlines(results)
        assert "due today!" in text

    def test_future_message(self, goal_deadlines):
        results = [{"name": "Marathon", "progress": 50, "deadline": "2025-06-10",
                     "days_remaining": 9, "overdue": False}]
        text = goal_deadlines.format_goal_deadlines(results)
        assert "9 day(s) left" in text
