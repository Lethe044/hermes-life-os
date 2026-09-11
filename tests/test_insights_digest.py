"""Tests for demo/insights_digest.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def insights_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "correlation_utils", "habit_correlation",
                "reading_correlation", "social_correlation", "substance_correlation",
                "workout_correlation", "insights_digest"):
        if mod in sys.modules:
            del sys.modules[mod]
    import insights_digest as idg
    importlib.reload(idg)
    import storage
    storage.set_active_profile(None)
    return idg


def _ts(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestComputeInsightsDigest:
    def test_no_data_returns_empty_findings(self, insights_digest):
        result = insights_digest.compute_insights_digest(90)
        assert result["findings"] == []

    def test_workout_finding_surfaced_above_threshold(self, insights_digest):
        import storage
        storage.save_fitness([{"date": _date(1), "type": "run", "duration": 30}])
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 3, "timestamp": _ts(2)})
        result = insights_digest.compute_insights_digest(90, threshold=1.0)
        labels = [f["label"] for f in result["findings"]]
        assert "Workout vs mood" in labels

    def test_finding_below_threshold_excluded(self, insights_digest):
        import storage
        storage.save_fitness([{"date": _date(1), "type": "run", "duration": 30}])
        storage.write_memory({"type": "mood", "score": 5.2, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 5.0, "timestamp": _ts(2)})
        result = insights_digest.compute_insights_digest(90, threshold=5.0)
        assert result["findings"] == []

    def test_habit_finding_surfaced(self, insights_digest):
        import storage
        storage.write_memory({"type": "habit_completion", "habit": "meditate",
                               "completed": True, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "habit_completion", "habit": "meditate",
                               "completed": False, "timestamp": _ts(2)})
        storage.write_memory({"type": "mood", "score": 3, "timestamp": _ts(2)})
        storage.save_habits([{"name": "meditate", "streak": 1, "best_streak": 1}])
        result = insights_digest.compute_insights_digest(90, threshold=1.0)
        labels = [f["label"] for f in result["findings"]]
        assert "'meditate' vs mood" in labels

    def test_substance_finding_surfaced(self, insights_digest):
        import storage
        storage.save_substance([{"date": _date(1), "substance": "caffeine", "amount": 1}])
        storage.write_memory({"type": "sleep", "hours": 4, "timestamp": _ts(1)})
        storage.write_memory({"type": "sleep", "hours": 8, "timestamp": _ts(2)})
        result = insights_digest.compute_insights_digest(90, threshold=1.0)
        labels = [f["label"] for f in result["findings"]]
        assert "'caffeine' vs sleep" in labels

    def test_findings_sorted_by_absolute_diff_descending(self, insights_digest):
        import storage
        storage.save_fitness([{"date": _date(1), "type": "run", "duration": 30}])
        storage.save_social([{"date": _date(3), "with_who": "Alice", "quality": 8, "duration_min": 60}])
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 8.5, "timestamp": _ts(3)})
        storage.write_memory({"type": "mood", "score": 2, "timestamp": _ts(2)})
        result = insights_digest.compute_insights_digest(90, threshold=1.0)
        diffs = [abs(f["diff"]) for f in result["findings"]]
        assert diffs == sorted(diffs, reverse=True)


class TestFormatInsightsDigest:
    def test_empty_findings_message(self, insights_digest):
        result = {"days": 90, "threshold": 1.0, "findings": []}
        text = insights_digest.format_insights_digest(result)
        assert "Nothing stood out" in text

    def test_with_findings_lists_each(self, insights_digest):
        result = {"days": 90, "threshold": 1.0, "findings": [
            {"label": "Workout vs mood", "diff": 5.0, "detail": "Some detail here."},
        ]}
        text = insights_digest.format_insights_digest(result)
        assert "Workout vs mood: Some detail here." in text
