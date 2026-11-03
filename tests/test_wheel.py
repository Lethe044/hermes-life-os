"""Life wheel."""

from __future__ import annotations

from datetime import datetime


def test_log_and_show(planner):
    d = planner.dispatch_tool
    out = d("log_life_wheel", {"scores": {"health": 8, "money": 3}})
    assert "health" in out and "#" * 8 + ".." in out and "Needs attention: money" in out
    assert "not rated" in out


def test_bad_scores(planner):
    d = planner.dispatch_tool
    assert "not one of the areas" in d("log_life_wheel", {"scores": {"luck": 5}})
    assert "from 1 to 10" in d("log_life_wheel", {"scores": {"health": 11}})
    assert "from 1 to 10" in d("log_life_wheel", {"scores": {"health": True}})
    assert d("log_life_wheel", {"scores": {}}).startswith("Check-in not saved:")
    assert d("log_life_wheel", {}).startswith("Check-in not saved:")


def test_same_day_merges_and_change_is_shown(planner):
    import wheel
    d = planner.dispatch_tool
    d("log_life_wheel", {"scores": {"health": 5}})
    d("log_life_wheel", {"scores": {"money": 6}, "note": "later"})
    assert len(wheel.checkins()) == 1 and wheel.checkins()[0]["scores"] == {"health": 5, "money": 6}
    planner.set_now(datetime(2026, 11, 20, 9, 0))
    out = d("log_life_wheel", {"scores": {"health": 7, "money": 4}})
    assert "(+2 since 2026-10-13)" in out and "(-2 since 2026-10-13)" in out
    assert "Overall flat" in out or "Overall" in out
    assert "History (2 check-ins" in d("get_life_wheel", {"history": True})


def test_nudge_after_35_days(planner):
    import wheel
    assert wheel.nudges() == []
    planner.dispatch_tool("log_life_wheel", {"scores": {"health": 5}})
    planner.set_now(datetime(2026, 11, 10, 9, 0))
    assert wheel.nudges() == []
    planner.set_now(datetime(2026, 11, 20, 9, 0))
    assert "38 days" in wheel.nudges()[0]


def test_delete_by_date(planner):
    d = planner.dispatch_tool
    d("log_life_wheel", {"scores": {"health": 5}})
    assert "Deleted the check-in from 2026-10-13" in d("delete_wheel_checkin", {"checkin": "2026-10-13"})
    assert d("get_life_wheel", {}).startswith("No life wheel check-in yet")
    assert d("delete_wheel_checkin", {"checkin": "nope"}).startswith("Check-in not deleted:")


def test_unreadable_rows_are_ignored(planner):
    import storage, wheel
    storage.save_wheel([{"date": "2026-10-01", "scores": "bad"}, 5])
    assert wheel.checkins() == [] and wheel.days_since_last() is None
    assert planner.dispatch_tool("get_life_wheel", {}).startswith("No life wheel")
