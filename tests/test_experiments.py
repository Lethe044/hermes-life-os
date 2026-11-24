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


def corr(a, b, r, n=14):
    return {"metric_a": a, "metric_b": b, "r": r, "n_days": n, "strength": "strong", "direction": "positive" if r > 0 else "negative",
            "note": "x"}


def test_ideas_follow_the_direction_that_helps(planner, monkeypatch):
    import experiments
    monkeypatch.setattr(experiments, "_correlations", lambda: [
        corr("hydration", "mood", 0.7),          # more water helps mood
        corr("caffeine", "sleep", -0.6),         # less caffeine helps sleep
        corr("meeting_hours", "stress", 0.5),    # fewer meetings, less stress
        corr("mood", "stress", -0.9),            # neither is a lever
        corr("hydration", "stress", 0.5),        # more water would raise stress: no idea
        corr("meeting_hours", "mood", 0.5),      # would need more meetings: no idea
    ])
    got = experiments.ideas(10)
    assert [(g["lever"], g["metric"]) for g in got] == [("hydration", "mood"), ("caffeine", "sleep"), ("meeting_hours", "stress")]
    assert got[0]["change"] == "Drink more water through the day" and "Cut back on caffeine" in got[1]["change"]
    out = planner.dispatch_tool("suggest_experiment", {"limit": 2})
    assert out.startswith("2 experiment ideas from your own data:") and "start_experiment name=" in out and "not proof" in out


def test_ideas_skip_busy_metrics_and_handle_no_data(planner, monkeypatch):
    import experiments
    monkeypatch.setattr(experiments, "_correlations", lambda: [corr("hydration", "mood", 0.7)])
    planner.dispatch_tool("start_experiment", {"name": "Walks", "metric": "mood"})
    assert experiments.ideas() == []
    assert planner.dispatch_tool("suggest_experiment", {}).startswith("No clear pattern to test yet")
    for bad in (0, 11, "x", True):
        assert planner.dispatch_tool("suggest_experiment", {"limit": bad}).startswith("No idea:")


def test_ideas_use_the_real_journal(planner):
    import experiments, storage
    from datetime import datetime, timedelta
    for k in range(10):
        ts = (datetime.utcnow() - timedelta(days=k + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        storage.write_memory({"type": "hydration", "amount_ml": 500 + 200 * k, "content": "w", "timestamp": ts})
        storage.write_memory({"type": "mood", "score": 3 + k % 7 if False else 3 + k * 0.5, "content": "m", "timestamp": ts})
    assert isinstance(experiments.ideas(), list)
