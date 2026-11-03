"""plan_my_day."""

from __future__ import annotations

from datetime import datetime


def test_nothing_to_plan(planner):
    assert planner.dispatch_tool("plan_my_day", {}).startswith("Nothing to schedule for 2026-10-13")


def test_dry_run_saves_nothing_and_apply_saves(planner):
    import timeblocks
    d = planner.dispatch_tool
    d("add_task", {"text": "Write report", "due": "today", "priority": "high", "minutes": 90})
    d("add_task", {"text": "Email Sam", "due": "today", "minutes": 15})
    out = d("plan_my_day", {})
    assert "proposal" in out and "09:00-10:30 Write report" in out and "10:35-10:50 Email Sam" in out
    assert timeblocks.day_plan("2026-10-13")["blocks"] == []
    out = d("plan_my_day", {"apply": True})
    assert "saved as time blocks" in out
    blocks = timeblocks.day_plan("2026-10-13")["blocks"]
    assert [b["title"] for b in blocks] == ["Write report", "Email Sam"] and all(b["task_id"] for b in blocks)
    assert d("plan_my_day", {}).startswith("Nothing to schedule")


def test_priorities_first_and_free_text_priority(planner):
    d = planner.dispatch_tool
    d("add_task", {"text": "Low thing", "due": "today"})
    d("add_priority", {"text": "Call mum"})
    out = d("plan_my_day", {}).splitlines()
    assert "Call mum (priority" in out[1] and "Low thing (due" in out[2]
    d("plan_my_day", {"apply": True})
    assert d("plan_my_day", {}).startswith("Nothing to schedule")


def test_overdue_before_due_and_respects_existing_blocks_and_now(planner):
    d = planner.dispatch_tool
    d("add_task", {"text": "Due today", "due": "today", "minutes": 30})
    d("add_task", {"text": "Late one", "due": "2026-10-10", "minutes": 30})
    d("add_time_block", {"title": "Meeting", "start": "09:00", "end": "10:00"})
    planner.set_now(datetime(2026, 10, 13, 9, 7))
    out = d("plan_my_day", {})
    assert "10:00-10:30 Late one (overdue" in out and "10:35-11:05 Due today" in out


def test_things_that_do_not_fit(planner):
    d = planner.dispatch_tool
    d("add_task", {"text": "Huge", "due": "today", "minutes": 480})
    d("add_time_block", {"title": "Workshop", "start": "07:00", "end": "20:00"})
    out = d("plan_my_day", {})
    assert "Did not fit:" in out and "Huge" in out


def test_validation(planner):
    d = planner.dispatch_tool
    assert "max_tasks" in d("plan_my_day", {"max_tasks": 0})
    assert "default_minutes" in d("plan_my_day", {"default_minutes": 1})
    assert d("plan_my_day", {"apply": "yes"}).startswith("Cannot plan the day:")
    assert d("plan_my_day", {"date": "garbage"}).startswith("Cannot plan the day:")
    assert "minutes must be" in d("add_task", {"text": "x", "minutes": 3})


def test_minutes_on_tasks(planner):
    d = planner.dispatch_tool
    d("add_task", {"text": "Study"})
    assert "~45 min" in d("update_task", {"task": "study", "fields": {"minutes": 45}})
    assert "~" not in d("update_task", {"task": "study", "fields": {"minutes": ""}})
