"""Income and cash flow."""

from __future__ import annotations

from datetime import datetime

import pytest


def inc(p, amount=3000, **kw):
    out = p.dispatch_tool("log_income", {"amount": amount, **kw})
    assert out.startswith("Logged: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_income()


def flow(p, **kw):
    return p.dispatch_tool("get_cash_flow", kw)


class TestLog:
    def test_minimal(self, planner):
        iid = inc(planner)
        assert rows() == [{"id": iid, "date": "2026-10-13", "amount": 3000.0, "source": "income"}]

    def test_output(self, planner):
        out = planner.dispatch_tool("log_income", {"amount": 3000, "source": "  Salary ", "notes": "oct"})
        assert out.startswith("Logged: Income 3,000 (Salary) on 2026-10-13 [id=")
        assert out.endswith("2026-10 so far: income 3,000, spent 0, net 3,000.")
        assert rows()[0]["notes"] == "oct"

    def test_cents_are_kept(self, planner):
        out = planner.dispatch_tool("log_income", {"amount": 250.456})
        assert "Income 250.46 (income)" in out and rows()[0]["amount"] == 250.46

    def test_numeric_string(self, planner):
        inc(planner, "100")
        assert rows()[0]["amount"] == 100.0

    @pytest.mark.parametrize("amount", [0, -5, "x", None, True, float("inf"), float("nan"), 1e13, 0.001, [5]])
    def test_bad_amounts(self, planner, amount):
        out = planner.dispatch_tool("log_income", {"amount": amount})
        assert out.startswith("Not logged: amount ") and rows() == []

    @pytest.mark.parametrize("source", [5, ["x"], "s" * 61])
    def test_bad_sources(self, planner, source):
        assert planner.dispatch_tool("log_income", {"amount": 5, "source": source}).startswith("Not logged: ")
        assert rows() == []

    def test_blank_source_defaults(self, planner):
        inc(planner, 5, source="  ")
        assert rows()[0]["source"] == "income"

    def test_backdated_to_its_own_month(self, planner):
        out = planner.dispatch_tool("log_income", {"amount": 10, "date": "2026-09-01"})
        assert "on 2026-09-01" in out and "\n2026-09: income 10" in out and "so far" not in out

    @pytest.mark.parametrize("date,msg", [("2026-10-14", "in the future"), ("soon", "not a valid date")])
    def test_bad_dates(self, planner, date, msg):
        assert msg in planner.dispatch_tool("log_income", {"amount": 5, "date": date}) and rows() == []

    def test_journal_entry_is_linked(self, planner):
        import storage
        iid = inc(planner, 120, source="refund")
        m = storage.get_all_memory()[-1]
        assert m["type"] == "income" and m["log_id"] == iid and m["content"] == "Income 120 (refund)"

    def test_does_not_touch_expenses(self, planner):
        import storage
        inc(planner)
        assert storage.load_spending() == []

    def test_limit(self, planner):
        import storage
        storage.save_income([{"id": str(i), "date": "2026-10-01", "amount": 1} for i in range(20000)])
        assert "already holds 20000" in planner.dispatch_tool("log_income", {"amount": 1})


class TestCashFlow:
    def test_empty(self, planner):
        assert flow(planner) == "No income or spending logged in the last 3 month(s)."

    def test_months_and_rates(self, planner):
        inc(planner, 3000, source="salary", date="2026-10-01")
        inc(planner, 3000, source="salary", date="2026-09-01")
        inc(planner, 250.5, source="freelance", date="2026-09-15")
        planner.dispatch_tool("log_expense", {"amount": 1200, "category": "rent", "date": "2026-09-02"})
        planner.dispatch_tool("log_expense", {"amount": 400, "category": "food", "date": "2026-10-05"})
        assert flow(planner).split("\n") == [
            "Cash flow, last 3 month(s):",
            "- 2026-10 (so far): income 3,000, spent 400, net +2,600, kept 86.7% of income.",
            "- 2026-09: income 3,250.50, spent 1,200, net +2,050.50, kept 63.1% of income.",
            "- 2026-08: nothing logged.",
            "Income sources: salary 6,000, freelance 250.50."]

    def test_spending_without_income(self, planner):
        planner.dispatch_tool("log_expense", {"amount": 50, "category": "food"})
        out = flow(planner)
        assert "income 0, spent 50, net -50, no income logged." in out

    def test_overspending_this_month_is_called_out(self, planner):
        inc(planner, 100)
        planner.dispatch_tool("log_expense", {"amount": 300, "category": "x"})
        assert "spent more than you earned so far (300 vs 100)" in flow(planner)

    def test_overspending_without_income_is_not_called_out(self, planner):
        planner.dispatch_tool("log_expense", {"amount": 300, "category": "x"})
        assert "more than you earned" not in flow(planner)

    def test_average_of_finished_months(self, planner):
        inc(planner, 1000, date="2026-09-01")
        inc(planner, 2000, date="2026-08-01")
        out = flow(planner, months=3)
        assert "Average net of the 2 finished month(s): +1,500." in out

    def test_average_needs_two_finished_months(self, planner):
        inc(planner, 1000, date="2026-09-01")
        assert "Average net" not in flow(planner)

    def test_one_month_window(self, planner):
        inc(planner, 1000, date="2026-09-01")
        inc(planner, 7)
        out = flow(planner, months=1)
        assert out.startswith("Cash flow, last 1 month(s):") and "2026-09" not in out

    def test_year_boundary(self, planner):
        planner.set_now(datetime(2027, 1, 15, 9, 0))
        inc(planner, 10, date="2026-12-20")
        out = flow(planner, months=3)
        assert "- 2027-01 (so far)" in out and "- 2026-12:" in out and "- 2026-11:" in out

    @pytest.mark.parametrize("months", [0, 25, -1, "x", None])
    def test_bad_months(self, planner, months):
        assert flow(planner, months=months).startswith("Cannot show cash flow: months")

    def test_day_start_hour_defines_the_current_month(self, planner, monkeypatch):
        planner.set_now(datetime(2026, 11, 1, 2, 0))
        monkeypatch.setenv("LIFE_OS_DAY_START_HOUR", "4")
        inc(planner, 10)  # 02:00 on the 1st still belongs to October for a night owl
        assert rows()[0]["date"] == "2026-10-31"
        assert "- 2026-10 (so far): income 10," in flow(planner, months=1)

    def test_garbage_rows_are_ignored(self, planner):
        import storage
        storage.save_income(["x", None, {"date": "2026-10-01", "amount": "lots"}, {"date": "2026-10-01", "amount": -5},
                             {"date": "2026-10-01", "amount": True}, {"amount": 5},
                             {"id": "k", "date": "2026-10-02", "amount": 40, "source": None}])
        storage.save_spending(["y", {"date": "2026-10-03", "amount": "x"}, {"date": "2026-10-03", "amount": 10}])
        assert "income 40, spent 10, net +30, kept 75% of income." in flow(planner)

    def test_not_list_stores(self, planner):
        import storage
        storage.save_income({"x": 1})
        assert flow(planner).startswith("No income or spending")


class TestEntryTools:
    def test_list_edit_delete(self, planner):
        import storage
        iid = inc(planner, 500, source="gig")
        assert "Income 500 (gig)" in planner.dispatch_tool("list_logs", {"tracker": "income"})
        planner.dispatch_tool("edit_log", {"tracker": "income", "log_id": iid,
                                           "fields": {"amount": 650, "source": "big gig", "notes": "n"}})
        r = rows()[0]
        assert (r["amount"], r["source"], r["notes"]) == (650, "big gig", "n")
        assert storage.get_all_memory()[-1]["content"] == "Income 650 (big gig)"
        planner.dispatch_tool("delete_log", {"tracker": "income", "log_id": iid})
        assert rows() == [] and storage.get_all_memory() == []

    @pytest.mark.parametrize("fields", [{"amount": 0}, {"amount": -3}, {"amount": "x"}, {"bogus": 1}])
    def test_invalid_edits_change_nothing(self, planner, fields):
        iid = inc(planner, 500)
        before = rows()
        planner.dispatch_tool("edit_log", {"tracker": "income", "log_id": iid, "fields": fields})
        assert rows() == before

    def test_undo(self, planner):
        inc(planner)
        planner.dispatch_tool("undo_last_log", {"tracker": "income"})
        assert rows() == []

    def test_log_many(self, planner):
        out = planner.dispatch_tool("log_many", {"entries": [
            {"tool": "log_income", "args": {"amount": 10, "date": "2026-10-10"}},
            {"tool": "log_income", "args": {"amount": 20}}]})
        assert {r["date"] for r in rows()} == {"2026-10-10", "2026-10-13"}, out

    def test_tracker_names(self, planner):
        import entries
        assert planner._TRACKER_NAMES == entries.tracker_names() and "income" in entries.tracker_names()

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        assert schemas["log_income"]["parameters"]["required"] == ["amount"]
        assert schemas["log_income"]["parameters"]["properties"]["date"] == planner._ENTRY_DATE_PROP

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        inc(planner, 77)
        path = backup.run_backup()
        storage.save_income([])
        restore.restore_backup(path, only="income", safety_backup=False)
        assert rows()[0]["amount"] == 77
