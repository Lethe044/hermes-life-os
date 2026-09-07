"""Tests for demo/consistency.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def consistency(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "consistency"):
        if mod in sys.modules:
            del sys.modules[mod]
    import consistency as c
    importlib.reload(c)
    import storage
    storage.set_active_profile(None)
    return c


class TestComputeLoggingConsistency:
    def test_no_data_returns_zero(self, consistency):
        result = consistency.compute_logging_consistency(30)
        assert result["days_with_any_entry"] == 0
        assert result["overall_pct"] == 0.0
        assert result["per_metric_pct"] == {}

    def test_one_day_logged_out_of_window(self, consistency):
        import storage
        storage.write_memory({"type": "mood", "content": "ok", "score": 7})
        result = consistency.compute_logging_consistency(10)
        assert result["days_with_any_entry"] == 1
        assert result["overall_pct"] == 10.0

    def test_per_metric_pct_only_includes_logged_metrics(self, consistency):
        import storage
        storage.write_memory({"type": "sleep", "content": "slept", "hours": 7})
        result = consistency.compute_logging_consistency(10)
        assert "sleep" in result["per_metric_pct"]
        assert "mood" not in result["per_metric_pct"]

    def test_per_metric_pct_value(self, consistency):
        import storage
        storage.write_memory({"type": "sleep", "content": "slept", "hours": 7})
        result = consistency.compute_logging_consistency(5)
        assert result["per_metric_pct"]["sleep"] == 20.0

    def test_days_param_passed_through(self, consistency):
        result = consistency.compute_logging_consistency(days=45)
        assert result["days"] == 45


class TestFormatLoggingConsistency:
    def test_no_data_message(self, consistency):
        result = {"days": 30, "days_with_any_entry": 0, "overall_pct": 0.0, "per_metric_pct": {}}
        text = consistency.format_logging_consistency(result)
        assert "No entries logged" in text

    def test_with_data_shows_overall_and_per_metric(self, consistency):
        result = {"days": 30, "days_with_any_entry": 15, "overall_pct": 50.0,
                  "per_metric_pct": {"mood": 40.0, "sleep": 60.0}}
        text = consistency.format_logging_consistency(result)
        assert "15/30 days" in text
        assert "50.0%" in text
        assert "sleep: 60.0%" in text
        assert "mood: 40.0%" in text

    def test_per_metric_sorted_descending(self, consistency):
        result = {"days": 30, "days_with_any_entry": 15, "overall_pct": 50.0,
                  "per_metric_pct": {"mood": 10.0, "sleep": 90.0}}
        text = consistency.format_logging_consistency(result)
        assert text.index("sleep") < text.index("mood")
