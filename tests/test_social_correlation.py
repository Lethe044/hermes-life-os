"""Tests for demo/social_correlation.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def social_correlation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "correlation_utils", "social_correlation"):
        if mod in sys.modules:
            del sys.modules[mod]
    import social_correlation as sc
    importlib.reload(sc)
    import storage
    storage.set_active_profile(None)
    return sc


def _ts(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestComputeSocialMoodImpact:
    def test_no_data_returns_none_diff(self, social_correlation):
        result = social_correlation.compute_social_mood_impact(90)
        assert result["mood_diff"] is None

    def test_with_vs_without_averages(self, social_correlation):
        import storage
        storage.save_social([{"date": _date(1), "with_who": "Alice", "quality": 8, "duration_min": 60}])
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 4, "timestamp": _ts(2)})
        result = social_correlation.compute_social_mood_impact(90)
        assert result["avg_mood_with_social"] == 9.0
        assert result["avg_mood_without_social"] == 4.0
        assert result["mood_diff"] == 5.0

    def test_day_without_mood_entry_excluded(self, social_correlation):
        import storage
        storage.save_social([{"date": _date(1), "with_who": "Alice", "quality": 8, "duration_min": 60}])
        result = social_correlation.compute_social_mood_impact(90)
        assert result["days_with_social"] == 0


class TestFormatSocialMoodImpact:
    def test_no_data_message(self, social_correlation):
        result = {"days": 90, "days_with_social": 0, "days_without_social": 0,
                  "avg_mood_with_social": None, "avg_mood_without_social": None, "mood_diff": None}
        text = social_correlation.format_social_mood_impact(result)
        assert "Not enough overlapping" in text

    def test_higher_direction(self, social_correlation):
        result = {"days": 90, "days_with_social": 2, "days_without_social": 2,
                  "avg_mood_with_social": 9.0, "avg_mood_without_social": 4.0, "mood_diff": 5.0}
        text = social_correlation.format_social_mood_impact(result)
        assert "higher on social days" in text

    def test_lower_direction(self, social_correlation):
        result = {"days": 90, "days_with_social": 2, "days_without_social": 2,
                  "avg_mood_with_social": 3.0, "avg_mood_without_social": 8.0, "mood_diff": -5.0}
        text = social_correlation.format_social_mood_impact(result)
        assert "lower on social days" in text
