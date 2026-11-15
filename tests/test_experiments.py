"""Personal experiments."""

from __future__ import annotations

from datetime import datetime, timedelta


def daily(values):
    """{offset_from_today: value} -> {date: {"sleep": value}} for the frozen 2026-10-13."""
    base = datetime(2026, 10, 13)
    return {(base + timedelta(days=k)).strftime("%Y-%m-%d"): {"sleep": v} for k, v in values.items()}


def feed(planner, monkeypatch, values, metric="sleep"):
    import metricseries
    data = {d: {metric: row["sleep"]} for d, row in daily(values).items()}
    monkeypatch.setattr(metricseries, "load_daily", lambda: data)


def test_start_validation_and_one_per_metric(planner):
    d = planner.dispatch_tool
    assert d("start_experiment", {"name": "Early bed", "metric": "sleep", "days": 7}).startswith("Experiment started: Early bed on sleep, 7 days from 2026-10-13")
    assert "still running on sleep" in d("start_experiment", {"name": "Other", "metric": "sleep"})
    assert "already running" in d("start_experiment", {"name": "early BED", "metric": "mood"})
    assert d("start_experiment", {"name": "x", "metric": "luck"}).startswith("Experiment not started:")
    assert d("start_experiment", {"name": "x", "metric": "mood", "days": 1}).startswith("Experiment not started:")
    assert d("start_experiment", {"name": "x", "metric": "mood", "start": "2027-12-01"}).startswith("Experiment not started:")
    assert d("start_experiment", {"name": "x", "metric": "overdue_tasks"}).startswith("Experiment not started:")


def test_verdicts(planner, monkeypatch):
    import experiments
    d = planner.dispatch_tool
    d("start_experiment", {"name": "Early bed", "metric": "sleep", "days": 7, "baseline_days": 7, "start": "2026-10-07"})
    feed(planner, monkeypatch, {})
    assert "Not enough data yet" in d("get_experiment", {"experiment": "early"})
    vals = {k: 6.0 + (k % 2) * 0.2 for k in range(-13, -6)}
    vals.update({k: 7.5 + (k % 2) * 0.2 for k in range(-6, 1)})
    feed(planner, monkeypatch, vals)
    res = experiments.analyze(experiments._load()[0])
    assert res["verdict"] == "better" and res["strength"] == "large" and res["direction"] == "up"
    out = d("get_experiment", {"experiment": "early"})
    assert "Verdict: better" in out and "hint, not proof" in out
    flat = {k: 7.0 + (k % 2) * 0.2 for k in range(-13, 1)}
    feed(planner, monkeypatch, flat)
    assert experiments.analyze(experiments._load()[0])["verdict"] == "no clear effect"


def test_lower_is_better_for_stress(planner, monkeypatch):
    import experiments, metricseries
    d = planner.dispatch_tool
    d("start_experiment", {"name": "Walks", "metric": "stress", "days": 7, "baseline_days": 7, "start": "2026-10-07"})
    data = {}
    for k in range(-13, 1):
        day = (datetime(2026, 10, 13) + timedelta(days=k)).strftime("%Y-%m-%d")
        data[day] = {"stress": 7.0 + (k % 2) * 0.1 if k < -6 else 4.0 + (k % 2) * 0.1}
    monkeypatch.setattr(metricseries, "load_daily", lambda: data)
    res = experiments.analyze(experiments._load()[0])
    assert res["verdict"] == "better" and res["direction"] == "down"


def test_conclude_and_lists(planner, monkeypatch):
    d = planner.dispatch_tool
    d("start_experiment", {"name": "Early bed", "metric": "sleep", "days": 5, "start": "2026-10-09"})
    feed(planner, monkeypatch, {})
    assert d("get_experiments", {}).startswith("1 experiment:")
    assert d("conclude_experiment", {"experiment": "early", "decision": "maybe"}).startswith("Not concluded:")
    out = d("conclude_experiment", {"experiment": "early", "decision": "keep"})
    assert out.startswith("Concluded.") and "decision: keep" in out
    assert d("conclude_experiment", {"experiment": "early"}).startswith("Not concluded: 'Early bed' is already")
    assert "done" in d("get_experiments", {"status": "done"})
    assert d("get_experiments", {"status": "running"}).startswith("No running")
    assert d("get_experiments", {"status": "x"}).startswith("Cannot list")
    assert "Deleted experiment" in d("delete_experiment", {"experiment": "early"})
    assert d("get_experiments", {}).startswith("No experiments yet")


def test_nudge_and_agenda(planner, monkeypatch):
    import experiments
    d = planner.dispatch_tool
    feed(planner, monkeypatch, {})
    d("start_experiment", {"name": "Early bed", "metric": "sleep", "days": 3, "start": "2026-10-11"})
    assert experiments.nudges() == [] and experiments.agenda_lines() == ["'Early bed' ends today"]
    planner.set_now(datetime(2026, 10, 16, 9, 0))
    assert "ended 3 days ago" in experiments.nudges()[0]
    assert experiments.agenda_lines() == ["'Early bed' is over, conclude it"]


def test_damaged_rows(planner):
    import experiments, storage
    storage.save_experiments([{"name": 3}, "x", {"id": "a", "name": "ok", "metric": "sleep", "status": "running",
                                                   "days": 5, "baseline_days": 5, "start": "2026-10-13"}])
    assert [r["name"] for r in experiments.listing()] == ["ok"]
    assert planner.dispatch_tool("get_experiments", {}).startswith("1 experiment")
