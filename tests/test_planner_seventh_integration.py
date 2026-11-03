"""Priorities, plan my day, life wheel, library and calendar export together with the shared systems."""

from __future__ import annotations

from datetime import datetime

import pytest

STORES = ["priorities", "wheel", "library"]
NEW_TOOLS = ["add_priority", "get_priorities", "complete_priority", "carry_over_priorities", "delete_priority",
             "plan_my_day", "log_life_wheel", "get_life_wheel", "delete_wheel_checkin", "add_library_item",
             "get_library", "update_library_item", "finish_library_item", "suggest_library_item",
             "get_library_stats", "delete_library_item", "export_calendar"]


def seed(p):
    d = p.dispatch_tool
    d("add_priority", {"text": "Ship the release"})
    d("log_life_wheel", {"scores": {"health": 6, "money": 3}})
    d("add_library_item", {"title": "Dune", "creator": "Frank Herbert"})


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
        assert data["priorities"][0]["text"] == "Ship the release" and data["wheel"][0]["scores"]["money"] == 3
        assert data["library"][0]["title"] == "Dune"

    def test_profiles_are_separate(self, planner):
        import storage
        seed(planner)
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("get_library", {}).startswith("Your library is empty")
            assert planner.dispatch_tool("get_life_wheel", {}).startswith("No life wheel")
        finally:
            storage.set_active_profile(None)
        assert "Dune" in planner.dispatch_tool("get_library", {})

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
        assert isinstance(d(tool, {"item": 5, "priority": [], "text": {}, "fields": "x", "scores": 3, "checkin": 1,
                                   "days": "x", "sections": 7, "kind": 4, "status": 4, "date": 3}), str)

    def test_schemas_are_wired(self, planner):
        import planner_schemas as ps
        names = {s["function"]["name"] for s in ps.PLANNER_SCHEMAS}
        assert set(NEW_TOOLS) <= names
        for t in NEW_TOOLS:
            assert t in ps.TOOL_MODULES
            schema = next(s for s in ps.PLANNER_SCHEMAS if s["function"]["name"] == t)
            assert len(schema["function"]["description"]) > 10

    def test_deletes_are_recoverable_from_the_trash(self, planner):
        d = planner.dispatch_tool
        seed(planner)
        d("delete_library_item", {"item": "dune"})
        d("delete_priority", {"priority": "ship"})
        d("delete_wheel_checkin", {"checkin": "2026-10-13"})
        out = d("get_trash", {})
        assert "Dune" in out and "Ship the release" in out
        assert d("restore_deleted", {"item": "Dune"}).startswith("Restored")
        assert "Dune" in d("get_library", {})


class TestSharedSystems:
    def test_search_finds_them(self, planner):
        seed(planner)
        d = planner.dispatch_tool
        assert "Dune" in d("search_everything", {"query": "herbert"})
        assert "Ship the release" in d("search_everything", {"query": "release"})

    def test_agenda_and_nudges_show_priorities(self, planner):
        seed(planner)
        assert "Top priorities today:" in planner.dispatch_tool("get_today_agenda", {})
        planner.set_now(datetime(2026, 10, 13, 16, 0))
        import nudges
        assert any("priority still open" in n for n in nudges._planner_nudges())

    def test_closing_lists_open_priorities(self, planner):
        seed(planner)
        assert "priority: Ship the release" in planner.dispatch_tool("get_closing_summary", {})

    def test_agenda_survives_a_broken_module(self, planner, monkeypatch):
        import priorities
        monkeypatch.setattr(priorities, "agenda_lines", lambda: 1 / 0)
        assert isinstance(planner.dispatch_tool("get_today_agenda", {}), str)

    def test_nudges_survive_a_broken_module(self, planner, monkeypatch):
        import nudges, wheel
        monkeypatch.setattr(wheel, "nudges", lambda n=1: 1 / 0)
        assert isinstance(nudges._planner_nudges(), list)


class TestDoctor:
    def test_clean_data_has_no_warnings(self, planner):
        import doctor
        seed(planner)
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"] == []

    @pytest.mark.parametrize("store,row", [
        ("priorities", {"id": "p1", "date": "nope", "text": "x"}),
        ("wheel", {"id": "w1", "date": "2026-10-01", "scores": {"health": 99}}),
        ("wheel", {"id": "w2", "date": "2026-10-01", "scores": {"luck": 5}}),
        ("library", {"id": "l1", "title": "x", "kind": "vinyl", "status": "want"}),
        ("library", {"id": "l2", "title": "x", "kind": "book", "status": "want", "progress": 500}),
    ])
    def test_problems_are_reported_and_have_a_repair_hint(self, planner, store, row):
        import doctor, repair_hints, storage
        storage.save_store(store, [row])
        warns = [f for f in doctor.check_planner_data() if f["level"] == "warn"]
        assert warns
        assert row["id"] in planner.dispatch_tool("get_repair_suggestions", {})

    def test_duplicate_ids_are_found(self, planner):
        import doctor, storage
        storage.save_library([{"id": "same", "title": "a", "kind": "book", "status": "want"},
                              {"id": "same", "title": "b", "kind": "book", "status": "want"}])
        assert any("shared by more than one" in f["message"] for f in doctor.check_planner_data())
