"""Tests for demo/budgets.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def budgets(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "budgets"):
        if mod in sys.modules:
            del sys.modules[mod]
    import budgets as b
    importlib.reload(b)
    import storage
    storage.set_active_profile(None)
    return b


class TestSetBudget:
    def test_set_budget_creates_entry(self, budgets):
        entry = budgets.set_budget("groceries", 400)
        assert entry == {"category": "groceries", "limit": 400}

    def test_set_budget_overwrites_existing_case_insensitive(self, budgets):
        budgets.set_budget("groceries", 400)
        budgets.set_budget("Groceries", 500)
        all_budgets = budgets.list_budgets()
        assert len(all_budgets) == 1
        assert all_budgets[0]["limit"] == 500
        # Case from the first call is preserved.
        assert all_budgets[0]["category"] == "groceries"

    def test_set_budget_persists_across_reload(self, budgets):
        budgets.set_budget("food", 200)
        from storage import load_budgets
        assert load_budgets() == [{"category": "food", "limit": 200}]


class TestListBudgets:
    def test_list_budgets_empty(self, budgets):
        assert budgets.list_budgets() == []

    def test_list_budgets_sorted_alphabetically(self, budgets):
        budgets.set_budget("shopping", 100)
        budgets.set_budget("food", 200)
        result = budgets.list_budgets()
        assert [b["category"] for b in result] == ["food", "shopping"]


class TestDeleteBudget:
    def test_delete_budget_removes(self, budgets):
        budgets.set_budget("food", 200)
        assert budgets.delete_budget("food") is True
        assert budgets.list_budgets() == []

    def test_delete_budget_case_insensitive(self, budgets):
        budgets.set_budget("Food", 200)
        assert budgets.delete_budget("food") is True

    def test_delete_budget_not_found(self, budgets):
        assert budgets.delete_budget("nonexistent") is False


class TestComputeBudgetStatus:
    def test_no_budgets(self, budgets):
        assert budgets.compute_budget_status() == []

    def test_budget_with_no_spending(self, budgets):
        budgets.set_budget("food", 100)
        result = budgets.compute_budget_status()
        assert result == [{
            "category": "food", "limit": 100, "spent": 0.0,
            "remaining": 100.0, "pct_used": 0.0, "over": False,
        }]

    def test_budget_with_current_month_spending(self, budgets, monkeypatch):
        from datetime import datetime
        from storage import load_spending, save_spending
        budgets.set_budget("food", 100)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        save_spending([{"date": today, "category": "food", "amount": 40}])
        result = budgets.compute_budget_status()
        assert result[0]["spent"] == 40.0
        assert result[0]["remaining"] == 60.0
        assert result[0]["pct_used"] == 40.0
        assert result[0]["over"] is False

    def test_budget_over_limit_flagged(self, budgets):
        from datetime import datetime
        from storage import save_spending
        budgets.set_budget("food", 10)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        save_spending([{"date": today, "category": "food", "amount": 50}])
        result = budgets.compute_budget_status()
        assert result[0]["over"] is True

    def test_spending_from_other_months_excluded(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([{"date": "2020-01-01", "category": "food", "amount": 999}])
        result = budgets.compute_budget_status()
        assert result[0]["spent"] == 0.0

    def test_filter_by_category(self, budgets):
        budgets.set_budget("food", 100)
        budgets.set_budget("fun", 50)
        result = budgets.compute_budget_status("fun")
        assert len(result) == 1
        assert result[0]["category"] == "fun"

    def test_zero_limit_with_spending_is_over_and_100_pct(self, budgets):
        from datetime import datetime
        from storage import save_spending
        budgets.set_budget("food", 0)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        save_spending([{"date": today, "category": "food", "amount": 5}])
        result = budgets.compute_budget_status()
        assert result[0]["pct_used"] == 100.0
        assert result[0]["over"] is True


class TestFormatBudgetStatus:
    def test_format_empty(self, budgets):
        assert budgets.format_budget_status([]) == "No budgets set yet."

    def test_format_includes_over_budget_flag(self, budgets):
        results = [{"category": "food", "limit": 10, "spent": 50, "remaining": -40,
                    "pct_used": 500.0, "over": True}]
        formatted = budgets.format_budget_status(results)
        assert "OVER BUDGET" in formatted
        assert "food" in formatted

    def test_format_orders_most_over_first(self, budgets):
        results = [
            {"category": "low", "limit": 100, "spent": 10, "remaining": 90, "pct_used": 10.0, "over": False},
            {"category": "high", "limit": 100, "spent": 90, "remaining": 10, "pct_used": 90.0, "over": False},
        ]
        formatted = budgets.format_budget_status(results)
        assert formatted.index("high") < formatted.index("low")


class TestFormatBudgetList:
    def test_format_empty(self, budgets):
        assert budgets.format_budget_list([]) == "No budgets set yet."

    def test_format_lists_limits(self, budgets):
        formatted = budgets.format_budget_list([{"category": "food", "limit": 200}])
        assert "food: 200" in formatted
