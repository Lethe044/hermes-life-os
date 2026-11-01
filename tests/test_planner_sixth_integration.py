"""The trash, the recommendation ledger and pinned backups together with the shared systems."""

from __future__ import annotations

import pytest

STORES = ["trash", "recs"]
NEW_TOOLS = ["get_trash", "restore_deleted", "empty_trash", "get_recommendation_history", "mark_recommendation", "pin_backup", "unpin_backup"]
NOT_FILED = {"remove_packing_items", "remove_itinerary_item"}     # parts of an entry, not whole entries


def seed(p):
    d = p.dispatch_tool
    d("add_task", {"text": "Pay rent"})
    d("delete_task", {"task": "rent"})
    import recledger
    recledger.record([{"type": "threshold", "metric": "sleep", "value": 6.0, "message": "Sleep has been low lately."}])


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
        assert data["trash"][0]["label"] == "Pay rent" and data["recs"][0]["metric"] == "sleep"

    def test_profiles_are_separate(self, planner):
        import storage
        seed(planner)
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("get_trash", {}).startswith("The trash is empty")
            assert planner.dispatch_tool("get_recommendation_history", {}).startswith("No open recommendations")
        finally:
            storage.set_active_profile(None)
        assert planner.dispatch_tool("get_trash", {}).startswith("1 deleted item")

    def test_backup_and_restore_round_trip_brings_the_trash_back(self, planner):
        import backup, restore, storage
        seed(planner)
        path = backup.run_backup()
        before = {s: storage.load_store(s) for s in STORES}
        for s in STORES:
            storage.save_store(s, [])
        restore.restore_backup(path)
        assert {s: storage.load_store(s) for s in STORES} == before and all(before.values())
        assert planner.dispatch_tool("restore_deleted", {"item": "rent"}).startswith("Restored 'Pay rent'")

    def test_the_trash_is_never_filed_in_itself(self, planner):
        import trash
        assert not any("trash" in stores for stores in trash.WATCHED.values())


class TestDispatch:
    @pytest.mark.parametrize("name", NEW_TOOLS)
    def test_every_tool_is_dispatched_and_never_raises_on_empty_input(self, planner, name):
        out = planner.dispatch_tool(name, {})
        assert isinstance(out, str) and out and not out.startswith("Unknown")

    @pytest.mark.parametrize("name", NEW_TOOLS)
    def test_every_tool_survives_junk_arguments(self, planner, name):
        junk = {k: [{"x": 1}] for k in ("item", "kind", "older_than_days", "status", "recommendation", "note", "backup")}
        out = planner.dispatch_tool(name, junk)
        assert isinstance(out, str) and out

    def test_schemas_are_wired_to_their_modules(self, planner):
        import planner_schemas as ps
        for schemas, module in ((ps.TRASH_SCHEMAS, "trash"), (ps.RECLEDGER_SCHEMAS, "recledger"), (ps.BACKUP_PIN_SCHEMAS, "backup")):
            for s in schemas:
                assert ps.TOOL_MODULES[s["function"]["name"]] == module
        assert set(NEW_TOOLS) <= set(ps.TOOL_MODULES)

    def test_tool_names_are_unique_and_well_formed(self, planner):
        names = [t["function"]["name"] for t in planner.TOOLS]
        assert len(names) == len(set(names)) and set(NEW_TOOLS) <= set(names)
        for t in planner.TOOLS:
            f = t["function"]
            if f["name"] in NEW_TOOLS:
                assert len(f["description"]) > 10 and set(f["parameters"].get("required", [])) <= set(f["parameters"]["properties"])

    def test_unknown_tool_in_a_module(self, planner):
        import trash, recledger, backup
        for mod in (trash, recledger, backup):
            assert mod.run_tool("nope", {}).startswith("Unknown ")


