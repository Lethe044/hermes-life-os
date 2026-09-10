"""Tests for demo/social_insights.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def social_insights(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "social_insights"):
        if mod in sys.modules:
            del sys.modules[mod]
    import social_insights as si
    importlib.reload(si)
    import storage
    storage.set_active_profile(None)
    return si


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeSocialInsights:
    def test_no_data_returns_empty(self, social_insights):
        result = social_insights.compute_social_insights(30)
        assert result["total_interactions"] == 0
        assert result["by_person"] == {}

    def test_totals_per_person(self, social_insights):
        import storage
        storage.save_social([
            {"date": _days_ago(1), "with_who": "Alice", "quality": 8, "duration_min": 60},
            {"date": _days_ago(2), "with_who": "Alice", "quality": 6, "duration_min": 30},
        ])
        result = social_insights.compute_social_insights(30)
        assert result["by_person"]["Alice"]["count"] == 2
        assert result["by_person"]["Alice"]["total_minutes"] == 90
        assert result["by_person"]["Alice"]["avg_quality"] == 7.0

    def test_most_frequent_contact(self, social_insights):
        import storage
        storage.save_social([
            {"date": _days_ago(1), "with_who": "Alice", "quality": 8, "duration_min": 60},
            {"date": _days_ago(2), "with_who": "Alice", "quality": 8, "duration_min": 60},
            {"date": _days_ago(3), "with_who": "Bob", "quality": 8, "duration_min": 60},
        ])
        result = social_insights.compute_social_insights(30)
        assert result["most_frequent_contact"] == "Alice"

    def test_blank_person_excluded_from_breakdown(self, social_insights):
        import storage
        storage.save_social([{"date": _days_ago(1), "with_who": "", "quality": 5, "duration_min": 10}])
        result = social_insights.compute_social_insights(30)
        assert result["by_person"] == {}
        assert result["total_interactions"] == 1

    def test_outside_window_excluded(self, social_insights):
        import storage
        storage.save_social([{"date": _days_ago(100), "with_who": "Alice", "quality": 8, "duration_min": 60}])
        result = social_insights.compute_social_insights(30)
        assert result["total_interactions"] == 0


class TestFormatSocialInsights:
    def test_no_data_message(self, social_insights):
        result = {"days": 30, "total_interactions": 0, "by_person": {},
                  "most_frequent_contact": None, "highest_quality_contact": None}
        text = social_insights.format_social_insights(result)
        assert "No social interactions logged" in text

    def test_with_data_shows_person_and_frequent(self, social_insights):
        result = {"days": 30, "total_interactions": 2, "by_person": {
            "Alice": {"count": 2, "total_minutes": 90, "avg_quality": 7.0},
        }, "most_frequent_contact": "Alice", "highest_quality_contact": "Alice"}
        text = social_insights.format_social_insights(result)
        assert "Alice: 2 interaction(s), 90 min total" in text
        assert "Most frequent: Alice." in text
