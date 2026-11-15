"""Life timeline."""

from __future__ import annotations


def test_empty(planner):
    assert planner.dispatch_tool("get_life_timeline", {}).startswith("Nothing on your timeline for 2026-10-07 to 2026-10-13")


def test_validation(planner):
    d = planner.dispatch_tool
    for args in ({"days": 0}, {"days": 91}, {"days": "x"}, {"kinds": "nope"}, {"kinds": 5}):
        assert d("get_life_timeline", args).startswith("Cannot build the timeline"), args


def test_merges_sources_newest_first(planner, monkeypatch):
    import metricseries
    d = planner.dispatch_tool
    monkeypatch.setattr(metricseries, "load_daily", lambda: {"2026-10-12": {"mood": 7.0, "sleep": 6.5}})
    d("add_task", {"text": "File taxes"})
    d("complete_task", {"task": "taxes"})
    d("add_library_item", {"title": "Dune", "kind": "book", "status": "done"})
    d("log_life_wheel", {"scores": {"health": 6, "career": 8}})
    d("add_waiting", {"what": "Quote", "who": "Sam"})
    d("resolve_waiting", {"item": "quote"})
    d("start_experiment", {"name": "Early bed", "metric": "sleep"})
    out = d("get_life_timeline", {})
    assert out.startswith("Your timeline, 2026-10-07 to 2026-10-13")
    for piece in ("Finished task: File taxes", "Finished book 'Dune'", "Life wheel check-in, average 7.0/10",
                  "Received: Quote from Sam", "Experiment started: Early bed on sleep", "Logged: mood 7.0, sleep 6.5"):
        assert piece in out, piece
    assert out.index("Tue 13 Oct (today)") < out.index("Mon 12 Oct (yesterday)")


def test_kinds_filter_window_and_isolation(planner, monkeypatch):
    import timeline
    d = planner.dispatch_tool
    d("add_task", {"text": "A"})
    d("complete_task", {"task": "A"})
    d("add_library_item", {"title": "Dune", "status": "done"})
    only = d("get_life_timeline", {"kinds": "library"})
    assert "Dune" in only and "Finished task" not in only
    assert "Finished task" in d("get_life_timeline", {"kinds": ["tasks"]})
    monkeypatch.setitem(timeline.SOURCES, "tasks", lambda a, b: 1 / 0)
    out = d("get_life_timeline", {})
    assert "Could not read: tasks." in out and "Dune" in out


def test_line_cap_and_damaged_rows(planner):
    import storage, timeline
    storage.save_tasks([{"done": True, "done_date": "2026-10-13", "text": f"t{i}", "id": str(i)} for i in range(130)]
                       + [{"done": True, "done_date": "bad"}, "x"])
    out = planner.dispatch_tool("get_life_timeline", {"kinds": "tasks"})
    assert "130 events" in out and "...and 10 older events" in out
