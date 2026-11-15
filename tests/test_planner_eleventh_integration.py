"""Experiments, tripwires, the workload forecast and the timeline together with the shared systems."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

STORES = ["experiments", "tripwires"]
NEW_TOOLS = ["start_experiment", "get_experiments", "get_experiment", "conclude_experiment", "delete_experiment",
             "add_tripwire", "get_tripwires", "delete_tripwire", "get_workload_forecast", "get_life_timeline"]


def seed(p):
    d = p.dispatch_tool
    d("start_experiment", {"name": "No late caffeine", "metric": "sleep", "change": "no coffee after 2pm"})
    d("add_tripwire", {"name": "Sleep debt", "metric": "sleep", "condition": "below", "threshold": 6,
                       "message": "Protect tonight."})


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
        assert data["experiments"][0]["metric"] == "sleep" and data["tripwires"][0]["threshold"] == 6

    def test_profiles_are_separate(self, planner):
        import storage
        seed(planner)
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("get_experiments", {}).startswith("No experiments")
            assert planner.dispatch_tool("get_tripwires", {}).startswith("No tripwires")
        finally:
            storage.set_active_profile(None)
        assert "No late caffeine" in planner.dispatch_tool("get_experiments", {})

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
        assert isinstance(d(tool, {"name": 5, "metric": [], "experiment": 3, "decision": {}, "days": "x", "kinds": 4,
                                   "condition": 1, "threshold": "q", "tripwire": [], "status": 2, "change": {},
                                   "baseline_days": "z", "start": 9, "message": []}), str)

    def test_schemas_are_wired(self, planner):
        import planner_schemas as ps
        names = {s["function"]["name"] for s in ps.PLANNER_SCHEMAS}
        assert set(NEW_TOOLS) <= names and all(t in ps.TOOL_MODULES for t in NEW_TOOLS)

    def test_deletes_are_recoverable(self, planner):
        d = planner.dispatch_tool
        seed(planner)
        d("delete_experiment", {"experiment": "caffeine"})
        d("delete_tripwire", {"tripwire": "sleep debt"})
        out = d("get_trash", {})
        assert "No late caffeine" in out and "Sleep debt" in out
        assert d("restore_deleted", {"item": "Sleep debt"}).startswith("Restored")
        assert "Sleep debt" in d("get_tripwires", {})


class TestSharedSystems:
    def test_search_finds_them(self, planner):
        seed(planner)
        d = planner.dispatch_tool
        assert "No late caffeine" in d("search_everything", {"query": "coffee"})
        assert "Sleep debt" in d("search_everything", {"query": "protect tonight"})

    def test_agenda_and_nudges_show_tripped_wires(self, planner, monkeypatch):
        import metricseries, nudges
        seed(planner)
        data = {(datetime(2026, 10, 13) + timedelta(days=-k)).strftime("%Y-%m-%d"): {"sleep": 5.0} for k in range(3)}
        monkeypatch.setattr(metricseries, "load_daily", lambda: data)
        assert "Tripwires:" in planner.dispatch_tool("get_today_agenda", {})
        assert any("Sleep debt" in n for n in nudges._planner_nudges())

    def test_failures_are_isolated(self, planner, monkeypatch):
        import experiments, nudges, tripwires, workload
        for mod in (experiments, tripwires, workload):
            monkeypatch.setattr(mod, "agenda_lines", lambda: 1 / 0)
            monkeypatch.setattr(mod, "nudges", lambda n=1: 1 / 0)
        assert isinstance(planner.dispatch_tool("get_today_agenda", {}), str)
        assert isinstance(nudges._planner_nudges(), list)


class TestDoctor:
    def test_clean_data_has_no_warnings(self, planner):
        import doctor
        seed(planner)
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"] == []

    @pytest.mark.parametrize("store,row", [
        ("experiments", {"id": "e1", "name": "", "metric": "sleep", "status": "running", "days": 5, "baseline_days": 5, "start": "2026-10-13"}),
        ("experiments", {"id": "e2", "name": "x", "metric": "luck", "status": "running", "days": 5, "baseline_days": 5, "start": "2026-10-13"}),
        ("experiments", {"id": "e3", "name": "x", "metric": "sleep", "status": "running", "days": 5, "baseline_days": 5, "start": "nope"}),
        ("tripwires", {"id": "t1", "name": "x", "metric": "sleep", "op": "near", "threshold": 3, "days": 2}),
        ("tripwires", {"id": "t2", "name": "x", "metric": "sleep", "op": "below", "threshold": "a", "days": 2}),
    ])
    def test_problems_are_reported_and_have_a_repair_hint(self, planner, store, row):
        import doctor, storage
        storage.save_store(store, [row])
        assert [f for f in doctor.check_planner_data() if f["level"] == "warn"]
        assert row["id"] in planner.dispatch_tool("get_repair_suggestions", {})
