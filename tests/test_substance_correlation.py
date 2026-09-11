"""Tests for demo/substance_correlation.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def substance_correlation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "correlation_utils", "substance_correlation"):
        if mod in sys.modules:
            del sys.modules[mod]
    import substance_correlation as sc
    importlib.reload(sc)
    import storage
    storage.set_active_profile(None)
    return sc


def _ts(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestComputeSubstanceSleepImpact:
    def test_no_data_returns_none_diff(self, substance_correlation):
        result = substance_correlation.compute_substance_sleep_impact("caffeine", 90)
        assert result["sleep_diff"] is None

    def test_with_vs_without_averages(self, substance_correlation):
        import storage
        storage.save_substance([{"date": _date(1), "substance": "caffeine", "amount": 1}])
        storage.write_memory({"type": "sleep", "hours": 5, "timestamp": _ts(1)})
        storage.write_memory({"type": "sleep", "hours": 8, "timestamp": _ts(2)})
        result = substance_correlation.compute_substance_sleep_impact("caffeine", 90)
        assert result["avg_sleep_with"] == 5.0
        assert result["avg_sleep_without"] == 8.0
        assert result["sleep_diff"] == -3.0

    def test_substance_matching_case_insensitive(self, substance_correlation):
        import storage
        storage.save_substance([{"date": _date(1), "substance": "Caffeine", "amount": 1}])
        storage.write_memory({"type": "sleep", "hours": 5, "timestamp": _ts(1)})
        storage.write_memory({"type": "sleep", "hours": 8, "timestamp": _ts(2)})
        result = substance_correlation.compute_substance_sleep_impact("caffeine", 90)
        assert result["days_with_substance"] == 1

    def test_different_substance_not_mixed_in(self, substance_correlation):
        import storage
        storage.save_substance([{"date": _date(1), "substance": "alcohol", "amount": 1}])
        storage.write_memory({"type": "sleep", "hours": 5, "timestamp": _ts(1)})
        result = substance_correlation.compute_substance_sleep_impact("caffeine", 90)
        assert result["days_with_substance"] == 0

    def test_day_without_sleep_entry_excluded(self, substance_correlation):
        import storage
        storage.save_substance([{"date": _date(1), "substance": "caffeine", "amount": 1}])
        result = substance_correlation.compute_substance_sleep_impact("caffeine", 90)
        assert result["days_with_substance"] == 0


class TestFormatSubstanceSleepImpact:
    def test_no_data_message(self, substance_correlation):
        result = {"substance": "caffeine", "days": 90, "days_with_substance": 0,
                  "days_without_substance": 0, "avg_sleep_with": None,
                  "avg_sleep_without": None, "sleep_diff": None}
        text = substance_correlation.format_substance_sleep_impact(result)
        assert "Not enough overlapping" in text

    def test_less_sleep_direction(self, substance_correlation):
        result = {"substance": "caffeine", "days": 90, "days_with_substance": 2,
                  "days_without_substance": 2, "avg_sleep_with": 5.0,
                  "avg_sleep_without": 8.0, "sleep_diff": -3.0}
        text = substance_correlation.format_substance_sleep_impact(result)
        assert "less sleep" in text

    def test_more_sleep_direction(self, substance_correlation):
        result = {"substance": "melatonin", "days": 90, "days_with_substance": 2,
                  "days_without_substance": 2, "avg_sleep_with": 8.5,
                  "avg_sleep_without": 7.0, "sleep_diff": 1.5}
        text = substance_correlation.format_substance_sleep_impact(result)
        assert "more sleep" in text
