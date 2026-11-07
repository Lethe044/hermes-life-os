"""Projects and the waiting list together with the shared systems."""

from __future__ import annotations

import pytest

STORES = ["projects", "waiting"]
NEW_TOOLS = ["add_project", "get_projects", "get_project", "update_project", "add_project_task", "delete_project",
             "add_waiting", "get_waiting", "chase_waiting", "resolve_waiting", "delete_waiting"]


def seed(p):
    d = p.dispatch_tool
    d("add_project", {"name": "Kitchen remodel", "outcome": "New cabinets installed"})
    d("add_waiting", {"what": "Cabinet quote", "who": "Marta", "follow_up": "today"})


class TestRegistry:
    @pytest.mark.parametrize("store", STORES)
    def test_registered(self, planner, store):
        import storage
        assert store in storage.DATA_STORES and storage.data_store_path(store).name == f"{store}.json"
        assert storage.load_store(store) == []

    def test_export_contains_them(self, planner):
        import data_export
        seed(planner)
        data = data_export.build_backup_payload()
        assert data["projects"][0]["tag"] == "kitchen-remodel" and data["waiting"][0]["who"] == "Marta"

    def test_profiles_are_separate(self, planner):
        import storage
        seed(planner)
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("get_projects", {}).startswith("No projects")
            assert planner.dispatch_tool("get_waiting", {}).startswith("You are not waiting")
        finally:
            storage.set_active_profile(None)
        assert "Kitchen" in planner.dispatch_tool("get_projects", {})

    def test_backup_and_restore_round_trip(self, planner):
        import backup, restore, storage
        seed(planner)
        path = backup.run_backup()
        before = {s: storage.load_store(s) for s in STORES}
        for s in STORES:
            storage.save_store(s, [])
        restore.restore_backup(path)
        assert {s: storage.load_store(s) for s in STORES} == before and all(before.values())


class TestDispatch:
    @pytest.mark.parametrize("tool", NEW_TOOLS)
    def test_empty_and_junk_input_never_raise(self, planner, tool):
        d = planner.dispatch_tool
        assert isinstance(d(tool, {}), str)
        assert isinstance(d(tool, {"name": 5, "project": [], "fields": "x", "text": {}, "what": 3, "who": [], "item": 2,
                                   "days": "x", "follow_up": 4, "status": 1, "due": 3, "tag": 5}), str)

    def test_schemas_are_wired(self, planner):
        import planner_schemas as ps
        names = {s["function"]["name"] for s in ps.PLANNER_SCHEMAS}
        assert set(NEW_TOOLS) <= names and all(t in ps.TOOL_MODULES for t in NEW_TOOLS)

    def test_deletes_are_recoverable(self, planner):
        d = planner.dispatch_tool
        seed(planner)
        d("delete_project", {"project": "kitchen"})
        d("delete_waiting", {"item": "cabinet"})
        out = d("get_trash", {})
        assert "Kitchen remodel" in out and "Cabinet quote" in out
        assert d("restore_deleted", {"item": "Cabinet quote"}).startswith("Restored")
        assert "Cabinet quote" in d("get_waiting", {})


class TestSharedSystems:
    def test_search_finds_them(self, planner):
        seed(planner)
        d = planner.dispatch_tool
        assert "Kitchen remodel" in d("search_everything", {"query": "cabinets"})
        assert "Cabinet quote" in d("search_everything", {"query": "marta"})

    def test_agenda_shows_follow_ups(self, planner):
        seed(planner)
        assert "Follow up on:" in planner.dispatch_tool("get_today_agenda", {})

    def test_failures_are_isolated(self, planner, monkeypatch):
        import nudges, projects, waiting
        monkeypatch.setattr(projects, "agenda_lines", lambda: 1 / 0)
        monkeypatch.setattr(waiting, "agenda_lines", lambda: 1 / 0)
        monkeypatch.setattr(projects, "nudges", lambda n=1: 1 / 0)
        monkeypatch.setattr(waiting, "nudges", lambda n=1: 1 / 0)
        assert isinstance(planner.dispatch_tool("get_today_agenda", {}), str)
        assert isinstance(nudges._planner_nudges(), list)


class TestDoctor:
    def test_clean_data_has_no_warnings(self, planner):
        import doctor
        seed(planner)
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"] == []

    @pytest.mark.parametrize("store,row", [
        ("projects", {"id": "p1", "name": "", "status": "active", "tag": "x"}),
        ("projects", {"id": "p2", "name": "x", "status": "stuck", "tag": "x"}),
        ("waiting", {"id": "w1", "what": "", "chase": "2026-10-13"}),
        ("waiting", {"id": "w2", "what": "x", "chase": "nope"}),
    ])
    def test_problems_are_reported_and_have_a_repair_hint(self, planner, store, row):
        import doctor, storage
        storage.save_store(store, [row])
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"]
        assert row["id"] in planner.dispatch_tool("get_repair_suggestions", {})