class TestCoverage:
    def test_every_planner_delete_tool_is_either_watched_or_listed_as_not_filed(self, planner):
        """A new delete_*, remove_* or clear_* tool must be added to trash.WATCHED (or to NOT_FILED here on purpose)."""
        import planner_schemas as ps, trash
        names = {s["function"]["name"] for s in ps.PLANNER_SCHEMAS}
        deleting = {n for n in names if n.startswith(("delete_", "remove_", "clear_"))}
        assert deleting - set(trash.WATCHED) == NOT_FILED

    def test_every_watched_store_exists_and_has_a_noun(self, planner):
        import storage, trash
        for stores in trash.WATCHED.values():
            for s in stores:
                assert s in storage.DATA_STORES and s in trash.NOUNS


class TestDoctor:
    def check(self):
        import doctor
        return doctor.check_planner_data()

    def warns(self, area):
        return [f for f in self.check() if f["area"] == area and f["level"] == "warn"]

    def test_clean_data_is_ok(self, planner):
        seed(planner)
        assert [x["level"] for x in self.check()] == ["ok"]

    def test_trash_problems(self, planner):
        import storage
        ok = {"id": "a", "store": "tasks", "tool": "delete_task", "deleted": "2026-10-13", "label": "x", "rows": [{"id": "r"}]}
        storage.save_trash([ok, {**ok, "id": "b", "store": "nope"}, {**ok, "id": "c", "store": "trash"}, {**ok, "id": "d", "rows": "x"},
                            {**ok, "id": "e", "deleted": "zz"}])
        assert self.warns("trash")[0]["message"].startswith("4 trash entrie(s)")

    def test_ledger_problems(self, planner):
        import storage
        ok = {"id": "a", "status": "open", "message": "m", "last_seen": "2026-10-13"}
        storage.save_recs([ok, {**ok, "id": "b", "status": "weird"}, {**ok, "id": "c", "message": 5}, {**ok, "id": "d", "last_seen": "zz"}])
        assert self.warns("recs")[0]["message"].startswith("3 recommendation(s)")

    @pytest.mark.parametrize("store", STORES)
    def test_shared_ids(self, planner, store):
        import storage
        storage.save_store(store, [{"id": "x"}, {"id": "x"}, {"id": "y"}])
        assert any("1 id(s) are shared" in f["message"] for f in self.warns(store))

    def test_repair_suggestions(self, planner):
        import storage
        storage.save_trash([{"id": "t1", "store": "nope", "rows": [], "deleted": "2026-10-13"}])
        storage.save_recs([{"id": "r1", "status": "weird", "message": "m", "last_seen": "2026-10-13"}])
        out = planner.dispatch_tool("get_repair_suggestions", {})
        assert "empty_trash(item='t1')" in out and "mark_recommendation(recommendation='r1', status='skipped')" in out


class TestCrossModule:
    def test_search_finds_the_ledger(self, planner):
        seed(planner)
        assert "recs (1):" in planner.dispatch_tool("search_everything", {"query": "sleep"})

    def test_a_deleted_task_no_longer_shows_in_the_agenda_but_comes_back(self, planner):
        d = planner.dispatch_tool
        d("add_task", {"text": "Pay rent", "due": "today"})
        assert "Pay rent" in d("get_today_agenda", {})
        d("delete_task", {"task": "rent"})
        assert "Pay rent" not in d("get_today_agenda", {})
        d("restore_deleted", {"item": "rent"})
        assert "Pay rent" in d("get_today_agenda", {})

    def test_deleting_through_the_tool_dispatch_of_other_modules_is_filed(self, planner):
        d = planner.dispatch_tool
        d("add_chore", {"name": "Water plants", "every": "weekly"})
        d("add_gift_idea", {"person": "Ayse", "idea": "Book"})
        d("delete_chore", {"chore": "water"})
        d("delete_gift_idea", {"gift": "book"})
        assert [e["tool"] for e in __import__("storage").load_trash()] == ["delete_chore", "delete_gift_idea"]

    def test_the_pin_tools_run_through_the_planner_dispatch(self, planner):
        import backup
        backup.run_backup()
        assert planner.dispatch_tool("pin_backup", {}).startswith("Pinned backup-")
        assert len(backup.pinned_names()) == 1
