"""Tests for demo/spending_trends.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def spending_trends(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "spending_trends"):
        if mod in sys.modules:
            del sys.modules[mod]
    import spending_trends as st
    importlib.reload(st)
    import storage
    storage.set_active_profile(None)
    return st


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeSpendingTrends:
    def test_no_data_returns_empty_categories(self, spending_trends):
        result = spending_trends.compute_spending_trends(30)
        assert result["categories"] == {}

    def test_current_vs_previous_window(self, spending_trends):
        import storage
        storage.save_spending([
            {"date": _days_ago(5), "category": "food", "amount": 100},
            {"date": _days_ago(40), "category": "food", "amount": 50},
        ])
        result = spending_trends.compute_spending_trends(30)
        assert result["categories"]["food"]["current"] == 100.0
        assert result["categories"]["food"]["previous"] == 50.0
        assert result["categories"]["food"]["delta"] == 50.0
        assert result["categories"]["food"]["pct_change"] == 100.0

    def test_category_only_in_current_window(self, spending_trends):
        import storage
        storage.save_spending([{"date": _days_ago(5), "category": "travel", "amount": 200}])
        result = spending_trends.compute_spending_trends(30)
        assert result["categories"]["travel"]["previous"] == 0.0
        assert result["categories"]["travel"]["pct_change"] == 100.0

    def test_category_only_in_previous_window(self, spending_trends):
        import storage
        storage.save_spending([{"date": _days_ago(40), "category": "travel", "amount": 200}])
        result = spending_trends.compute_spending_trends(30)
        assert result["categories"]["travel"]["current"] == 0.0
        assert result["categories"]["travel"]["pct_change"] == -100.0

    def test_beyond_previous_window_excluded(self, spending_trends):
        import storage
        storage.save_spending([{"date": _days_ago(200), "category": "food", "amount": 999}])
        result = spending_trends.compute_spending_trends(30)
        assert result["categories"] == {}

    def test_multiple_entries_same_category_summed(self, spending_trends):
        import storage
        storage.save_spending([
            {"date": _days_ago(1), "category": "food", "amount": 30},
            {"date": _days_ago(2), "category": "food", "amount": 20},
        ])
        result = spending_trends.compute_spending_trends(30)
        assert result["categories"]["food"]["current"] == 50.0


class TestFormatSpendingTrends:
    def test_empty_categories_message(self, spending_trends):
        result = {"days": 30, "categories": {}}
        text = spending_trends.format_spending_trends(result)
        assert "No spending logged" in text

    def test_up_direction(self, spending_trends):
        result = {"days": 30, "categories": {
            "food": {"current": 100.0, "previous": 50.0, "delta": 50.0, "pct_change": 100.0},
        }}
        text = spending_trends.format_spending_trends(result)
        assert "up 100.0%" in text

    def test_down_direction(self, spending_trends):
        result = {"days": 30, "categories": {
            "food": {"current": 20.0, "previous": 50.0, "delta": -30.0, "pct_change": -60.0},
        }}
        text = spending_trends.format_spending_trends(result)
        assert "down 60.0%" in text

    def test_sorted_by_biggest_dollar_swing(self, spending_trends):
        result = {"days": 30, "categories": {
            "food": {"current": 55.0, "previous": 50.0, "delta": 5.0, "pct_change": 10.0},
            "travel": {"current": 300.0, "previous": 100.0, "delta": 200.0, "pct_change": 200.0},
        }}
        text = spending_trends.format_spending_trends(result)
        assert text.index("travel") < text.index("food")
