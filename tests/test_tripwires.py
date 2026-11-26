"""Tripwires."""

from __future__ import annotations

from datetime import datetime, timedelta


def feed(monkeypatch, metric, values):
    """values: {offset_from_today: number}."""
    import metricseries
    data = {(datetime(2026, 10, 13) + timedelta(days=k)).strftime("%Y-%m-%d"): {metric: v} for k, v in values.items()}
    monkeypatch.setattr(metricseries, "load_daily", lambda: data)


def test_add_validation(planner):
    d = planner.dispatch_tool
    out = d("add_tripwire", {"name": "Sleep debt", "metric": "sleep", "condition": "below", "threshold": 6, "days": 3})
    assert out.startswith("Tripwire set: Sleep debt: sleep below 6 for 3 days in a row")
    assert "already exists" in d("add_tripwire", {"name": "sleep DEBT", "metric": "mood", "condition": "below", "threshold": 3})
    for bad in ({"metric": "x"}, {"condition": "near"}, {"threshold": "a"}, {"threshold": True}, {"days": 0}, {"days": 31}, {"name": ""}):
        args = {"name": "n", "metric": "mood", "condition": "below", "threshold": 3}
        args.update(bad)
        assert d("add_tripwire", args).startswith("Tripwire not set:"), bad


def test_trips_after_enough_days(planner, monkeypatch):
    import tripwires
    d = planner.dispatch_tool
    d("add_tripwire", {"name": "Sleep debt", "metric": "sleep", "condition": "below", "threshold": 6, "days": 3,
                       "message": "Protect tonight."})
    feed(monkeypatch, "sleep", {0: 5, -1: 5.5})
    assert "none tripped" in d("get_tripwires", {}) and tripwires.nudges() == []
    feed(monkeypatch, "sleep", {0: 5, -1: 5.5, -2: 4})
    out = d("get_tripwires", {})
    assert "1 tripped" in out and "TRIPPED (held 3 days)" in out
    assert tripwires.nudges() == ["Tripwire 'Sleep debt': Protect tonight."]
    assert tripwires.agenda_lines() == ["Sleep debt: Protect tonight."]
    feed(monkeypatch, "sleep", {-1: 5, -2: 5, -3: 5})  # no reading today yet: counts from yesterday
    assert tripwires.tripped()
    feed(monkeypatch, "sleep", {0: 8, -1: 5, -2: 5, -3: 5})
    assert not tripwires.tripped()
    feed(monkeypatch, "sleep", {})
    assert "no data yet" in d("get_tripwires", {})


def test_above_and_live_counts(planner, monkeypatch):
    import tripwires
    d = planner.dispatch_tool
    d("add_tripwire", {"name": "Stress", "metric": "stress", "condition": "above", "threshold": 7, "days": 2})
    feed(monkeypatch, "stress", {0: 8, -1: 9})
    assert tripwires.tripped()
    d("add_tripwire", {"name": "Backlog", "metric": "overdue_tasks", "condition": "above", "threshold": 1, "days": 9})
    assert tripwires.listing()[0]["days"] == 1
    feed(monkeypatch, "stress", {})
    assert not tripwires.tripped()
    d("add_task", {"text": "a", "due": "2026-10-01"})
    assert not tripwires.tripped()
    d("add_task", {"text": "b", "due": "2026-10-02"})
    assert [t["wire"]["name"] for t in tripwires.tripped()] == ["Backlog"]


def test_delete_and_damaged(planner):
    import storage, tripwires
    d = planner.dispatch_tool
    assert d("get_tripwires", {}).startswith("No tripwires yet")
    storage.save_tripwires([{"name": 1}, "x", {"id": "z", "name": "ok", "metric": "mood", "op": "below", "threshold": 3, "days": 2, "message": "m"}])
    assert [r["name"] for r in tripwires.listing()] == ["ok"]
    assert "Deleted tripwire 'ok'" in d("delete_tripwire", {"tripwire": "ok"})
    assert d("delete_tripwire", {"tripwire": "ok"}).startswith("Tripwire not deleted:")


def test_follow_up_task_is_created_once(planner, monkeypatch):
    import tasks
    d = planner.dispatch_tool
    assert d("act_on_tripwires", {}) == "No tripped tripwire has a follow-up task to create."
    out = d("add_tripwire", {"name": "Sleep debt", "metric": "sleep", "condition": "below", "threshold": 6, "days": 2,
                             "task": "Protect tonight's sleep"})
    assert "then add task 'Protect tonight's sleep'" in out
    d("add_tripwire", {"name": "Plain", "metric": "sleep", "condition": "below", "threshold": 6, "days": 2})
    feed(monkeypatch, "sleep", {0: 5, -1: 5})
    assert "Would create 1 task due today" in d("act_on_tripwires", {"apply": False})
    assert not tasks._rows(tasks._load())
    out = d("act_on_tripwires", {})
    assert out == "Created 1 task due today: 'Protect tonight's sleep'."
    made = tasks._rows(tasks._load())[0]
    assert made["due"] == "2026-10-13" and made["priority"] == "high" and made["tags"] == ["tripwire"]
    assert d("act_on_tripwires", {}) == "Already open: 'Protect tonight's sleep'."
    feed(monkeypatch, "sleep", {0: 8})
    assert d("act_on_tripwires", {}).startswith("No tripped")
    assert d("act_on_tripwires", {"apply": "x"}).startswith("Cannot act on tripwires:")
    assert d("add_tripwire", {"name": "n2", "metric": "mood", "condition": "below", "threshold": 2, "task": "x" * 101}).startswith("Tripwire not set:")
