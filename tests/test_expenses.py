"""Expense management: ids, list / update / delete, journal sync, legacy migration."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

DEMO = Path(__file__).parent.parent / "demo"
sys.path.insert(0, str(DEMO))

import clock  # noqa: E402 - needs the demo/ path set up above


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None) or ""
        if path.startswith(str(DEMO)) and name != "clock":
            del sys.modules[name]
    when = datetime(2026, 10, 12, 9, 0)
    monkeypatch.setattr(clock, "now", lambda: when)
    import tools
    importlib.reload(tools)
    import storage
    storage.set_active_profile(None)
    return tools


def log(app, amount, category="food", **kw):
    out = app.dispatch_tool("log_expense", {"amount": amount, "category": category, **kw})
    return out.split("[id=")[1].split("]")[0]


class TestIds:
    def test_logged_expense_gets_an_id_shown_in_the_reply(self, app):
        import storage
        eid = log(app, 10)
        assert storage.load_spending()[-1]["id"] == eid
        assert len(eid) == 8

    def test_journal_entry_is_linked(self, app):
        import storage
        eid = log(app, 10)
        assert storage.get_all_memory()[-1]["expense_id"] == eid

    def test_ids_are_unique(self, app):
        assert len({log(app, 1) for _ in range(30)}) == 30

    def test_legacy_rows_get_ids_once(self, app):
        import storage
        storage.save_spending([{"date": "2026-10-10", "amount": 5, "category": "food"},
                               {"date": "2026-10-11", "amount": 6, "category": "bus", "id": "keepme01"}])
        app.dispatch_tool("list_expenses", {})
        first = storage.load_spending()
        assert first[1]["id"] == "keepme01"
        assert first[0]["id"] and first[0]["id"] != "keepme01"
        app.dispatch_tool("list_expenses", {})
        assert storage.load_spending() == first


class TestList:
    def test_newest_first_with_ids(self, app):
        a = log(app, 1, date="2026-10-10")
        b = log(app, 2, date="2026-10-12")
        out = app.dispatch_tool("list_expenses", {})
        assert out.index(b) < out.index(a)
        assert "2026-10-12  2.00  food" in out

    def test_empty(self, app):
        assert app.dispatch_tool("list_expenses", {}) == "No expenses found in the last 30 days."

    def test_days_window_and_category_filter(self, app):
        log(app, 1, "food", date="2026-10-01")
        log(app, 2, "food")
        log(app, 3, "bus")
        out = app.dispatch_tool("list_expenses", {"days": 3, "category": "FOOD"})
        assert "2.00" in out and "1.00" not in out and "3.00" not in out

    def test_limit(self, app):
        for _ in range(5):
            log(app, 1)
        assert app.dispatch_tool("list_expenses", {"limit": 2}).startswith("2 expense(s)")

    def test_bad_numbers(self, app):
        assert "whole numbers" in app.dispatch_tool("list_expenses", {"days": "soon"})

    def test_notes_shown(self, app):
        log(app, 1, notes="lunch with Sam")
        assert "lunch with Sam" in app.dispatch_tool("list_expenses", {})


class TestUpdate:
    def test_changes_amount_category_notes(self, app):
        import storage
        eid = log(app, 10, "food")
        out = app.dispatch_tool("update_expense", {"expense_id": eid, "amount": 12.5,
                                                    "category": " Groceries ", "notes": "fixed"})
        assert "12.50" in out and "groceries" in out
        row = storage.load_spending()[0]
        assert (row["amount"], row["category"], row["notes"]) == (12.5, "groceries", "fixed")

    def test_syncs_the_journal_entry(self, app):
        import storage
        eid = log(app, 10, "food")
        app.dispatch_tool("update_expense", {"expense_id": eid, "amount": 20})
        mem = storage.get_all_memory()[-1]
        assert mem["amount"] == 20.0 and mem["content"] == "food: 20.0"

    def test_moving_the_date_moves_the_journal_stamp(self, app):
        import storage
        eid = log(app, 10)
        app.dispatch_tool("update_expense", {"expense_id": eid, "date": "2026-10-01"})
        assert storage.load_spending()[0]["date"] == "2026-10-01"
        assert storage.get_all_memory()[-1]["timestamp"] == "2026-10-01T12:00:00Z"

    def test_leaves_other_fields_alone(self, app):
        import storage
        eid = log(app, 10, "food", notes="n")
        app.dispatch_tool("update_expense", {"expense_id": eid, "amount": 11})
        row = storage.load_spending()[0]
        assert row["category"] == "food" and row["notes"] == "n" and row["date"] == "2026-10-12"

    @pytest.mark.parametrize("fields,msg", [
        ({"amount": 0}, "above 0"), ({"amount": -3}, "above 0"), ({"amount": "abc"}, "must be a number"),
        ({"amount": float("inf")}, "above 0"), ({"amount": float("nan")}, "above 0"),
        ({"category": "  "}, "category cannot be empty"),
        ({"date": "2026-10-13"}, "in the future"), ({"date": "soon"}, "YYYY-MM-DD"),
    ])
    def test_invalid_changes_leave_everything_untouched(self, app, fields, msg):
        import storage
        eid = log(app, 10)
        before = (storage.load_spending(), storage.get_all_memory())
        out = app.dispatch_tool("update_expense", {"expense_id": eid, **fields})
        assert out.startswith("Expense not changed: ") and msg in out
        assert (storage.load_spending(), storage.get_all_memory()) == before

    def test_partial_invalid_does_not_apply_valid_part(self, app):
        import storage
        eid = log(app, 10)
        app.dispatch_tool("update_expense", {"expense_id": eid, "amount": 99, "date": "garbage"})
        assert storage.load_spending()[0]["amount"] == 10.0

    def test_unknown_id(self, app):
        out = app.dispatch_tool("update_expense", {"expense_id": "nope", "amount": 1})
        assert "No expense found with id 'nope'" in out

    def test_nothing_to_change(self, app):
        eid = log(app, 10)
        assert app.dispatch_tool("update_expense", {"expense_id": eid}).startswith("Nothing to change")

    def test_legacy_row_without_journal_twin(self, app):
        import storage
        storage.save_spending([{"date": "2026-10-10", "amount": 5, "category": "food"}])
        eid = app.dispatch_tool("list_expenses", {}).split("[id=")[1].split("]")[0]
        assert "updated" in app.dispatch_tool("update_expense", {"expense_id": eid, "amount": 6})
        assert storage.load_spending()[0]["amount"] == 6.0

    def test_budget_sees_the_correction(self, app):
        import budgets
        eid = log(app, 100, "food")
        app.dispatch_tool("update_expense", {"expense_id": eid, "amount": 40})
        assert budgets._current_month_spent_by_category()["food"] == 40.0


class TestDelete:
    def test_removes_row_and_journal_entry_only_for_that_expense(self, app):
        import storage
        keep = log(app, 1)
        gone = log(app, 2)
        out = app.dispatch_tool("delete_expense", {"expense_id": gone})
        assert "Deleted expense" in out and "2.00" in out
        assert [e["id"] for e in storage.load_spending()] == [keep]
        assert [m["expense_id"] for m in storage.get_all_memory()] == [keep]

    def test_unknown_id(self, app):
        log(app, 1)
        assert "No expense found" in app.dispatch_tool("delete_expense", {"expense_id": "zzz"})

    def test_missing_id(self, app):
        assert "No expense found" in app.dispatch_tool("delete_expense", {})

    def test_deleted_expense_leaves_the_summary(self, app):
        eid = log(app, 50)
        app.dispatch_tool("delete_expense", {"expense_id": eid})
        assert "No spending logged" in app.dispatch_tool("get_spending_summary", {"days": 30})

    def test_double_delete(self, app):
        eid = log(app, 1)
        app.dispatch_tool("delete_expense", {"expense_id": eid})
        assert "No expense found" in app.dispatch_tool("delete_expense", {"expense_id": eid})


class TestSchemas:
    def test_new_tools_registered_with_required_id(self, app):
        schemas = {t["function"]["name"]: t["function"] for t in app.TOOLS}
        for n in ("update_expense", "delete_expense"):
            assert schemas[n]["parameters"]["required"] == ["expense_id"]
        assert "list_expenses" in schemas

    def test_every_schema_name_is_dispatchable(self, app):
        # Calling an unknown tool must not be what the new names do.
        for n in ("list_expenses", "update_expense", "delete_expense"):
            assert not app.dispatch_tool(n, {}).startswith("Unknown tool")
