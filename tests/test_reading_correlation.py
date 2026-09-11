"""Tests for demo/reading_correlation.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def reading_correlation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "correlation_utils", "reading_correlation"):
        if mod in sys.modules:
            del sys.modules[mod]
    import reading_correlation as rc
    importlib.reload(rc)
    import storage
    storage.set_active_profile(None)
    return rc


def _ts(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestComputeReadingMoodImpact:
    def test_no_data_returns_none_diff(self, reading_correlation):
        result = reading_correlation.compute_reading_mood_impact(90)
        assert result["mood_diff"] is None

    def test_with_vs_without_averages(self, reading_correlation):
        import storage
        storage.save_reading([{"date": _date(1), "title": "Book A", "pages": 20}])
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 4, "timestamp": _ts(2)})
        result = reading_correlation.compute_reading_mood_impact(90)
        assert result["avg_mood_with_reading"] == 9.0
        assert result["avg_mood_without_reading"] == 4.0
        assert result["mood_diff"] == 5.0


class TestFormatReadingMoodImpact:
    def test_no_data_message(self, reading_correlation):
        result = {"days": 90, "days_with_reading": 0, "days_without_reading": 0,
                  "avg_mood_with_reading": None, "avg_mood_without_reading": None, "mood_diff": None}
        text = reading_correlation.format_reading_mood_impact(result)
        assert "Not enough overlapping" in text

    def test_higher_direction(self, reading_correlation):
        result = {"days": 90, "days_with_reading": 2, "days_without_reading": 2,
                  "avg_mood_with_reading": 9.0, "avg_mood_without_reading": 4.0, "mood_diff": 5.0}
        text = reading_correlation.format_reading_mood_impact(result)
        assert "higher on reading days" in text
