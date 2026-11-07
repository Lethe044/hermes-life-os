"""Projects."""

from __future__ import annotations

from datetime import datetime


def test_add_validate_and_unique(planner):
    d = planner.dispatch_tool
    out = d("add_project", {"name": "Launch website", "outcome": "Live", "due": "2026-11-01"})
    assert out.startswith("Project added: Launch website (active)") and "#launch-website" in out
    assert "already exists" in d("add_project", {"name": "launch WEBSITE"})
    assert "belongs to another project" in d("add_project", {"name": "Other", "tag": "launch-website"})
    assert d("add_project", {"name": ""}).startswith("Project not added:")
    assert d("add_project", {"name": "X", "due": "someday"}).startswith("Project not added:")
    assert d("add_project", {"name": "Y", "tag": "two words"}).startswith("Project not added:")


def test_progress_and_next_action(planner):
    d = planner.dispatch_tool
    d("add_project", {"name": "Trip plan"})
    d("add_project_task", {"project": "trip", "text": "Book flights", "due": "2026-10-20"})
    d("add_project_task", {"project": "trip", "text": "Book hotel", "due": "2026-10-15", "priority": "high"})
    d("add_project_task", {"project": "trip", "text": "Pack"})
    d("complete_task", {"task": "pack"})
    out = d("get_project", {"project": "trip"})
    assert "33%" in out and "1/3 tasks" in out and "Next action: Book hotel (due 2026-10-15)" in out
    assert "no next action" not in d("get_projects", {})


def test_stuck_overdue_and_nudges(planner):
    import projects
    d = planner.dispatch_tool
    d("add_project", {"name": "Empty"})
    assert "[no next action]" in d("get_projects", {}) and "no open task" in projects.nudges()[0]
    d("add_project_task", {"project": "empty", "text": "x"})
    assert projects.nudges() == []
    d("update_project", {"project": "empty", "fields": {"due": "2026-10-13"}})
    planner.set_now(datetime(2026, 10, 20, 9, 0))
    assert "[overdue]" in d("get_projects", {}) and "was due 2026-10-13" in projects.nudges()[0]
    d("update_project", {"project": "empty", "fields": {"status": "paused"}})
    assert projects.nudges() == []


def test_update_status_done_blocks_new_tasks(planner):
    d = planner.dispatch_tool
    d("add_project", {"name": "Alpha"})
    d("add_project", {"name": "Beta"})
    assert "(done)" in d("update_project", {"project": "alpha", "fields": {"status": "done"}})
    assert "is done" in d("add_project_task", {"project": "alpha", "text": "more"})
    assert "status must be" in d("update_project", {"project": "beta", "fields": {"status": "stuck"}})
    assert "already exists" in d("update_project", {"project": "beta", "fields": {"name": "Alpha"}})
    assert d("update_project", {"project": "beta", "fields": {"colour": 1}}).startswith("Project not changed:")
    assert d("get_projects", {"status": "done"}).count("\n") == 1
    assert d("get_projects", {"status": "weird"}).startswith("Cannot show projects:")


def test_agenda_and_delete_keep_tasks(planner):
    import projects, tasks
    d = planner.dispatch_tool
    d("add_project", {"name": "Garden"})
    d("add_project_task", {"project": "garden", "text": "Buy soil", "due": "today"})
    assert projects.agenda_lines() == ["Garden: Buy soil"]
    assert "Its tasks are still there" in d("delete_project", {"project": "garden"})
    assert len(tasks.list_tasks("open")) == 1
    assert d("get_projects", {}).startswith("No projects yet")


def test_damaged_rows(planner):
    import projects, storage
    storage.save_projects([{"name": "x", "status": "weird", "tag": "x"}, 5, {"id": "a", "name": "ok", "status": "active", "tag": "ok"}])
    assert [p["name"] for p in projects.listing()] == ["ok"]
