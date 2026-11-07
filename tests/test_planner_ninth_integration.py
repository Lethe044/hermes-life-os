"""Flashcards and net worth together with the shared systems."""

from __future__ import annotations

import pytest

STORES = ["cards", "networth"]
NEW_TOOLS = ["add_flashcards", "review_flashcards", "reveal_flashcard", "answer_flashcard", "get_flashcard_stats",
             "delete_flashcard", "set_account_balance", "get_net_worth", "get_net_worth_trend", "delete_account"]


def seed(p):
    d = p.dispatch_tool
    d("add_flashcards", {"cards": [{"front": "Capital of Peru", "back": "Lima"}], "deck": "geo"})
    d("set_account_balance", {"name": "Brokerage", "balance": 4200, "kind": "asset", "category": "investments"})


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
        assert data["cards"][0]["back"] == "Lima" and data["networth"][0]["balance"] == 4200

    def test_profiles_are_separate(self, planner):
        import storage
        seed(planner)
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("get_flashcard_stats", {}).startswith("No flashcards")
            assert planner.dispatch_tool("get_net_worth", {}).startswith("No accounts")
        finally:
            storage.set_active_profile(None)
        assert "Brokerage" in planner.dispatch_tool("get_net_worth", {})

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
        assert isinstance(d(tool, {"cards": 5, "deck": [], "card": 3, "correct": "x", "name": {}, "balance": "x",
                                   "kind": 1, "category": [], "months": "x", "account": 2}), str)

    def test_schemas_are_wired(self, planner):
        import planner_schemas as ps
        names = {s["function"]["name"] for s in ps.PLANNER_SCHEMAS}
        assert set(NEW_TOOLS) <= names and all(t in ps.TOOL_MODULES for t in NEW_TOOLS)

    def test_deletes_are_recoverable(self, planner):
        d = planner.dispatch_tool
        seed(planner)
        d("delete_flashcard", {"card": "peru"})
        d("delete_account", {"account": "brokerage"})
        assert "Peru" in d("get_trash", {}) and "Brokerage" in d("get_trash", {})
        assert d("restore_deleted", {"item": "Brokerage"}).startswith("Restored")
        assert "Brokerage" in d("get_net_worth", {})


class TestSharedSystems:
    def test_search_finds_them(self, planner):
        seed(planner)
        d = planner.dispatch_tool
        assert "Capital of Peru" in d("search_everything", {"query": "lima"})
        assert "Brokerage" in d("search_everything", {"query": "investments"})

    def test_agenda_shows_due_cards(self, planner):
        seed(planner)
        assert "Flashcards:" in planner.dispatch_tool("get_today_agenda", {})

    def test_failures_are_isolated(self, planner, monkeypatch):
        import flashcards, networth, nudges
        monkeypatch.setattr(flashcards, "agenda_lines", lambda: 1 / 0)
        monkeypatch.setattr(flashcards, "nudges", lambda n=1: 1 / 0)
        monkeypatch.setattr(networth, "nudges", lambda n=1: 1 / 0)
        assert isinstance(planner.dispatch_tool("get_today_agenda", {}), str)
        assert isinstance(nudges._planner_nudges(), list)


class TestDoctor:
    def test_clean_data_has_no_warnings(self, planner):
        import doctor
        seed(planner)
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"] == []

    @pytest.mark.parametrize("store,row", [
        ("cards", {"id": "c1", "front": "a", "back": "b", "box": 9, "due": "2026-10-13"}),
        ("cards", {"id": "c2", "front": "a", "back": "b", "box": 1, "due": "nope"}),
        ("networth", {"id": "n1", "name": "x", "kind": "gold", "history": [], "balance": 1}),
        ("networth", {"id": "n2", "name": "x", "kind": "asset", "history": [], "balance": "lots"}),
    ])
    def test_problems_are_reported_and_have_a_repair_hint(self, planner, store, row):
        import doctor, storage
        storage.save_store(store, [row])
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"]
        assert row["id"] in planner.dispatch_tool("get_repair_suggestions", {})
