"""Tests for demo/focus_summary.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def focus_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "focus_summary"):
        if mod in sys.modules:
            del sys.modules[mod]
    import focus_summary as fs
    importlib.reload(fs)
    import storage
    storage.set_active_profile(None)
    return fs


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeFocusSummary:
    def test_no_sessions_returns_zeroed_result(self, focus_summary):
        result = focus_summary.compute_focus_summary(30)
        assert result["total_sessions"] == 0
        assert result["most_common_task"] is None

    def test_totals_and_averages(self, focus_summary):
        import storage
        storage.save_focus([
            {"date": _days_ago(1), "duration": 25, "quality": 8, "completed": True, "distractions": 1, "task": "writing"},
            {"date": _days_ago(2), "duration": 15, "quality": 6, "completed": False, "distractions": 3, "task": "writing"},
        ])
        result = focus_summary.compute_focus_summary(30)
        assert result["total_sessions"] == 2
        assert result["total_minutes"] == 40
        assert result["avg_duration"] == 20.0
        assert result["avg_quality"] == 7.0
        assert result["completed_sessions"] == 1
        assert result["completion_pct"] == 50.0
        assert result["total_distractions"] == 4
        assert result["most_common_task"] == "writing"

    def test_outside_window_excluded(self, focus_summary):
        import storage
        storage.save_focus([{"date": _days_ago(60), "duration": 25, "quality": 8,
                              "completed": True, "distractions": 0, "task": "reading"}])
        result = focus_summary.compute_focus_summary(30)
        assert result["total_sessions"] == 0

    def test_task_without_name_excluded_from_most_common(self, focus_summary):
        import storage
        storage.save_focus([{"date": _days_ago(1), "duration": 25, "quality": 8,
                              "completed": True, "distractions": 0, "task": ""}])
        result = focus_summary.compute_focus_summary(30)
        assert result["most_common_task"] is None


class TestFormatFocusSummary:
    def test_no_sessions_message(self, focus_summary):
        result = {"days": 30, "total_sessions": 0, "total_minutes": 0, "avg_duration": 0.0,
                  "avg_quality": 0.0, "completed_sessions": 0, "completion_pct": 0.0,
                  "total_distractions": 0, "most_common_task": None}
        text = focus_summary.format_focus_summary(result)
        assert "No focus sessions logged" in text

    def test_with_data_shows_totals_and_task(self, focus_summary):
        result = {"days": 30, "total_sessions": 2, "total_minutes": 40, "avg_duration": 20.0,
                  "avg_quality": 7.0, "completed_sessions": 1, "completion_pct": 50.0,
                  "total_distractions": 4, "most_common_task": "writing"}
        text = focus_summary.format_focus_summary(result)
        assert "2 focus session(s)" in text
        assert "writing" in text
