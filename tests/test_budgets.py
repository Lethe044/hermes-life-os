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


class TestCaseInsensitiveSpending:
    """Regression: log_expense stores the category exactly as the agent
    typed it, so "Food" spending must still count against a "food" budget."""

    def test_status_counts_spending_with_different_case(self, budgets):
        from datetime import datetime
        from storage import save_spending
        budgets.set_budget("food", 100)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        save_spending([
            {"date": today, "category": "Food", "amount": 30},
            {"date": today, "category": "FOOD", "amount": 20},
            {"date": today, "category": "food", "amount": 10},
        ])
        result = budgets.compute_budget_status()
        assert result[0]["spent"] == 60.0

    def test_status_budget_case_differs_from_spending_case(self, budgets):
        from datetime import datetime
        from storage import save_spending
        budgets.set_budget("Groceries", 100)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        save_spending([{"date": today, "category": "groceries", "amount": 45}])
        assert budgets.compute_budget_status()[0]["spent"] == 45.0

    def test_missing_category_counts_as_uncategorized(self, budgets):
        from datetime import datetime
        from storage import save_spending
        budgets.set_budget("uncategorized", 100)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        save_spending([{"date": today, "amount": 15}, {"date": today, "category": None, "amount": 5}])
        assert budgets.compute_budget_status()[0]["spent"] == 20.0


def _dt(y, m, d):
    from datetime import datetime
    return datetime(y, m, d, 12, 0)


class TestComputeBudgetStatusToday:
    def test_today_param_selects_month(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([
            {"date": "2026-09-10", "category": "food", "amount": 70},
            {"date": "2026-10-02", "category": "food", "amount": 25},
        ])
        assert budgets.compute_budget_status(today=_dt(2026, 9, 20))[0]["spent"] == 70.0
        assert budgets.compute_budget_status(today=_dt(2026, 10, 20))[0]["spent"] == 25.0


class TestBudgetForecast:
    def test_no_budgets(self, budgets):
        assert budgets.compute_budget_forecast(today=_dt(2026, 10, 10)) == []

    def test_will_exceed_when_pace_passes_limit(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 300)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 100}])
        r = budgets.compute_budget_forecast(today=_dt(2026, 10, 10))[0]
        # 100 over 10 days of a 31-day month -> 310 projected
        assert r["projected"] == 310.0
        assert r["status"] == "will_exceed"
        assert r["remaining"] == 200.0
        assert r["days_left"] == 21
        assert r["daily_allowance"] == round(200 / 21, 2)

    def test_on_track(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 500)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 100}])
        r = budgets.compute_budget_forecast(today=_dt(2026, 10, 10))[0]
        assert r["status"] == "on_track"

    def test_already_over(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 300)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 350}])
        r = budgets.compute_budget_forecast(today=_dt(2026, 10, 10))[0]
        assert r["status"] == "over"
        assert r["daily_allowance"] == 0.0
        assert r["remaining"] == -50.0

    def test_no_spending_is_on_track_with_zero_projection(self, budgets):
        budgets.set_budget("food", 300)
        r = budgets.compute_budget_forecast(today=_dt(2026, 10, 10))[0]
        assert r["projected"] == 0.0
        assert r["status"] == "on_track"

    def test_last_day_of_month_allowance_is_whole_remainder(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 300)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 250}])
        r = budgets.compute_budget_forecast(today=_dt(2026, 10, 31))[0]
        assert r["days_left"] == 0
        assert r["daily_allowance"] == 50.0

    def test_february_uses_28_days(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 1000)
        save_spending([{"date": "2027-02-03", "category": "food", "amount": 70}])
        r = budgets.compute_budget_forecast(today=_dt(2027, 2, 7))[0]
        assert r["days_left"] == 21
        assert r["projected"] == round(70 / 7 * 28, 2)

    def test_leap_february_uses_29_days(self, budgets):
        budgets.set_budget("food", 1000)
        r = budgets.compute_budget_forecast(today=_dt(2028, 2, 10))[0]
        assert r["days_left"] == 19

    def test_low_confidence_early_in_month(self, budgets):
        budgets.set_budget("food", 300)
        assert budgets.compute_budget_forecast(today=_dt(2026, 10, 3))[0]["low_confidence"] is True
        assert budgets.compute_budget_forecast(today=_dt(2026, 10, 10))[0]["low_confidence"] is False

    def test_filter_by_category_case_insensitive(self, budgets):
        budgets.set_budget("Food", 100)
        budgets.set_budget("fun", 50)
        result = budgets.compute_budget_forecast("food", today=_dt(2026, 10, 10))
        assert [r["category"] for r in result] == ["Food"]

    def test_spending_case_insensitive(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 300)
        save_spending([{"date": "2026-10-04", "category": "FOOD", "amount": 100}])
        assert budgets.compute_budget_forecast(today=_dt(2026, 10, 10))[0]["spent"] == 100.0

    def test_other_months_excluded(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 300)
        save_spending([{"date": "2026-09-04", "category": "food", "amount": 999}])
        assert budgets.compute_budget_forecast(today=_dt(2026, 10, 10))[0]["spent"] == 0.0

    def test_zero_limit_with_spending_is_over(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 0)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 5}])
        assert budgets.compute_budget_forecast(today=_dt(2026, 10, 10))[0]["status"] == "over"


