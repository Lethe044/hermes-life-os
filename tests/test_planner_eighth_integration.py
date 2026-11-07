"""Inbox and weekly review together with the shared systems."""

from __future__ import annotations

import pytest

STORES = ["inbox", "reviews"]
NEW_TOOLS = ["add_to_inbox", "get_inbox", "process_inbox_item", "delete_inbox_item", "start_weekly_review",
             "save_weekly_review", "get_weekly_reviews", "delete_weekly_review"]


def seed(p):
    d = p.dispatch_tool
    d("add_to_inbox", {"text": "learn the cello"})
    d("save_weekly_review", {"wins": "finished the cello plan", "focus": ["practise scales"]})


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
        assert data["inbox"][0]["text"] == "learn the cello" and data["reviews"][0]["focus"] == ["practise scales"]

    def test_profiles_are_separate(self, planner):
        import storage
        seed(planner)
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("get_inbox", {}).startswith("Your inbox is empty")
            assert planner.dispatch_tool("get_weekly_reviews", {}).startswith("No weekly reviews")
        finally:
            storage.set_active_profile(None)
        assert "cello" in planner.dispatch_tool("get_inbox", {})

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
        assert isinstance(d(tool, {"item": 5, "text": {}, "as": [], "wins": 3, "focus": 9, "rating": "x", "review": 1,
                                   "limit": "x", "create_tasks": 4, "due": 3, "tags": 5}), str)

    def test_schemas_are_wired(self, planner):
        import planner_schemas as ps
        names = {s["function"]["name"] for s in ps.PLANNER_SCHEMAS}
        assert set(NEW_TOOLS) <= names and all(t in ps.TOOL_MODULES for t in NEW_TOOLS)

    def test_deletes_are_recoverable(self, planner):
        d = planner.dispatch_tool
        seed(planner)
        d("delete_inbox_item", {"item": "cello"})
        d("delete_weekly_review", {"review": "2026-10-12"})
        assert "cello" in d("get_trash", {})
        assert d("restore_deleted", {"item": "learn the cello"}).startswith("Restored")
        assert "cello" in d("get_inbox", {})


class TestSharedSystems:
    def test_search_finds_them(self, planner):
        seed(planner)
        d = planner.dispatch_tool
        assert "cello" in d("search_everything", {"query": "cello"})
        assert "scales" in d("search_everything", {"query": "scales"})

    def test_agenda_shows_the_inbox(self, planner):
        seed(planner)
        assert "Inbox:" in planner.dispatch_tool("get_today_agenda", {})

    def test_failures_are_isolated(self, planner, monkeypatch):
        import inbox, nudges
        monkeypatch.setattr(inbox, "agenda_lines", lambda: 1 / 0)
        monkeypatch.setattr(inbox, "nudges", lambda n=1: 1 / 0)
        assert isinstance(planner.dispatch_tool("get_today_agenda", {}), str)
        assert isinstance(nudges._planner_nudges(), list)

    def test_review_facts_survive_a_broken_source(self, planner, monkeypatch):
        import wheel, weekly_review
        monkeypatch.setattr(wheel, "checkins", lambda: 1 / 0)
        assert "Weekly review for the week" in weekly_review.start_text()


class TestDoctor:
    def test_clean_data_has_no_warnings(self, planner):
        import doctor
        seed(planner)
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"] == []

    @pytest.mark.parametrize("store,row", [
        ("inbox", {"id": "i1", "text": "", "added": "2026-10-13"}),
        ("inbox", {"id": "i2", "text": "x", "added": "nope"}),
        ("reviews", {"id": "r1", "week": "nope"}),
        ("reviews", {"id": "r2", "week": "2026-10-12", "rating": 9}),
        ("reviews", {"id": "r3", "week": "2026-10-12", "focus": "text"}),
    ])
    def test_problems_are_reported_and_have_a_repair_hint(self, planner, store, row):
        import doctor, storage
        storage.save_store(store, [row])
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"]
        assert row["id"] in planner.dispatch_tool("get_repair_suggestions", {})
