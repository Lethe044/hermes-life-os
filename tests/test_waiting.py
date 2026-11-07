"""Waiting-for list."""

from __future__ import annotations

from datetime import datetime


def test_add_default_follow_up_and_duplicates(planner):
    d = planner.dispatch_tool
    out = d("add_waiting", {"what": "Quote", "who": "plumber"})
    assert out.startswith("Waiting for: Quote from plumber - asked today") and "follow up 2026-10-20" in out
    assert "already waiting" in d("add_waiting", {"what": "quote", "who": "Plumber"})
    assert d("add_waiting", {"what": "Quote", "who": "electrician"}).startswith("Waiting for:")
    assert d("add_waiting", {"what": ""}).startswith("Not added:")
    assert "in the past" in d("add_waiting", {"what": "x", "follow_up": "2026-10-01"})
    assert d("add_waiting", {"what": "y", "follow_up": "sometime"}).startswith("Not added:")


def test_list_order_and_due_count(planner):
    d = planner.dispatch_tool
    assert d("get_waiting", {}).startswith("You are not waiting")
    d("add_waiting", {"what": "Later", "follow_up": "2026-10-30"})
    d("add_waiting", {"what": "Now", "who": "Sam", "follow_up": "today"})
    out = d("get_waiting", {}).splitlines()
    assert out[0] == "Waiting for 2 things (1 due for a follow-up):" and out[1].startswith("- Now from Sam")


def test_chase_resolve_delete(planner):
    import waiting
    d = planner.dispatch_tool
    d("add_waiting", {"what": "Contract", "who": "Sam", "follow_up": "today"})
    assert "Next one on 2026-10-16" in d("chase_waiting", {"item": "contract", "days": 3})
    assert "chased 1 time" in d("get_waiting", {})
    assert d("chase_waiting", {"item": "contract", "days": 0}).startswith("Follow-up not recorded:")
    assert "no longer pending" in d("resolve_waiting", {"item": "contract"})
    assert d("resolve_waiting", {"item": "contract"}).startswith("Not resolved:")
    assert waiting.open_items() == []
    d("add_waiting", {"what": "Refund"})
    assert "Deleted 'Refund'" in d("delete_waiting", {"item": "refund"})


def test_nudge_and_agenda(planner):
    import waiting
    d = planner.dispatch_tool
    d("add_waiting", {"what": "Parcel", "who": "courier"})
    assert waiting.nudges() == [] and waiting.agenda_lines() == []
    planner.set_now(datetime(2026, 10, 21, 9, 0))
    assert "follow up on 'Parcel' from courier" in waiting.nudges()[0].replace("Time to f", "f").replace("Time to", "")
    d("add_waiting", {"what": "Other", "follow_up": "today"})
    assert "(and 1 more)" in waiting.nudges()[0] and len(waiting.agenda_lines()) == 2


def test_damaged_rows(planner):
    import storage, waiting
    storage.save_waiting([{"what": 3}, "x", {"id": "1", "what": "ok", "chase": "2026-10-13", "asked": "2026-10-13"}])
    assert [r["what"] for r in waiting.open_items()] == ["ok"]
