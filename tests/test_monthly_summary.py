"""Tests for demo/monthly_summary.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def monthly_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "monthly_summary"):
        if mod in sys.modules:
            del sys.modules[mod]
    import monthly_summary as ms
    importlib.reload(ms)
    import storage
    storage.set_active_profile(None)
    return ms


class TestMonthBounds:
    def test_regular_month(self, monthly_summary):
        start, end = monthly_summary._month_bounds(2025, 4)
        assert start == "2025-04-01"
        assert end == "2025-04-30"

    def test_february_non_leap_year(self, monthly_summary):
        start, end = monthly_summary._month_bounds(2025, 2)
        assert end == "2025-02-28"

    def test_february_leap_year(self, monthly_summary):
        start, end = monthly_summary._month_bounds(2024, 2)
        assert end == "2024-02-29"


class TestPreviousMonth:
    def test_regular_case(self, monthly_summary):
        assert monthly_summary._previous_month(2025, 6) == (2025, 5)

    def test_january_wraps_to_previous_december(self, monthly_summary):
        assert monthly_summary._previous_month(2025, 1) == (2024, 12)


class TestComputeMonthlyComparison:
    def test_no_data_returns_empty_comparison(self, monthly_summary):
        result = monthly_summary.compute_monthly_comparison(today="2025-06-10")
        assert result["comparison"] == {}
        assert result["current_month"] == "2025-06"
        assert result["previous_month"] == "2025-05"
        assert result["days_compared"] == 10

    def test_january_previous_month_is_last_december(self, monthly_summary):
        result = monthly_summary.compute_monthly_comparison(today="2025-01-05")
        assert result["previous_month"] == "2024-12"

    def test_improvement_reflected_in_comparison(self, monthly_summary):
        import storage
        # This month (June): higher mood.
        storage.write_memory({"type": "mood", "content": "great", "score": 9.0,
                               "timestamp": "2025-06-01T10:00:00Z"})
        # Last month (May), same day-of-month span: lower mood.
        storage.write_memory({"type": "mood", "content": "meh", "score": 4.0,
                               "timestamp": "2025-05-01T10:00:00Z"})
        result = monthly_summary.compute_monthly_comparison(today="2025-06-01")
        assert result["comparison"]["mood"]["current"] == 9.0
        assert result["comparison"]["mood"]["previous"] == 4.0
        assert result["comparison"]["mood"]["delta"] == 5.0

    def test_previous_month_span_capped_at_its_own_length(self, monthly_summary):
        # Comparing on Jan 31 means "previous month" (Dec) span should be
        # capped at Dec's actual last day, not overshoot into January data.
        result = monthly_summary.compute_monthly_comparison(today="2025-01-31")
        assert result["days_compared"] == 31


class TestFormatMonthlyComparison:
    def test_empty_comparison_message(self, monthly_summary):
        result = {"current_month": "2025-06", "previous_month": "2025-05",
                  "days_compared": 10, "comparison": {}}
        text = monthly_summary.format_monthly_comparison(result)
        assert "Not enough overlapping data" in text

    def test_with_data_shows_direction(self, monthly_summary):
        result = {"current_month": "2025-06", "previous_month": "2025-05", "days_compared": 10,
                  "comparison": {"mood": {"current": 8.0, "previous": 5.0,
                                            "delta": 3.0, "pct_change": 60.0}}}
        text = monthly_summary.format_monthly_comparison(result)
        assert "up 60.0%" in text

    def test_negative_delta_shows_down(self, monthly_summary):
        result = {"current_month": "2025-06", "previous_month": "2025-05", "days_compared": 10,
                  "comparison": {"stress": {"current": 3.0, "previous": 6.0,
                                              "delta": -3.0, "pct_change": -50.0}}}
        text = monthly_summary.format_monthly_comparison(result)
        assert "down 50.0%" in text
