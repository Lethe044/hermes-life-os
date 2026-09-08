"""Tests for demo/hydration_summary.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def hydration_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "hydration_summary"):
        if mod in sys.modules:
            del sys.modules[mod]
    import hydration_summary as hs
    importlib.reload(hs)
    import storage
    storage.set_active_profile(None)
    return hs


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeHydrationSummary:
    def test_no_log_returns_zeroed_result(self, hydration_summary):
        result = hydration_summary.compute_hydration_summary(30)
        assert result["days_logged"] == 0
        assert result["current_goal_streak"] == 0

    def test_average_and_goal_met_count(self, hydration_summary):
        import storage
        storage.save_hydration({
            "today": 0, "goal": 8,
            "log": [
                {"date": _days_ago(1), "glasses": 8},
                {"date": _days_ago(2), "glasses": 4},
            ],
        })
        result = hydration_summary.compute_hydration_summary(30)
        assert result["days_logged"] == 2
        assert result["avg_glasses_per_day"] == 6.0
        assert result["days_goal_met"] == 1
        assert result["goal_met_pct"] == 50.0

    def test_multiple_entries_same_day_summed(self, hydration_summary):
        import storage
        storage.save_hydration({
            "today": 0, "goal": 8,
            "log": [
                {"date": _days_ago(1), "glasses": 4},
                {"date": _days_ago(1), "glasses": 4},
            ],
        })
        result = hydration_summary.compute_hydration_summary(30)
        assert result["days_goal_met"] == 1

    def test_current_streak_consecutive_days_meeting_goal(self, hydration_summary):
        import storage
        storage.save_hydration({
            "today": 0, "goal": 8,
            "log": [
                {"date": _days_ago(0), "glasses": 8},
                {"date": _days_ago(1), "glasses": 8},
                {"date": _days_ago(2), "glasses": 3},
            ],
        })
        result = hydration_summary.compute_hydration_summary(30)
        assert result["current_goal_streak"] == 2

    def test_outside_window_excluded_from_averages(self, hydration_summary):
        import storage
        storage.save_hydration({
            "today": 0, "goal": 8,
            "log": [{"date": _days_ago(100), "glasses": 8}],
        })
        result = hydration_summary.compute_hydration_summary(30)
        assert result["days_logged"] == 0

    def test_custom_goal_used(self, hydration_summary):
        import storage
        storage.save_hydration({
            "today": 0, "goal": 10,
            "log": [{"date": _days_ago(1), "glasses": 8}],
        })
        result = hydration_summary.compute_hydration_summary(30)
        assert result["days_goal_met"] == 0


class TestFormatHydrationSummary:
    def test_no_log_message(self, hydration_summary):
        result = {"days": 30, "goal": 8, "days_logged": 0, "avg_glasses_per_day": 0.0,
                  "days_goal_met": 0, "goal_met_pct": 0.0, "current_goal_streak": 0}
        text = hydration_summary.format_hydration_summary(result)
        assert "No hydration logged" in text

    def test_with_data_shows_average_and_streak(self, hydration_summary):
        result = {"days": 30, "goal": 8, "days_logged": 10, "avg_glasses_per_day": 7.5,
                  "days_goal_met": 6, "goal_met_pct": 60.0, "current_goal_streak": 3}
        text = hydration_summary.format_hydration_summary(result)
        assert "7.5 glasses/day" in text
        assert "6/10 logged days" in text
        assert "streak: 3 day(s)" in text

    def test_zero_streak_omits_streak_line(self, hydration_summary):
        result = {"days": 30, "goal": 8, "days_logged": 5, "avg_glasses_per_day": 3.0,
                  "days_goal_met": 0, "goal_met_pct": 0.0, "current_goal_streak": 0}
        text = hydration_summary.format_hydration_summary(result)
        assert "streak" not in text
