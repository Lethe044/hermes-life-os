"""Weekly review."""

from __future__ import annotations

from datetime import datetime


def test_start_shows_facts_and_questions(planner):
    d = planner.dispatch_tool
    d("add_task", {"text": "Ship it"})
    d("complete_task", {"task": "ship"})
    d("add_task", {"text": "Late thing", "due": "2026-10-10"})
    d("add_to_inbox", {"text": "idea"})
    d("log_life_wheel", {"scores": {"money": 3, "health": 8}})
    out = d("start_weekly_review", {})
    assert "week of 2026-10-12" in out and "Tasks finished: 1 (e.g. Ship it)" in out
    assert "Overdue: 1" in out and "Inbox: 1 unsorted item" in out and "lowest: money" in out
    assert "1. What went well" in out and "3. What are the up to five" in out


def test_save_replace_and_list(planner):
    d = planner.dispatch_tool
    assert "saved for the week of 2026-10-12" in d("save_weekly_review", {"wins": "shipped", "rating": 4})
    d("save_weekly_review", {"wins": "shipped more", "lessons": "sleep", "focus": ["a", "b"], "rating": 5})
    import weekly_review
    assert len(weekly_review.reviews()) == 1
    out = d("get_weekly_reviews", {})
    assert "rated 5/5" in out and "Wins: shipped more" in out and "Focus: a, b" in out
    assert "already saved" in d("start_weekly_review", {})


def test_focus_becomes_tasks_next_monday(planner):
    d = planner.dispatch_tool
    out = d("save_weekly_review", {"focus": "plan trip; call bank", "create_tasks": True})
    assert "Created 2 tasks due next Monday" in out
    import tasks
    assert {t["due"] for t in tasks.list_tasks("open")} == {"2026-10-19"}


def test_validation(planner):
    d = planner.dispatch_tool
    assert d("save_weekly_review", {}).startswith("Review not saved:")
    assert "from 1 to 5" in d("save_weekly_review", {"rating": 6})
    assert "at most 5" in d("save_weekly_review", {"focus": list("abcdef")})
    assert d("save_weekly_review", {"wins": "x", "create_tasks": "yes"}).startswith("Review not saved:")
    assert d("get_weekly_reviews", {"limit": 0}).startswith("Cannot show reviews:")


def test_nudge_only_late_in_the_week_and_after_first_review(planner):
    import weekly_review
    assert weekly_review.nudges() == []
    planner.dispatch_tool("save_weekly_review", {"wins": "ok"})
    planner.set_now(datetime(2026, 10, 16, 9, 0))   # Friday, same week already reviewed
    assert weekly_review.nudges() == []
    planner.set_now(datetime(2026, 10, 23, 9, 0))   # next Friday, not reviewed yet
    assert "weekly review" in weekly_review.nudges()[0]
    planner.set_now(datetime(2026, 10, 21, 9, 0))   # Wednesday
    assert weekly_review.nudges() == []


def test_previous_focus_is_recalled_and_delete(planner):
    d = planner.dispatch_tool
    d("save_weekly_review", {"focus": ["finish deck"]})
    planner.set_now(datetime(2026, 10, 20, 9, 0))
    assert "Last week you wanted to focus on: finish deck" in d("start_weekly_review", {})
    assert "Deleted the review for the week of 2026-10-12" in d("delete_weekly_review", {"review": "2026-10-12"})
    assert d("delete_weekly_review", {"review": "nope"}).startswith("Review not deleted:")