class TestFormatBudgetForecast:
    def test_format_empty(self, budgets):
        assert budgets.format_budget_forecast([]) == "No budgets set yet."

    def test_format_orders_worst_first_and_describes_each_state(self, budgets):
        from storage import save_spending
        budgets.set_budget("aaa_ok", 1000)
        budgets.set_budget("bbb_pace", 300)
        budgets.set_budget("ccc_over", 50)
        save_spending([
            {"date": "2026-10-04", "category": "aaa_ok", "amount": 10},
            {"date": "2026-10-04", "category": "bbb_pace", "amount": 100},
            {"date": "2026-10-04", "category": "ccc_over", "amount": 80},
        ])
        out = budgets.format_budget_forecast(budgets.compute_budget_forecast(today=_dt(2026, 10, 10)))
        assert out.index("ccc_over") < out.index("bbb_pace") < out.index("aaa_ok")
        assert "OVER by 30" in out
        assert "on pace for 310.0" in out
        assert "on track" in out

    def test_format_early_month_note(self, budgets):
        budgets.set_budget("food", 100)
        out = budgets.format_budget_forecast(budgets.compute_budget_forecast(today=_dt(2026, 10, 2)))
        assert "rough" in out

    def test_format_no_early_note_later_in_month(self, budgets):
        budgets.set_budget("food", 100)
        out = budgets.format_budget_forecast(budgets.compute_budget_forecast(today=_dt(2026, 10, 20)))
        assert "rough" not in out


