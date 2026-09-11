"""Tests for demo/correlation_utils.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def correlation_utils(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "correlation_utils"):
        if mod in sys.modules:
            del sys.modules[mod]
    import correlation_utils as cu
    importlib.reload(cu)
    import storage
    storage.set_active_profile(None)
    return cu


def _ts(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestEntryDate:
    def test_valid_timestamp(self, correlation_utils):
        assert correlation_utils.entry_date({"timestamp": "2026-01-05T10:00:00Z"}) == "2026-01-05"

    def test_missing_timestamp(self, correlation_utils):
        assert correlation_utils.entry_date({}) is None

    def test_invalid_timestamp(self, correlation_utils):
        assert correlation_utils.entry_date({"timestamp": "not-a-date"}) is None


class TestMetricByDate:
    def test_groups_by_date(self, correlation_utils):
        import storage
        storage.write_memory({"type": "mood", "score": 8, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 6, "timestamp": _ts(1)})
        result = correlation_utils.metric_by_date(90, "mood")
        date_key = list(result.keys())[0]
        assert result[date_key] == [8.0, 6.0]

    def test_wrong_metric_excluded(self, correlation_utils):
        import storage
        storage.write_memory({"type": "stress", "score": 8, "timestamp": _ts(1)})
        result = correlation_utils.metric_by_date(90, "mood")
        assert result == {}


class TestComputeMetricImpactByPresence:
    def test_no_data_returns_none_diff(self, correlation_utils):
        result = correlation_utils.compute_metric_impact_by_presence(set(), "mood", 90)
        assert result["diff"] is None

    def test_present_vs_absent_split(self, correlation_utils):
        import storage
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 3, "timestamp": _ts(2)})
        date1 = correlation_utils.entry_date({"timestamp": _ts(1)})
        result = correlation_utils.compute_metric_impact_by_presence({date1}, "mood", 90)
        assert result["avg_metric_true"] == 9.0
        assert result["avg_metric_false"] == 3.0
        assert result["diff"] == 6.0

    def test_absence_inferred_not_required_to_be_logged(self, correlation_utils):
        import storage
        storage.write_memory({"type": "mood", "score": 5, "timestamp": _ts(1)})
        # No explicit "event didn't happen" record exists anywhere - the date
        # simply isn't in event_dates, and that alone should count as "false".
        result = correlation_utils.compute_metric_impact_by_presence(set(), "mood", 90)
        assert result["days_false"] == 1
        assert result["days_true"] == 0


class TestComputeMetricImpactByStatus:
    def test_dates_outside_status_dict_excluded(self, correlation_utils):
        import storage
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        # This mood entry's date has no corresponding status entry at all,
        # so it should be excluded from both sides rather than counted false.
        result = correlation_utils.compute_metric_impact_by_status({}, "mood", 90)
        assert result["days_true"] == 0
        assert result["days_false"] == 0

    def test_explicit_true_false_split(self, correlation_utils):
        import storage
        storage.write_memory({"type": "mood", "score": 9, "timestamp": _ts(1)})
        storage.write_memory({"type": "mood", "score": 3, "timestamp": _ts(2)})
        date1 = correlation_utils.entry_date({"timestamp": _ts(1)})
        date2 = correlation_utils.entry_date({"timestamp": _ts(2)})
        result = correlation_utils.compute_metric_impact_by_status(
            {date1: True, date2: False}, "mood", 90)
        assert result["avg_metric_true"] == 9.0
        assert result["avg_metric_false"] == 3.0
