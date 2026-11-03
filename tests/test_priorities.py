"""Daily priorities (Big 3)."""

from __future__ import annotations

from datetime import datetime


def test_limit_of_three_and_duplicates(planner):
    d = planner.dispatch_tool
    for t in ("a one", "b two", "c three"):
        assert d("add_priority", {"text": t}).startswith("Priority added")
    assert "already has 3" in d("add_priority", {"text": "d four"})
    assert "0/3 done" in d("get_priorities", {})


def test_duplicate_text_rejected(planner):
    d = planner.dispatch_tool
    d("add_priority", {"text": "Write"})
    assert "already a priority" in d("add_priority", {"text": "write"})


def test_needs_something(planner):
    assert planner.dispatch_tool("add_priority", {}).startswith("Priority not added:")
    assert "no open task" in planner.dispatch_tool("add_priority", {"task": "nothing"})


def test_linked_task_completes_with_priority(planner):
    d = planner.dispatch_tool
    d("add_task", {"text": "File taxes"})
    d("add_priority", {"task": "taxes"})
    assert "linked task is done too" in d("complete_priority", {"priority": "taxes"})
    assert "Already done" in d("complete_priority", {"priority": "taxes"})
    import tasks
    assert tasks.list_tasks("open") == []


def test_carry_over_and_room(planner):
    d = planner.dispatch_tool
    import priorities
    priorities.add_priority("old one", None, "2026-10-12")
    priorities.add_priority("old two", None, "2026-10-12")
    d("add_priority", {"text": "today a"})
    d("add_priority", {"text": "today b"})
    out = d("carry_over_priorities", {})
    assert "Carried 1 priority" in out and "No room for: old two" in out
    assert "Nothing to carry over" in d("carry_over_priorities", {"from_date": "2026-09-01"})


def test_streak(planner):
    import priorities
    for day in ("2026-10-11", "2026-10-12"):
        row = priorities.add_priority("x " + day, None, day)
        priorities.complete_priority(row["id"])
    assert priorities.streak() == 2
    assert "Streak: 2 days" in planner.dispatch_tool("get_priorities", {"date": "2026-10-12"})


def test_nudge_only_in_the_afternoon(planner):
    import priorities
    priorities.add_priority("Finish deck")
    assert priorities.nudges() == []
    planner.set_now(datetime(2026, 10, 13, 16, 0))
    assert "Finish deck" in priorities.nudges()[0]
    assert priorities.agenda_lines() == ["Finish deck"]


def test_old_entries_are_dropped_and_ids_assigned(planner):
    import priorities, storage
    storage.save_priorities([{"date": "2025-01-01", "text": "ancient", "done": False}, "junk"])
    assert len(priorities._load()) == 2 and priorities._load()[0]["id"]
    priorities.add_priority("fresh")
    assert [r["text"] for r in storage.load_priorities() if isinstance(r, dict)] == ["fresh"]


def test_bad_date_and_junk(planner):
    d = planner.dispatch_tool
    assert "couldn't understand the date" in d("add_priority", {"text": "x", "date": "someday"})
    assert d("get_priorities", {"date": 5}).startswith("Cannot show priorities:")
    assert d("delete_priority", {"priority": "zzz"}).startswith("Priority not deleted:")
