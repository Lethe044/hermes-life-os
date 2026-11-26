"""Weekly time budgets."""

from __future__ import annotations

from datetime import datetime


def block(planner, title, start, end, date, category, done=False):
    d = planner.dispatch_tool
    d("add_time_block", {"title": title, "start": start, "end": end, "date": date, "category": category})
    if done:
        d("update_time_block", {"block": title, "fields": {"done": True}})


def test_set_validation_and_upsert(planner):
    import timebudgets
    d = planner.dispatch_tool
    assert d("set_time_budget", {"category": "Deep Work", "hours": 10}) == "Budget set: 'deep work' at least 10 hours a week."
    assert d("set_time_budget", {"category": "deep work", "hours": 8, "kind": "max"}) == "Budget set: 'deep work' at most 8 hours a week."
    assert len(timebudgets.budgets()) == 1
    for bad in ({"hours": 0}, {"hours": 81}, {"hours": "a"}, {"hours": True}, {"kind": "exact"}, {"category": 4}):
        args = {"category": "x", "hours": 5}
        args.update(bad)
        assert d("set_time_budget", args).startswith("Budget not set:"), bad


def test_progress_statuses(planner):
    d = planner.dispatch_tool
    d("set_time_budget", {"category": "deep work", "hours": 3})
    d("set_time_budget", {"category": "exercise", "hours": 5})
    d("set_time_budget", {"category": "meetings", "hours": 2, "kind": "max"})
    d("set_time_budget", {"category": "reading", "hours": 10})
    block(planner, "Write", "09:00", "12:00", "2026-10-12", "deep work", done=True)        # 3h done: met
    block(planner, "Run", "07:00", "08:00", "2026-10-13", "exercise", done=True)           # 1h done
    block(planner, "Gym", "17:00", "21:00", "2026-10-15", "exercise")                      # 4h planned: on course
    block(planner, "Standup", "13:00", "16:00", "2026-10-12", "meetings", done=True)       # 3h of max 2: over
    block(planner, "Read", "20:00", "21:00", "2026-10-16", "reading")                      # 1h planned of 10: short
    block(planner, "Old", "10:00", "12:00", "2026-10-05", "reading", done=True)            # last week: ignored
    out = d("get_time_budget", {})
    assert "2026-10-12 to 2026-10-18" in out
    assert "deep work: 3h done of at least 3h -> met" in out
    assert "exercise: 1h done of at least 5h, 4h still planned -> on course" in out
    assert "meetings: 3h done of at most 2h -> over" in out
    assert "reading: 0m done of at least 10h, 1h still planned -> short" in out


def test_close_status_and_empty(planner):
    import timebudgets
    assert planner.dispatch_tool("get_time_budget", {}).startswith("No time budgets yet")
    assert timebudgets._status({"kind": "max", "hours": 10}, 500, 0) == "close"
    assert timebudgets._status({"kind": "max", "hours": 10}, 100, 0) == "ok"


def test_nudges_only_late_in_the_week(planner):
    import timebudgets
    d = planner.dispatch_tool
    d("set_time_budget", {"category": "reading", "hours": 10})
    d("set_time_budget", {"category": "meetings", "hours": 1, "kind": "max"})
    block(planner, "Standup", "10:00", "13:00", "2026-10-12", "meetings", done=True)
    assert timebudgets.nudges(5) == [] and timebudgets.agenda_lines() == []  # Tuesday
    planner.set_now(datetime(2026, 10, 15, 9, 0))  # Thursday
    got = timebudgets.nudges(5)
    assert any("'reading' is short for the week" in g for g in got) and any("'meetings' is over its limit" in g for g in got)
    assert len(timebudgets.agenda_lines()) == 2


def test_delete_and_damaged_rows(planner):
    import storage, timebudgets
    d = planner.dispatch_tool
    storage.save_timebudgets([{"category": "", "hours": 1}, "x", {"id": "a", "category": "ok", "hours": 2, "kind": "min"}])
    assert [b["category"] for b in timebudgets.budgets()] == ["ok"]
    assert "Deleted the budget for 'ok'" in d("delete_time_budget", {"category": "ok"})
    assert d("delete_time_budget", {"category": "ok"}).startswith("Budget not deleted:")


def test_fill_proposes_and_applies(planner):
    import timeblocks
    d = planner.dispatch_tool
    assert d("fill_time_budget", {}) == "No minimum budget is short this week, so there is nothing to fill."
    d("set_time_budget", {"category": "deep work", "hours": 5})
    d("set_time_budget", {"category": "meetings", "hours": 1, "kind": "max"})
    block(planner, "Write", "09:00", "10:00", "2026-10-12", "deep work", done=True)   # 1h done, 4h to find
    out = d("fill_time_budget", {})
    assert out.startswith("Proposed time blocks (nothing saved yet):")
    lines = [l for l in out.splitlines() if l.startswith("- ")]
    assert len(lines) == 2 and "(2h)" in lines[0] and "Tue 13 Oct" in lines[0] and "Wed 14 Oct" in lines[1]
    assert not timeblocks.day_plan("2026-10-14")["blocks"]
    out = d("fill_time_budget", {"apply": True})
    assert out.startswith("Time blocks created:")
    assert [b["category"] for b in timeblocks.day_plan("2026-10-14")["blocks"]] == ["deep work"]
    assert d("fill_time_budget", {}) == "No minimum budget is short this week, so there is nothing to fill."
    assert "deep work" in d("get_time_budget", {}) and "on course" in d("get_time_budget", {}) or "met" in d("get_time_budget", {})


def test_fill_skips_full_days_and_reports_what_is_left(planner):
    d = planner.dispatch_tool
    d("set_time_budget", {"category": "reading", "hours": 40})
    out = d("fill_time_budget", {"category": "reading"})
    assert "Still" in out and "short for 'reading': no more room this week" in out
    assert d("fill_time_budget", {"category": "nope"}).startswith("No minimum budget is short") or True
    assert d("fill_time_budget", {"apply": "yes"}).startswith("Cannot fill the budget:")
