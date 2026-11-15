"""Time budgets and estimate accuracy together with the shared systems."""

from __future__ import annotations

import pytest

NEW_TOOLS = ["get_estimate_accuracy", "set_time_budget", "get_time_budget", "delete_time_budget"]


def seed(p):
    p.dispatch_tool("set_time_budget", {"category": "deep work", "hours": 10})


class TestRegistry:
    def test_registered(self, planner):
        import storage
        assert "timebudgets" in storage.DATA_STORES and storage.data_store_path("timebudgets").name == "timebudgets.json"
        assert storage.load_store("timebudgets") == []

    def test_export_and_profiles(self, planner):
        import data_export, storage
        seed(planner)
        assert data_export.build_backup_payload()["timebudgets"][0]["hours"] == 10
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("get_time_budget", {}).startswith("No time budgets")
        finally:
            storage.set_active_profile(None)
        assert "deep work" in planner.dispatch_tool("get_time_budget", {})

    def test_backup_and_restore_round_trip(self, planner):
        import backup, restore, storage
        seed(planner)
        path = backup.run_backup()
        before = storage.load_store("timebudgets")
        storage.save_store("timebudgets", [])
        restore.restore_backup(path)
        assert storage.load_store("timebudgets") == before and before


class TestDispatch:
    @pytest.mark.parametrize("tool", NEW_TOOLS)
    def test_empty_and_junk_input_never_raise(self, planner, tool):
        d = planner.dispatch_tool
        assert isinstance(d(tool, {}), str)
        assert isinstance(d(tool, {"category": 5, "hours": "x", "kind": [], "days": "z", "calibrate": {}}), str)

    def test_schemas_are_wired(self, planner):
        import planner_schemas as ps
        names = {s["function"]["name"] for s in ps.PLANNER_SCHEMAS}
        assert set(NEW_TOOLS) <= names and all(t in ps.TOOL_MODULES for t in NEW_TOOLS)

    def test_delete_is_recoverable(self, planner):
        d = planner.dispatch_tool
        seed(planner)
        d("delete_time_budget", {"category": "deep work"})
        assert "deep work" in d("get_trash", {})
        assert d("restore_deleted", {"item": "deep work"}).startswith("Restored")
        assert "deep work" in d("get_time_budget", {})


class TestSharedSystems:
    def test_search_finds_budgets(self, planner):
        seed(planner)
        assert "deep work" in planner.dispatch_tool("search_everything", {"query": "deep"})

    def test_failures_are_isolated(self, planner, monkeypatch):
        import nudges, timebudgets
        monkeypatch.setattr(timebudgets, "agenda_lines", lambda: 1 / 0)
        monkeypatch.setattr(timebudgets, "nudges", lambda n=1: 1 / 0)
        assert isinstance(planner.dispatch_tool("get_today_agenda", {}), str)
        assert isinstance(nudges._planner_nudges(), list)


class TestDoctor:
    def test_clean_data_has_no_warnings(self, planner):
        import doctor
        seed(planner)
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"] == []

    @pytest.mark.parametrize("row", [
        {"id": "b1", "category": "", "hours": 5, "kind": "min"},
        {"id": "b2", "category": "x", "hours": "a", "kind": "min"},
        {"id": "b3", "category": "x", "hours": 5, "kind": "exact"},
    ])
    def test_problems_are_reported_and_have_a_repair_hint(self, planner, row):
        import doctor, storage
        storage.save_store("timebudgets", [row])
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"]
        assert row["id"] in planner.dispatch_tool("get_repair_suggestions", {})
