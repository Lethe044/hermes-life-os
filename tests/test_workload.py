"""Workload forecast."""

from __future__ import annotations

from datetime import datetime


def test_nothing_due(planner):
    assert planner.dispatch_tool("get_workload_forecast", {}).startswith("Nothing is due in the next 14 days")


def test_validation(planner):
    for bad in (0, 31, "x", True):
        assert planner.dispatch_tool("get_workload_forecast", {"days": bad}).startswith("Cannot forecast")


def test_overload_and_moves(planner):
    import workload
    d = planner.dispatch_tool
    d("add_task", {"text": "Big report", "due": "2026-10-14", "minutes": 240, "priority": "high"})
    d("add_task", {"text": "Taxes", "due": "2026-10-14", "minutes": 240, "priority": "normal"})
    d("add_task", {"text": "Tidy desk", "due": "2026-10-14", "minutes": 90, "priority": "low"})
    d("add_time_block", {"title": "Workshop", "start": "08:00", "end": "17:00", "date": "2026-10-14"})
    res = workload.forecast(5)
    day = next(r for r in res["days"] if r["date"] == "2026-10-14")
    assert day["load"] == 570 and day["free"] == 360 and day["status"] == "overloaded"
    assert res["moves"][0] == {"task": "Tidy desk", "minutes": 90, "from": "2026-10-14", "to": "2026-10-15"}
    out = d("get_workload_forecast", {"days": 5})
    assert "[OVER]".replace("OVER", "OVER") in out and "1 day overloaded: Wed." in out
    assert "move 'Tidy desk' (90 min) from 2026-10-14 to 2026-10-15" in out


def test_overdue_counts_today_and_linked_blocks_are_skipped(planner):
    import workload
    d = planner.dispatch_tool
    d("add_task", {"text": "Old one", "due": "2026-10-01", "minutes": 60})
    d("add_task", {"text": "Held", "due": "2026-10-13", "minutes": 60})
    d("add_task", {"text": "Undated"})
    held = [t for t in workload.__dict__ and __import__("tasks")._rows(__import__("tasks")._load()) if t["text"] == "Held"][0]
    d("add_time_block", {"title": "Held", "start": "10:00", "end": "11:00", "date": "2026-10-13", "task": held["id"]})
    today = workload.forecast(2)["days"][0]
    assert [t["text"] for t in today["tasks"]] == ["Old one"] and today["load"] == 60


def test_default_minutes_and_status_labels(planner):
    import workload
    assert workload._minutes({}) == 30 and workload._minutes({"minutes": True}) == 30 and workload._minutes({"minutes": 45}) == 45
    assert workload._label(0, 100) == "clear" and workload._label(60, 100) == "ok"
    assert workload._label(90, 100) == "tight" and workload._label(101, 100) == "overloaded"


def test_nudge_and_agenda(planner):
    import workload
    d = planner.dispatch_tool
    assert workload.nudges() == [] and workload.agenda_lines() == []
    d("add_task", {"text": "Huge", "due": "2026-10-14", "minutes": 480})
    d("add_task", {"text": "Huger", "due": "2026-10-14", "minutes": 120})
    assert workload.nudges()[0].startswith("Tomorrow is overloaded") and workload.agenda_lines()
    planner.set_now(datetime(2026, 10, 13, 21, 30))
    d("add_task", {"text": "Late", "due": "2026-10-13", "minutes": 120})
    assert any(l.startswith("Today is overloaded") for l in workload._worst_soon())
