"""Tests for demo/stress_summary.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def stress_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "stress_summary"):
        if mod in sys.modules:
            del sys.modules[mod]
    import stress_summary as ss
    importlib.reload(ss)
    import storage
    storage.set_active_profile(None)
    return ss


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeStressSummary:
    def test_no_entries_returns_zeroed_result(self, stress_summary):
        result = stress_summary.compute_stress_summary(30)
        assert result["total_entries"] == 0
        assert result["trend"] == "steady"

    def test_average_score(self, stress_summary):
        import storage
        storage.save_mental([
            {"date": _days_ago(1), "score": 8, "trigger": "work"},
            {"date": _days_ago(2), "score": 4, "trigger": "work"},
        ])
        result = stress_summary.compute_stress_summary(30)
        assert result["avg_score"] == 6.0

    def test_high_stress_days_counted(self, stress_summary):
        import storage
        storage.save_mental([
            {"date": _days_ago(1), "score": 9, "trigger": "work"},
            {"date": _days_ago(2), "score": 3, "trigger": "work"},
        ])
        result = stress_summary.compute_stress_summary(30)
        assert result["high_stress_days"] == 1

    def test_top_triggers(self, stress_summary):
        import storage
        storage.save_mental([
            {"date": _days_ago(1), "score": 5, "trigger": "work"},
            {"date": _days_ago(2), "score": 5, "trigger": "work"},
            {"date": _days_ago(3), "score": 5, "trigger": "sleep"},
        ])
        result = stress_summary.compute_stress_summary(30)
        assert result["top_triggers"][0] == ("work", 2)

    def test_trend_improving(self, stress_summary):
        import storage
        storage.save_mental([
            {"date": _days_ago(10), "score": 9, "trigger": "work"},
            {"date": _days_ago(8), "score": 9, "trigger": "work"},
            {"date": _days_ago(2), "score": 2, "trigger": "work"},
            {"date": _days_ago(1), "score": 2, "trigger": "work"},
        ])
        result = stress_summary.compute_stress_summary(30)
        assert result["trend"] == "improving"

    def test_trend_worsening(self, stress_summary):
        import storage
        storage.save_mental([
            {"date": _days_ago(10), "score": 2, "trigger": "work"},
            {"date": _days_ago(8), "score": 2, "trigger": "work"},
            {"date": _days_ago(2), "score": 9, "trigger": "work"},
            {"date": _days_ago(1), "score": 9, "trigger": "work"},
        ])
        result = stress_summary.compute_stress_summary(30)
        assert result["trend"] == "worsening"

    def test_trend_steady_for_small_difference(self, stress_summary):
        import storage
        storage.save_mental([
            {"date": _days_ago(10), "score": 5, "trigger": "work"},
            {"date": _days_ago(1), "score": 5.5, "trigger": "work"},
        ])
        result = stress_summary.compute_stress_summary(30)
        assert result["trend"] == "steady"

    def test_entries_without_score_excluded(self, stress_summary):
        import storage
        storage.save_mental([{"date": _days_ago(1), "type": "gratitude", "items": ["x"]}])
        result = stress_summary.compute_stress_summary(30)
        assert result["total_entries"] == 0

    def test_outside_window_excluded(self, stress_summary):
        import storage
        storage.save_mental([{"date": _days_ago(100), "score": 8, "trigger": "work"}])
        result = stress_summary.compute_stress_summary(30)
        assert result["total_entries"] == 0


class TestFormatStressSummary:
    def test_no_entries_message(self, stress_summary):
        result = {"days": 30, "total_entries": 0, "avg_score": 0.0, "trend": "steady",
                  "high_stress_days": 0, "top_triggers": []}
        text = stress_summary.format_stress_summary(result)
        assert "No stress logged" in text

    def test_with_data_shows_trend_and_triggers(self, stress_summary):
        result = {"days": 30, "total_entries": 5, "avg_score": 6.5, "trend": "worsening",
                  "high_stress_days": 2, "top_triggers": [("work", 3)]}
        text = stress_summary.format_stress_summary(result)
        assert "trend: worsening" in text
        assert "work (3)" in text
