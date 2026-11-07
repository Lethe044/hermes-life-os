"""Net worth."""

from __future__ import annotations

from datetime import datetime


def test_create_and_update(planner):
    d = planner.dispatch_tool
    assert d("set_account_balance", {"name": "Checking", "balance": 2500, "kind": "asset", "category": "Cash"}) == \
        "Added asset Checking: 2,500. Net worth: 2,500."
    assert "Added liability Loan: 1,000.5. Net worth: 1,499.5." in d("set_account_balance", {"name": "Loan", "balance": 1000.5, "kind": "liability"})
    out = d("set_account_balance", {"name": "checking", "balance": 3000})
    assert "Checking is now 3,000 (was 2,500)" in out and "Net worth: 1,999.5" in out


def test_validation(planner):
    d = planner.dispatch_tool
    assert "asset or a liability" in d("set_account_balance", {"name": "X", "balance": 1})
    assert d("set_account_balance", {"name": "X", "balance": "1", "kind": "asset"}).startswith("Balance not saved:")
    assert d("set_account_balance", {"name": "X", "balance": True, "kind": "asset"}).startswith("Balance not saved:")
    assert d("set_account_balance", {"name": "X", "balance": float("nan"), "kind": "asset"}).startswith("Balance not saved:")
    assert "too large" in d("set_account_balance", {"name": "X", "balance": 1e15, "kind": "asset"})
    d("set_account_balance", {"name": "Cash", "balance": 5, "kind": "asset"})
    assert "is a asset" in d("set_account_balance", {"name": "Cash", "balance": 5, "kind": "liability"})


def test_same_day_replaces_history_and_change_is_shown(planner):
    import networth
    d = planner.dispatch_tool
    d("set_account_balance", {"name": "Savings", "balance": 1000, "kind": "asset"})
    d("set_account_balance", {"name": "Savings", "balance": 1100})
    assert len(networth._load()[0]["history"]) == 1
    planner.set_now(datetime(2026, 11, 13, 9, 0))
    d("set_account_balance", {"name": "Savings", "balance": 1500})
    out = d("get_net_worth", {})
    assert "Net worth: 1,500" in out and "Change since 2026-10-13: +400" in out and "Savings (other): 1,500" in out


def test_trend_uses_the_balance_on_each_month_end(planner):
    d = planner.dispatch_tool
    d("set_account_balance", {"name": "Savings", "balance": 1000, "kind": "asset"})
    planner.set_now(datetime(2026, 12, 5, 9, 0))
    d("set_account_balance", {"name": "Savings", "balance": 2000})
    out = d("get_net_worth_trend", {"months": 3})
    assert "- 2026-10: 1,000" in out and "- 2026-11: 1,000" in out and "- 2026-12 (today): 2,000" in out
    assert "From 1,000 to 2,000 (+1,000)" in out
    assert "no data" in d("get_net_worth_trend", {"months": 5})


def test_empty_and_bad_months(planner):
    d = planner.dispatch_tool
    assert d("get_net_worth", {}).startswith("No accounts yet")
    assert d("get_net_worth_trend", {}).startswith("No history yet")
    assert d("get_net_worth_trend", {"months": 1}).startswith("Cannot show the trend:")


def test_nudge_after_35_days_and_delete(planner):
    import networth
    d = planner.dispatch_tool
    assert networth.nudges() == []
    d("set_account_balance", {"name": "Cash", "balance": 5, "kind": "asset"})
    planner.set_now(datetime(2026, 11, 10, 9, 0))
    assert networth.nudges() == []
    planner.set_now(datetime(2026, 11, 20, 9, 0))
    assert "38 days ago" in networth.nudges()[0]
    assert "Deleted the account Cash" in d("delete_account", {"account": "cash"})
    assert d("delete_account", {"account": "cash"}).startswith("Account not deleted:")


def test_damaged_accounts_are_skipped(planner):
    import networth, storage
    storage.save_networth([{"name": "bad"}, 3, {"name": "ok", "kind": "asset", "balance": 5, "updated": "2026-10-13",
                                                  "history": [{"date": "2026-10-13", "balance": 5}]}])
    assert networth.total_on("2026-10-13")["net"] == 5
