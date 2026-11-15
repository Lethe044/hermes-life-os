"""Estimate accuracy and the calibrated workload forecast."""

from __future__ import annotations


def finish(planner, text, minutes, spent, due=None):
    import storage
    d = planner.dispatch_tool
    args = {"text": text, "minutes": minutes}
    if due:
        args["due"] = due
    d("add_task", args)
    d("complete_task", {"task": text})
    rows = storage.load_focus()
    rows.append({"date": "2026-10-12", "duration": spent, "task": text, "quality": 7, "completed": True, "distractions": 0})
    storage.save_focus(rows)


def test_nothing_yet(planner):
    assert planner.dispatch_tool("get_estimate_accuracy", {}).startswith("No finished task has both an estimate")


def test_factor_needs_three_tasks(planner):
    import estimates
    finish(planner, "Write report", 60, 90)
    finish(planner, "Email Sam", 30, 45)
    out = planner.dispatch_tool("get_estimate_accuracy", {})
    assert "took 1h30" in out and "1.50x" in out and "underestimating" in out and "needs 3 such tasks" in out
    assert estimates.calibration_factor() is None
    finish(planner, "Budget", 60, 90)
    assert estimates.calibration_factor() == 1.5
    assert "scales its numbers" in planner.dispatch_tool("get_estimate_accuracy", {})


def test_matching_ignores_case_open_tasks_and_bad_rows(planner):
    import estimates, storage
    planner.dispatch_tool("add_task", {"text": "Open one", "minutes": 30})
    finish(planner, "Plan trip", 40, 40)
    rows = storage.load_focus()
    rows += [{"task": "plan TRIP", "duration": 20, "date": "2026-10-12"}, {"task": "x", "duration": "a"}, "junk",
             {"task": "Open one", "duration": 99}, {"duration": 10}]
    storage.save_focus(rows)
    got = estimates.accuracy()
    assert got["tasks"] == [{"text": "Plan trip", "estimate": 40, "actual": 60}]


def test_factor_is_clamped_and_overestimates(planner):
    import estimates
    for i in range(3):
        finish(planner, f"Quick {i}", 100, 5)
    assert estimates.accuracy()["factor"] == 0.5
    assert "overestimating" in planner.dispatch_tool("get_estimate_accuracy", {})


def test_workload_uses_the_factor(planner):
    import workload
    for i in range(3):
        finish(planner, f"Done {i}", 60, 120)
    planner.dispatch_tool("add_task", {"text": "Next", "due": "2026-10-14", "minutes": 60})
    on = workload.forecast(3)
    off = workload.forecast(3, calibrate=False)
    assert on["factor"] == 2.0 and on["days"][1]["load"] == 120
    assert off["factor"] is None and off["days"][1]["load"] == 60
    assert "Estimates are scaled by 2.00" in planner.dispatch_tool("get_workload_forecast", {"days": 3})
    assert "scaled" not in planner.dispatch_tool("get_workload_forecast", {"days": 3, "calibrate": False})
    assert planner.dispatch_tool("get_workload_forecast", {"calibrate": "yes"}).startswith("Cannot forecast")
