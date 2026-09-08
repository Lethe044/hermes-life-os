"""Tests for demo/meal_summary.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def meal_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "meal_summary"):
        if mod in sys.modules:
            del sys.modules[mod]
    import meal_summary as ms
    importlib.reload(ms)
    import storage
    storage.set_active_profile(None)
    return ms


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeMealSummary:
    def test_no_meals_returns_zeroed_result(self, meal_summary):
        result = meal_summary.compute_meal_summary(30)
        assert result["total_meals"] == 0
        assert result["top_foods"] == []

    def test_totals_and_averages(self, meal_summary):
        import storage
        storage.save_nutrition([
            {"date": _days_ago(1), "time": "breakfast", "food": "oatmeal", "calories": 300},
            {"date": _days_ago(1), "time": "lunch", "food": "salad", "calories": 400},
        ])
        result = meal_summary.compute_meal_summary(30)
        assert result["total_meals"] == 2
        assert result["days_logged"] == 1
        assert result["avg_calories_per_meal"] == 350.0
        assert result["avg_calories_per_day"] == 700.0

    def test_by_meal_time_breakdown(self, meal_summary):
        import storage
        storage.save_nutrition([
            {"date": _days_ago(1), "time": "breakfast", "food": "oatmeal", "calories": 300},
            {"date": _days_ago(2), "time": "breakfast", "food": "eggs", "calories": 250},
            {"date": _days_ago(3), "time": "dinner", "food": "pasta", "calories": 600},
        ])
        result = meal_summary.compute_meal_summary(30)
        assert result["by_meal_time"] == {"breakfast": 2, "dinner": 1}

    def test_top_foods_case_insensitive(self, meal_summary):
        import storage
        storage.save_nutrition([
            {"date": _days_ago(1), "time": "lunch", "food": "Salad", "calories": 300},
            {"date": _days_ago(2), "time": "lunch", "food": "salad", "calories": 300},
        ])
        result = meal_summary.compute_meal_summary(30)
        assert result["top_foods"][0] == ("salad", 2)

    def test_outside_window_excluded(self, meal_summary):
        import storage
        storage.save_nutrition([{"date": _days_ago(60), "time": "lunch", "food": "salad", "calories": 300}])
        result = meal_summary.compute_meal_summary(30)
        assert result["total_meals"] == 0

    def test_meal_without_food_excluded_from_top_foods(self, meal_summary):
        import storage
        storage.save_nutrition([{"date": _days_ago(1), "time": "snack", "food": "", "calories": 100}])
        result = meal_summary.compute_meal_summary(30)
        assert result["top_foods"] == []


class TestFormatMealSummary:
    def test_no_meals_message(self, meal_summary):
        result = {"days": 30, "total_meals": 0, "days_logged": 0,
                  "avg_calories_per_meal": 0.0, "avg_calories_per_day": 0.0,
                  "by_meal_time": {}, "top_foods": []}
        text = meal_summary.format_meal_summary(result)
        assert "No meals logged" in text

    def test_with_data_shows_totals_and_foods(self, meal_summary):
        result = {"days": 30, "total_meals": 3, "days_logged": 2,
                  "avg_calories_per_meal": 350.0, "avg_calories_per_day": 525.0,
                  "by_meal_time": {"breakfast": 2, "lunch": 1},
                  "top_foods": [("oatmeal", 2)]}
        text = meal_summary.format_meal_summary(result)
        assert "3 meal(s)" in text
        assert "breakfast: 2" in text
        assert "oatmeal (2)" in text
