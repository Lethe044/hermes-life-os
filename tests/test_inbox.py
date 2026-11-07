"""Inbox capture and triage."""

from __future__ import annotations

from datetime import datetime


def test_capture_list_and_duplicates(planner):
    d = planner.dispatch_tool
    assert d("add_to_inbox", {"text": "  buy   a lamp "}).startswith("Captured: buy a lamp")
    assert "already in your inbox" in d("add_to_inbox", {"text": "Buy a lamp"})
    assert d("add_to_inbox", {"text": ""}).startswith("Not captured:")
    assert d("add_to_inbox", {"text": "x" * 301}).startswith("Not captured:")
    out = d("get_inbox", {})
    assert "Inbox: 1 item" in out and "buy a lamp (today)" in out


def test_empty_inbox(planner):
    assert planner.dispatch_tool("get_inbox", {}).startswith("Your inbox is empty")


def test_process_into_each_target(planner):
    d = planner.dispatch_tool
    for t in ("call dentist", "idea about sleep", "Hyperion", "stretch"):
        d("add_to_inbox", {"text": t})
    assert "to task" in d("process_inbox_item", {"item": "dentist", "as": "task", "due": "tomorrow", "minutes": 20})
    assert "to note" in d("process_inbox_item", {"item": "sleep", "as": "note", "tags": ["ideas"]})
    assert "book" in d("process_inbox_item", {"item": "hyperion", "as": "library"})
    assert "priority" in d("process_inbox_item", {"item": "stretch", "as": "priority"})
    import tasks, library, priorities, notes, inbox
    assert tasks.list_tasks("open")[0]["minutes"] == 20 and library.listing()[0]["title"] == "Hyperion"
    assert priorities.open_today()[0]["text"] == "stretch" and notes._load()[0]["text"] == "idea about sleep"
    assert inbox.listing() == []


def test_failed_processing_keeps_the_item(planner):
    d = planner.dispatch_tool
    d("add_to_inbox", {"text": "thing"})
    assert d("process_inbox_item", {"item": "thing", "as": "task", "due": "someday"}).startswith("Item not moved:")
    assert d("process_inbox_item", {"item": "thing", "as": "garden"}).startswith("Item not moved:")
    assert d("process_inbox_item", {"item": "nothing", "as": "task"}).startswith("Item not moved:")
    assert "Inbox: 1 item" in d("get_inbox", {})


def test_nudges_and_agenda(planner):
    import inbox
    assert inbox.nudges() == [] and inbox.agenda_lines() == []
    planner.dispatch_tool("add_to_inbox", {"text": "old idea"})
    assert inbox.nudges() == [] and "1 unsorted item" in inbox.agenda_lines()[0]
    planner.set_now(datetime(2026, 10, 17, 9, 0))
    assert "waited 3+ days" in inbox.nudges()[0]
    for i in range(10):
        planner.dispatch_tool("add_to_inbox", {"text": f"item {i}"})
    assert "holds 11 items" in inbox.nudges()[0]


def test_delete_and_junk_rows(planner):
    import inbox, storage
    d = planner.dispatch_tool
    d("add_to_inbox", {"text": "drop me"})
    assert "Dropped 'drop me'" in d("delete_inbox_item", {"item": "drop"})
    storage.save_inbox([{"text": "no id", "added": "2026-10-13"}, 5])
    assert inbox.listing()[0]["id"] and "Inbox: 1 item" in d("get_inbox", {})
