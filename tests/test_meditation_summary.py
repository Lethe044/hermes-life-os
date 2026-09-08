"""Tests for demo/meditation_summary.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def meditation_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "meditation_summary"):
        if mod in sys.modules:
            del sys.modules[mod]
    import meditation_summary as ms
    importlib.reload(ms)
    import storage
    storage.set_active_profile(None)
    return ms


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeMeditationSummary:
    def test_no_sessions_returns_zeroed_result(self, meditation_summary):
        result = meditation_summary.compute_meditation_summary(30)
        assert result["total_sessions"] == 0
        assert result["consistency_pct"] == 0.0

    def test_non_meditation_mental_entries_excluded(self, meditation_summary):
        import storage
        storage.save_mental([{"date": _days_ago(1), "type": "gratitude", "items": ["sun"]}])
        result = meditation_summary.compute_meditation_summary(30)
        assert result["total_sessions"] == 0

    def test_totals_and_average(self, meditation_summary):
        import storage
        storage.save_mental([
            {"date": _days_ago(1), "type": "meditation", "duration": 10},
            {"date": _days_ago(2), "type": "meditation", "duration": 20},
        ])
        result = meditation_summary.compute_meditation_summary(30)
        assert result["total_sessions"] == 2
        assert result["total_minutes"] == 30
        assert result["avg_duration"] == 15.0

    def test_multiple_sessions_same_day_count_once_for_consistency(self, meditation_summary):
        import storage
        storage.save_mental([
            {"date": _days_ago(1), "type": "meditation", "duration": 10},
            {"date": _days_ago(1), "type": "meditation", "duration": 5},
        ])
        result = meditation_summary.compute_meditation_summary(10)
        assert result["days_with_session"] == 1
        assert result["consistency_pct"] == 10.0

    def test_outside_window_excluded(self, meditation_summary):
        import storage
        storage.save_mental([{"date": _days_ago(60), "type": "meditation", "duration": 10}])
        result = meditation_summary.compute_meditation_summary(30)
        assert result["total_sessions"] == 0


class TestFormatMeditationSummary:
    def test_no_sessions_message(self, meditation_summary):
        result = {"days": 30, "total_sessions": 0, "total_minutes": 0,
                  "avg_duration": 0.0, "days_with_session": 0, "consistency_pct": 0.0}
        text = meditation_summary.format_meditation_summary(result)
        assert "No meditation sessions logged" in text

    def test_with_data_shows_totals_and_consistency(self, meditation_summary):
        result = {"days": 30, "total_sessions": 5, "total_minutes": 75,
                  "avg_duration": 15.0, "days_with_session": 5, "consistency_pct": 16.7}
        text = meditation_summary.format_meditation_summary(result)
        assert "5 meditation session(s)" in text
        assert "16.7%" in text
