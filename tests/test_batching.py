"""Task batching."""

from __future__ import annotations


def seed(d):
    d("add_task", {"text": "Call dentist", "tags": ["calls"], "minutes": 10})
    d("add_task", {"text": "Call bank", "tags": ["calls", "money"]})
    d("add_task", {"text": "Call mum", "tags": "calls"})
    d("add_task", {"text": "Buy stamps", "tags": ["errands"]})
    d("add_task", {"text": "Pay bill", "tags": ["money"], "minutes": 20})
    d("add_task", {"text": "Done call", "tags": ["calls"]})
    d("complete_task", {"task": "Done call"})


def test_empty(planner):
    assert planner.dispatch_tool("batch_tasks", {}).startswith("No batches yet")


def test_lists_batches_with_two_or_more(planner):
    seed(planner.dispatch_tool)
    out = planner.dispatch_tool("batch_tasks", {})
    assert out.startswith("2 batches of open tasks")
    assert "#calls: 3 tasks, about 40m: Call dentist, Call bank, Call mum" in out
    assert "#money: 2 tasks, about 35m" in out and "errands" not in out


def test_single_tag_view_shows_even_one_task(planner):
    seed(planner.dispatch_tool)
    assert "#errands: 1 task" in planner.dispatch_tool("batch_tasks", {"tag": "#errands"})
    assert planner.dispatch_tool("batch_tasks", {"tag": "nothing"}).startswith("No batches yet")
    assert planner.dispatch_tool("batch_tasks", {"tag": "a b"}).startswith("Cannot batch: give one tag")


def test_apply_blocks_the_first_fitting_gap(planner):
    import timeblocks
    d = planner.dispatch_tool
    seed(d)
    d("add_time_block", {"title": "Standup", "start": "09:00", "end": "09:30", "date": "2026-10-14"})
    out = d("batch_tasks", {"tag": "calls", "apply": True, "date": "2026-10-14"})
    assert out == "Batch blocked: Batch: #calls on 2026-10-14 07:00-07:40 (40m) for 3 tasks."
    block = [b for b in timeblocks.day_plan("2026-10-14")["blocks"] if b["title"] == "Batch: #calls"][0]
    assert block["notes"] == "Call dentist; Call bank; Call mum" and block["category"] == "task"


def test_apply_errors(planner):
    d = planner.dispatch_tool
    seed(d)
    assert d("batch_tasks", {"apply": True}).startswith("Cannot batch: say which tag")
    assert d("batch_tasks", {"apply": True, "tag": "ghost"}).startswith("Cannot batch: no open task has that tag")
    assert d("batch_tasks", {"apply": "yes"}).startswith("Cannot batch:")
    d("add_time_block", {"title": "All day", "start": "07:00", "end": "22:00", "date": "2026-10-14"})
    assert d("batch_tasks", {"tag": "calls", "apply": True, "date": "2026-10-14"}).startswith("Cannot batch: no free gap")
    assert d("batch_tasks", {"tag": "calls", "apply": True, "date": "nonsense"}).startswith("Cannot batch:")


def test_long_notes_are_trimmed(planner):
    import timeblocks
    d = planner.dispatch_tool
    for i in range(12):
        d("add_task", {"text": f"Phone person number {i} about something", "tags": ["calls"], "minutes": 5})
    d("batch_tasks", {"tag": "calls", "apply": True, "date": "2026-10-14"})
    note = [b for b in timeblocks.day_plan("2026-10-14")["blocks"]][0]["notes"]
    assert len(note) <= timeblocks.MAX_NOTES and note.endswith("...")
