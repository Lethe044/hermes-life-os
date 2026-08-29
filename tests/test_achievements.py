"""Tests for demo/achievements.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def achievements(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "achievements"):
        if mod in sys.modules:
            del sys.modules[mod]
    import achievements as ach
    importlib.reload(ach)
    import storage
    storage.set_active_profile(None)
    return ach


def _date(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestConsecutiveDayStreak:
    def test_empty_returns_zero(self, achievements):
        assert achievements._consecutive_day_streak([]) == 0

    def test_single_day_today(self, achievements):
        assert achievements._consecutive_day_streak([_date(0)]) == 1

    def test_streak_of_three_ending_today(self, achievements):
        dates = [_date(0), _date(1), _date(2)]
        assert achievements._consecutive_day_streak(dates) == 3

    def test_grace_period_for_yesterday(self, achievements):
        # Logged yesterday and the day before, nothing today yet -
        # streak should still count (grace period), not reset to 0.
        dates = [_date(1), _date(2)]
        assert achievements._consecutive_day_streak(dates) == 2

    def test_gap_breaks_streak(self, achievements):
        dates = [_date(0), _date(1), _date(5)]  # gap between day 1 and day 5
        assert achievements._consecutive_day_streak(dates) == 2

    def test_nothing_recent_returns_zero(self, achievements):
        dates = [_date(10), _date(11)]
        assert achievements._consecutive_day_streak(dates) == 0

    def test_duplicate_dates_counted_once(self, achievements):
        dates = [_date(0), _date(0), _date(1)]
        assert achievements._consecutive_day_streak(dates) == 2


class TestEntryTypeCounts:
    def test_counts_by_type(self, achievements):
        entries = [{"type": "mood"}, {"type": "mood"}, {"type": "workout"}]
        counts = achievements._entry_type_counts(entries)
        assert counts == {"mood": 2, "workout": 1}

    def test_empty_entries(self, achievements):
        assert achievements._entry_type_counts([]) == {}


class TestBadgeHelper:
    def test_earned_when_current_meets_target(self, achievements):
        badge = achievements._badge("id", "Name", "desc", "icon", 10, 10)
        assert badge["earned"] is True
        assert badge["progress_pct"] == 100.0

    def test_not_earned_below_target(self, achievements):
        badge = achievements._badge("id", "Name", "desc", "icon", 5, 10)
        assert badge["earned"] is False
        assert badge["progress_pct"] == 50.0

    def test_progress_capped_at_target(self, achievements):
        badge = achievements._badge("id", "Name", "desc", "icon", 999, 10)
        assert badge["progress"] == 10
        assert badge["progress_pct"] == 100.0


class TestEvaluateAchievements:
    def test_no_data_returns_all_unearned(self, achievements):
        results = achievements.evaluate_achievements()
        assert len(results) > 0
        assert all(not r["earned"] for r in results)

    def test_first_workout_badge_earned(self, achievements):
        import storage
        storage.write_memory({"type": "workout", "content": "5k run"})
        results = achievements.evaluate_achievements()
        badge = next(r for r in results if r["id"] == "count-workout-1")
        assert badge["earned"] is True

    def test_habit_streak_badge_earned(self, achievements):
        import storage
        storage.save_habits([{"name": "meditate", "streak": 7, "best_streak": 7}])
        results = achievements.evaluate_achievements()
        badge = next(r for r in results if r["id"] == "habit-streak-meditate-7")
        assert badge["earned"] is True

    def test_habit_streak_badge_not_earned_below_milestone(self, achievements):
        import storage
        storage.save_habits([{"name": "meditate", "streak": 3, "best_streak": 3}])
        results = achievements.evaluate_achievements()
        badge = next(r for r in results if r["id"] == "habit-streak-meditate-7")
        assert badge["earned"] is False
        assert badge["progress"] == 3

    def test_logging_streak_badge(self, achievements):
        import storage
        for days_ago in range(7):
            storage.write_memory({"type": "mood", "content": "entry", "score": 5})
        results = achievements.evaluate_achievements()
        streak_badge = next(r for r in results if r["id"] == "logging-streak-7")
        # all writes happened "now" so this is a 1-day streak, not 7 -
        # just confirms the badge exists and reflects actual data, not
        # entry *count*.
        assert streak_badge["progress"] == 1

    def test_multiple_habits_each_get_their_own_badges(self, achievements):
        import storage
        storage.save_habits([
            {"name": "run", "streak": 10, "best_streak": 10},
            {"name": "read", "streak": 2, "best_streak": 2},
        ])
        results = achievements.evaluate_achievements()
        ids = {r["id"] for r in results}
        assert "habit-streak-run-7" in ids
        assert "habit-streak-read-7" in ids
