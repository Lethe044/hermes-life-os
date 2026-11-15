"""Shared metric helpers."""

from __future__ import annotations

import pytest


def test_check_metric(planner):
    import metricseries as ms
    assert ms.check_metric(" Social Quality ") == "social_quality" and ms.check_metric("overdue_tasks") == "overdue_tasks"
    for bad in ("x", None, 3, "overdue_tasks_"):
        with pytest.raises(ValueError):
            ms.check_metric(bad)
    with pytest.raises(ValueError):
        ms.check_metric("open_tasks", allow_state=False)


def test_values_and_day_minus(planner):
    import metricseries as ms
    daily = {"2026-10-10": {"mood": 5.0}, "2026-10-11": {"sleep": 7.0}, "2026-10-12": {"mood": 6.0}, "2026-10-20": {"mood": 9.0}}
    assert ms.values(daily, "mood", "2026-10-10", "2026-10-13") == {"2026-10-10": 5.0, "2026-10-12": 6.0}
    assert ms.day_minus("2026-10-01", 1) == "2026-09-30"


def test_load_daily_reads_the_journal(planner):
    import metricseries as ms, storage
    from datetime import datetime, timedelta
    ts = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    storage.write_memory({"type": "mood", "score": 6, "content": "ok", "timestamp": ts})
    storage.write_memory({"type": "mood", "score": 8, "content": "ok", "timestamp": ts})
    assert list(ms.load_daily().values()) == [{"mood": 7.0}]


def test_state_values(planner):
    import metricseries as ms
    d = planner.dispatch_tool
    d("add_task", {"text": "old", "due": "2026-10-01"})
    d("add_task", {"text": "new"})
    d("add_to_inbox", {"text": "idea"})
    d("add_waiting", {"what": "x", "follow_up": "today"})
    assert ms.state_value("overdue_tasks") == 1 and ms.state_value("open_tasks") == 2
    assert ms.state_value("inbox_items") == 1 and ms.state_value("overdue_follow_ups") == 0
    assert ms.state_value("mood") is None
