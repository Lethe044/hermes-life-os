"""Tests for demo/time_of_day.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def time_of_day(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "time_of_day"):
        if mod in sys.modules:
            del sys.modules[mod]
    import time_of_day as tod
    importlib.reload(tod)
    import storage
    storage.set_active_profile(None)
    return tod


def _write_mood_at_hour(storage, hour: int, value: float, days_ago: int = 1):
    dt = (datetime.utcnow() - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0)
    storage.write_memory({
        "type": "mood", "content": "feeling", "score": value,
        "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


class TestTimeBucket:
    def test_morning(self, time_of_day):
        assert time_of_day._time_bucket(8) == "Morning"

    def test_afternoon(self, time_of_day):
        assert time_of_day._time_bucket(14) == "Afternoon"

    def test_evening(self, time_of_day):
        assert time_of_day._time_bucket(19) == "Evening"

    def test_night_late(self, time_of_day):
        assert time_of_day._time_bucket(23) == "Night"

    def test_night_early(self, time_of_day):
        assert time_of_day._time_bucket(2) == "Night"

    def test_boundaries(self, time_of_day):
        assert time_of_day._time_bucket(5) == "Morning"
        assert time_of_day._time_bucket(11) == "Morning"
        assert time_of_day._time_bucket(12) == "Afternoon"
        assert time_of_day._time_bucket(17) == "Evening"
        assert time_of_day._time_bucket(22) == "Night"


class TestComputeTimeOfDayPatterns:
    def test_no_data_returns_empty_metrics(self, time_of_day):
        result = time_of_day.compute_time_of_day_patterns(90)
        assert result["metrics"] == {}

    def test_single_metric_filter(self, time_of_day):
        import storage
        _write_mood_at_hour(storage, 8, 7.0)
        result = time_of_day.compute_time_of_day_patterns(90, metric="mood")
        assert list(result["metrics"].keys()) == ["mood"]

    def test_best_and_worst_time(self, time_of_day):
        import storage
        _write_mood_at_hour(storage, 8, 9.0, days_ago=1)   # Morning: great
        _write_mood_at_hour(storage, 20, 2.0, days_ago=2)  # Evening: bad
        result = time_of_day.compute_time_of_day_patterns(90, metric="mood")
        data = result["metrics"]["mood"]
        assert data["best_time"] == "Morning"
        assert data["worst_time"] == "Evening"

    def test_stress_lower_is_better(self, time_of_day):
        import storage
        for i in range(1, 8):
            dt = (datetime.utcnow() - timedelta(days=i)).replace(hour=8, minute=0, second=0)
            storage.write_memory({"type": "stress", "content": "s", "score": 8.0,
                                   "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ")})
            dt2 = (datetime.utcnow() - timedelta(days=i)).replace(hour=20, minute=0, second=0)
            storage.write_memory({"type": "stress", "content": "s", "score": 1.0,
                                   "timestamp": dt2.strftime("%Y-%m-%dT%H:%M:%SZ")})
        result = time_of_day.compute_time_of_day_patterns(90, metric="stress")
        data = result["metrics"]["stress"]
        assert data["best_time"] == "Evening"
        assert data["worst_time"] == "Morning"

    def test_entries_without_timestamp_hour_excluded(self, time_of_day):
        import storage
        storage.write_memory({"type": "mood", "content": "feeling", "score": 5.0,
                               "timestamp": "not-a-valid-timestamp"})
        result = time_of_day.compute_time_of_day_patterns(90, metric="mood")
        assert result["metrics"] == {}

    def test_days_param_passed_through(self, time_of_day):
        result = time_of_day.compute_time_of_day_patterns(days=15)
        assert result["days"] == 15


class TestFormatTimeOfDayInsights:
    def test_empty_metrics_returns_empty_list(self, time_of_day):
        assert time_of_day.format_time_of_day_insights({"days": 90, "metrics": {}}) == []

    def test_single_bucket_only_is_skipped(self, time_of_day):
        result = {"days": 90, "metrics": {
            "mood": {"bucket_averages": {"Morning": 8.0}, "sample_counts": {"Morning": 3},
                      "best_time": "Morning", "worst_time": "Morning"},
        }}
        assert time_of_day.format_time_of_day_insights(result) == []

    def test_two_buckets_produces_one_line(self, time_of_day):
        result = {"days": 90, "metrics": {
            "mood": {"bucket_averages": {"Morning": 9.0, "Evening": 3.0},
                      "sample_counts": {"Morning": 3, "Evening": 2},
                      "best_time": "Morning", "worst_time": "Evening"},
        }}
        lines = time_of_day.format_time_of_day_insights(result)
        assert len(lines) == 1
        assert "Morning" in lines[0]
        assert "Evening" in lines[0]
