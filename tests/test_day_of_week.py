"""Tests for demo/day_of_week.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def day_of_week(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "day_of_week"):
        if mod in sys.modules:
            del sys.modules[mod]
    import day_of_week as dow
    importlib.reload(dow)
    import storage
    storage.set_active_profile(None)
    return dow


def _write_mood_on_weekday(storage, weekday_target: int, days_ago_start: int, value: float):
    """Writes a mood memory entry stamped with a timestamp that falls on
    the given weekday (0=Monday), searching backward from days_ago_start
    up to 7 days to find a matching date."""
    for offset in range(days_ago_start, days_ago_start + 7):
        dt = datetime.utcnow() - timedelta(days=offset)
        if dt.weekday() == weekday_target:
            storage.write_memory({
                "type": "mood", "content": "feeling", "score": value,
                "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            return
    raise AssertionError("could not find a matching weekday in range")


class TestComputeDayOfWeekPatterns:
    def test_no_data_returns_empty_metrics(self, day_of_week):
        result = day_of_week.compute_day_of_week_patterns(90)
        assert result["metrics"] == {}

    def test_single_metric_filter(self, day_of_week):
        import storage
        _write_mood_on_weekday(storage, 0, 1, 8.0)
        result = day_of_week.compute_day_of_week_patterns(90, metric="mood")
        assert list(result["metrics"].keys()) == ["mood"]

    def test_best_and_worst_day_for_mood(self, day_of_week):
        import storage
        _write_mood_on_weekday(storage, 0, 1, 9.0)   # Monday: great mood
        _write_mood_on_weekday(storage, 2, 8, 3.0)   # Wednesday: bad mood
        result = day_of_week.compute_day_of_week_patterns(90, metric="mood")
        data = result["metrics"]["mood"]
        assert data["best_day"] == "Monday"
        assert data["worst_day"] == "Wednesday"

    def test_stress_lower_is_better(self, day_of_week):
        import storage
        for offset in range(1, 15):
            dt = datetime.utcnow() - timedelta(days=offset)
            if dt.weekday() == 0:
                storage.write_memory({"type": "stress", "content": "stressed", "score": 9.0,
                                       "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ")})
            elif dt.weekday() == 3:
                storage.write_memory({"type": "stress", "content": "calm", "score": 1.0,
                                       "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ")})
        result = day_of_week.compute_day_of_week_patterns(90, metric="stress")
        data = result["metrics"]["stress"]
        # Lower stress is the "best" outcome, so the low-stress day wins.
        assert data["best_day"] == "Thursday"
        assert data["worst_day"] == "Monday"

    def test_sample_counts_tracked(self, day_of_week):
        import storage
        _write_mood_on_weekday(storage, 1, 2, 5.0)
        _write_mood_on_weekday(storage, 1, 9, 7.0)
        result = day_of_week.compute_day_of_week_patterns(90, metric="mood")
        assert result["metrics"]["mood"]["sample_counts"]["Tuesday"] == 2

    def test_days_param_passed_through(self, day_of_week):
        result = day_of_week.compute_day_of_week_patterns(days=30)
        assert result["days"] == 30

    def test_no_metric_checks_all_trackable_metrics(self, day_of_week):
        import storage
        _write_mood_on_weekday(storage, 4, 3, 8.0)
        result = day_of_week.compute_day_of_week_patterns(90)
        assert "mood" in result["metrics"]
        assert "energy" not in result["metrics"]


class TestFormatDayOfWeekInsights:
    def test_empty_metrics_returns_empty_list(self, day_of_week):
        result = {"days": 90, "metrics": {}}
        assert day_of_week.format_day_of_week_insights(result) == []

    def test_single_weekday_only_is_skipped(self, day_of_week):
        result = {"days": 90, "metrics": {
            "mood": {"weekday_averages": {"Monday": 8.0}, "sample_counts": {"Monday": 3},
                      "best_day": "Monday", "worst_day": "Monday"},
        }}
        assert day_of_week.format_day_of_week_insights(result) == []

    def test_two_weekdays_produces_one_line(self, day_of_week):
        result = {"days": 90, "metrics": {
            "mood": {"weekday_averages": {"Monday": 9.0, "Wednesday": 3.0},
                      "sample_counts": {"Monday": 3, "Wednesday": 2},
                      "best_day": "Monday", "worst_day": "Wednesday"},
        }}
        lines = day_of_week.format_day_of_week_insights(result)
        assert len(lines) == 1
        assert "Mood" in lines[0]
        assert "Mondays" in lines[0]
        assert "Wednesdays" in lines[0]