class TestBudgetHistory:
    def test_no_budgets(self, budgets):
        result = budgets.compute_budget_history(today=_dt(2026, 10, 15))
        assert result["categories"] == []
        assert result["months"] == ["2026-07", "2026-08", "2026-09"]

    def test_excludes_current_month_and_is_oldest_first(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([
            {"date": "2026-07-05", "category": "food", "amount": 50},
            {"date": "2026-08-05", "category": "food", "amount": 150},
            {"date": "2026-09-05", "category": "food", "amount": 100},
            {"date": "2026-10-05", "category": "food", "amount": 999},
        ])
        result = budgets.compute_budget_history(3, today=_dt(2026, 10, 15))
        c = result["categories"][0]
        assert [h["month"] for h in c["history"]] == ["2026-07", "2026-08", "2026-09"]
        assert [h["spent"] for h in c["history"]] == [50.0, 150.0, 100.0]
        assert [h["over"] for h in c["history"]] == [False, True, False]  # 100 is not over 100
        assert c["months_over"] == 1
        assert c["avg_spent"] == 100.0

    def test_year_rollover(self, budgets):
        result = budgets.compute_budget_history(3, today=_dt(2026, 2, 10))
        assert result["months"] == ["2025-11", "2025-12", "2026-01"]

    def test_january_looks_back_to_previous_year(self, budgets):
        result = budgets.compute_budget_history(1, today=_dt(2026, 1, 10))
        assert result["months"] == ["2025-12"]

    def test_months_clamped(self, budgets):
        assert len(budgets.compute_budget_history(0, today=_dt(2026, 10, 15))["months"]) == 1
        assert len(budgets.compute_budget_history(-5, today=_dt(2026, 10, 15))["months"]) == 1
        assert len(budgets.compute_budget_history(100, today=_dt(2026, 10, 15))["months"]) == 24

    def test_case_insensitive_and_sorted(self, budgets):
        from storage import save_spending
        budgets.set_budget("zeta", 10)
        budgets.set_budget("Alpha", 100)
        save_spending([{"date": "2026-09-05", "category": "ALPHA", "amount": 40}])
        result = budgets.compute_budget_history(1, today=_dt(2026, 10, 15))
        assert [c["category"] for c in result["categories"]] == ["Alpha", "zeta"]
        assert result["categories"][0]["history"][0]["spent"] == 40.0

    def test_format_empty(self, budgets):
        assert budgets.format_budget_history(budgets.compute_budget_history()) == "No budgets set yet."

    def test_format_includes_month_breakdown(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([{"date": "2026-08-05", "category": "food", "amount": 150}])
        out = budgets.format_budget_history(budgets.compute_budget_history(3, today=_dt(2026, 10, 15)))
        assert "last 3 completed month(s)" in out
        assert "2026-08: 150.0 (over)" in out
        assert "over in 1/3 months" in out
        assert "current limits" in out


class TestUnbudgetedSpending:
    def test_no_spending(self, budgets):
        result = budgets.compute_unbudgeted_spending(today=_dt(2026, 10, 10))
        assert result == {"total": 0.0, "categories": []}

    def test_lists_only_categories_without_budget_biggest_first(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([
            {"date": "2026-10-02", "category": "food", "amount": 40},
            {"date": "2026-10-02", "category": "fun", "amount": 30},
            {"date": "2026-10-03", "category": "gifts", "amount": 90},
            {"date": "2026-10-04", "category": "fun", "amount": 10},
        ])
        result = budgets.compute_unbudgeted_spending(today=_dt(2026, 10, 10))
        assert result["categories"] == [
            {"category": "gifts", "spent": 90.0},
            {"category": "fun", "spent": 40.0},
        ]
        assert result["total"] == 130.0

    def test_budget_matching_is_case_insensitive(self, budgets):
        from storage import save_spending
        budgets.set_budget("Food", 100)
        save_spending([{"date": "2026-10-02", "category": "food", "amount": 40}])
        assert budgets.compute_unbudgeted_spending(today=_dt(2026, 10, 10))["categories"] == []

    def test_other_months_excluded(self, budgets):
        from storage import save_spending
        save_spending([{"date": "2026-09-02", "category": "fun", "amount": 40}])
        assert budgets.compute_unbudgeted_spending(today=_dt(2026, 10, 10))["categories"] == []

    def test_zero_amounts_skipped(self, budgets):
        from storage import save_spending
        save_spending([{"date": "2026-10-02", "category": "fun", "amount": 0}])
        assert budgets.compute_unbudgeted_spending(today=_dt(2026, 10, 10))["categories"] == []

    def test_format_none(self, budgets):
        out = budgets.format_unbudgeted_spending(budgets.compute_unbudgeted_spending(today=_dt(2026, 10, 10)))
        assert out == "No spending outside your budgets this month."

    def test_format_lists_categories(self, budgets):
        from storage import save_spending
        save_spending([{"date": "2026-10-02", "category": "gifts", "amount": 90}])
        out = budgets.format_unbudgeted_spending(budgets.compute_unbudgeted_spending(today=_dt(2026, 10, 10)))
        assert "90.0 total" in out
        assert "- gifts: 90.0" in out


class TestBudgetAlerts:
    def test_no_budgets_no_alerts(self, budgets):
        assert budgets.budget_alerts(today=_dt(2026, 10, 10)) == []

    def test_comfortable_budget_no_alert(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 50}])
        assert budgets.budget_alerts(today=_dt(2026, 10, 10)) == []

    def test_near_limit_alerts_with_days_left(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 85}])
        alerts = budgets.budget_alerts(today=_dt(2026, 10, 10))
        assert len(alerts) == 1
        assert "85.0% used" in alerts[0]
        assert "21 days to go" in alerts[0]

    def test_exactly_at_threshold_alerts(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 80}])
        assert len(budgets.budget_alerts(today=_dt(2026, 10, 10))) == 1

    def test_over_budget_alerts(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 130}])
        alerts = budgets.budget_alerts(today=_dt(2026, 10, 10))
        assert len(alerts) == 1
        assert "is over" in alerts[0]

    def test_custom_threshold(self, budgets):
        from storage import save_spending
        budgets.set_budget("food", 100)
        save_spending([{"date": "2026-10-04", "category": "food", "amount": 55}])
        assert budgets.budget_alerts(today=_dt(2026, 10, 10)) == []
        assert len(budgets.budget_alerts(threshold_pct=50, today=_dt(2026, 10, 10))) == 1

    def test_zero_limit_without_spending_no_alert(self, budgets):
        budgets.set_budget("food", 0)
        assert budgets.budget_alerts(today=_dt(2026, 10, 10)) == []
