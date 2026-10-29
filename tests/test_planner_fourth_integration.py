"""Time blocks, objectives, recipes, the meal plan and trips together with the shared systems."""

from __future__ import annotations

import pytest

STORES = ["timeblocks", "okrs", "recipes", "mealplan", "trips"]
NEW_TOOLS = [
    "add_time_block", "get_day_plan", "update_time_block", "delete_time_block", "finish_time_block", "find_free_time",
    "schedule_task", "get_time_allocation", "add_objective", "add_key_result", "record_key_result", "get_okrs", "update_okr",
    "delete_okr", "add_recipe", "get_recipes", "get_recipe", "update_recipe", "delete_recipe", "suggest_recipes", "plan_meal",
    "get_meal_plan", "clear_meals", "log_planned_meal", "shopping_from_plan", "add_trip", "get_trips", "get_trip", "update_trip",
    "delete_trip", "add_packing_items", "pack_items", "remove_packing_items", "add_itinerary_item", "remove_itinerary_item",
    "search_everything", "get_closing_summary", "get_repair_suggestions", "get_symptom_triggers"]


def seed_all(p):
    d = p.dispatch_tool
    d("add_time_block", {"title": "Deep work", "start": "09:00", "end": "10:00"})
    d("add_objective", {"name": "Fit", "key_results": [{"name": "Run", "target": 10}]})
    d("add_recipe", {"name": "Soup", "ingredients": ["2 carrots"], "servings": 2})
    d("plan_meal", {"slot": "dinner", "recipe": "soup"})
    d("add_trip", {"name": "Rome", "start": "2026-11-01", "template": "city"})


class TestRegistry:
    @pytest.mark.parametrize("store", STORES)
    def test_registered(self, planner, store):
        import storage
        assert store in storage.DATA_STORES and storage.data_store_path(store).name == f"{store}.json"
        assert storage.load_store(store) == []

    def test_export_contains_them(self, planner):
        import data_export
        seed_all(planner)
        data = data_export.build_backup_payload()
        assert data["timeblocks"][0]["title"] == "Deep work" and data["okrs"][0]["name"] == "Fit"
        assert data["recipes"][0]["name"] == "Soup" and data["mealplan"][0]["name"] == "Soup" and data["trips"][0]["name"] == "Rome"

    def test_profiles_are_separate(self, planner):
        import storage
        seed_all(planner)
        storage.set_active_profile("alex")
        try:
            for tool, empty in (("get_okrs", "No objectives yet"), ("get_trips", "No trips yet"), ("get_recipes", "No recipes yet"),
                                ("get_day_plan", "Nothing planned"), ("get_meal_plan", "No meals planned")):
                assert planner.dispatch_tool(tool, {}).startswith(empty), tool
        finally:
            storage.set_active_profile(None)
        assert planner.dispatch_tool("get_trips", {}).startswith("1 trip:")

    def test_backup_and_restore_round_trip(self, planner):
        import backup, restore, storage
        seed_all(planner)
        path = backup.run_backup()
        before = {s: storage.load_store(s) for s in STORES}
        for s in STORES:
            storage.save_store(s, [])
        restore.restore_backup(path)
        assert {s: storage.load_store(s) for s in STORES} == before and all(before.values())

    def test_restore_knows_the_new_sections(self, planner):
        import restore
        assert set(STORES) <= set(restore.known_sections())


class TestDispatch:
    @pytest.mark.parametrize("name", NEW_TOOLS)
    def test_every_tool_is_dispatched_and_never_raises_on_empty_input(self, planner, name):
        out = planner.dispatch_tool(name, {})
        assert isinstance(out, str) and out and not out.startswith("Unknown")

    @pytest.mark.parametrize("name", NEW_TOOLS)
    def test_every_tool_survives_junk_arguments(self, planner, name):
        junk = {k: [{"x": 1}] for k in ("title", "start", "end", "date", "task", "block", "objective", "name", "recipe", "trip",
                                         "query", "slot", "text", "items", "fields", "days", "period", "symptom", "limit", "meal")}
        out = planner.dispatch_tool(name, junk)
        assert isinstance(out, str) and out

    def test_every_schema_is_wired_to_a_module(self, planner):
        import planner_schemas as ps
        for schemas, module in ((ps.TIMEBLOCK_SCHEMAS, "timeblocks"), (ps.OKR_SCHEMAS, "okrs"), (ps.RECIPE_SCHEMAS, "recipes"),
                                (ps.TRIP_SCHEMAS, "trips"), (ps.SEARCH_SCHEMAS, "finder"), (ps.CLOSING_SCHEMAS, "closing"),
                                (ps.REPAIR_SCHEMAS, "repair_hints")):
            for s in schemas:
                assert ps.TOOL_MODULES[s["function"]["name"]] == module
        assert ps.TOOL_MODULES["get_symptom_triggers"] == "symptoms"
        assert set(NEW_TOOLS) <= set(ps.TOOL_MODULES)

    def test_the_new_tools_are_in_the_tool_list(self, planner):
        names = {t["function"]["name"] for t in planner.TOOLS}
        assert set(NEW_TOOLS) <= names

    def test_required_arguments_have_schemas_and_descriptions(self, planner):
        for t in planner.TOOLS:
            f = t["function"]
            if f["name"] in NEW_TOOLS:
                assert len(f["description"]) > 10 and set(f["parameters"].get("required", [])) <= set(f["parameters"]["properties"])

    def test_unknown_tool_in_a_module(self, planner):
        import timeblocks, okrs, recipes, trips, finder, closing, repair_hints
        for mod in (timeblocks, okrs, recipes, trips, finder, closing, repair_hints):
            assert mod.run_tool("nope", {}).startswith("Unknown ")

    def test_date_properties_are_not_the_shared_backdate_text(self, planner):
        from planner_schemas import ENTRY_DATE_PROP
        for t in planner.TOOLS:
            if t["function"]["name"] in NEW_TOOLS:
                d = t["function"]["parameters"]["properties"].get("date")
                assert d is None or d != ENTRY_DATE_PROP, t["function"]["name"]


class TestDoctor:
    def check(self):
        import doctor
        return doctor.check_planner_data()

    def warns(self, area):
        return [f for f in self.check() if f["area"] == area and f["level"] == "warn"]

    def test_clean_data_is_ok(self, planner):
        seed_all(planner)
        f = self.check()
        assert [x["level"] for x in f] == ["ok"]
        assert "time blocks, objectives, recipes, the meal plan, trips, chores, expiry dates, routines, gift ideas and decisions" in f[0]["message"]

    def test_timeblock_problems(self, planner):
        import storage
        storage.save_timeblocks([{"id": "a", "date": "2026-10-13", "start": "09:00", "end": "10:00", "title": "ok"},
                                 {"id": "b", "date": "2026-10-13", "start": "11:00", "end": "10:00"},
                                 {"id": "c", "date": "nope", "start": "09:00", "end": "10:00"},
                                 {"id": "d", "date": "2026-10-13", "start": "x", "end": "10:00"}])
        assert self.warns("timeblocks")[0]["message"].startswith("3 time block(s)")

    def test_okr_problems(self, planner):
        import storage
        good = {"start_value": 0, "target": 5, "current": 1}
        storage.save_okrs([{"id": "a", "start": "2026-10-01", "end": "2026-12-31", "key_results": [good]},
                           {"id": "b", "start": "x", "end": "2026-12-31"},
                           {"id": "c", "start": "2026-10-01", "end": "2026-12-31", "key_results": [{**good, "target": 0}]},
                           {"id": "d", "start": "2026-10-01", "end": "2026-12-31", "key_results": [{**good, "current": "x"}]},
                           {"id": "e", "start": "2026-10-01", "end": "2026-12-31", "key_results": ["junk"]}])
        assert self.warns("okrs")[0]["message"].startswith("4 objective(s)")

    def test_recipe_problems(self, planner):
        import storage
        storage.save_recipes([{"id": "a", "ingredients": [{"name": "x"}], "servings": 2}, {"id": "b", "ingredients": [], "servings": 2},
                              {"id": "c", "ingredients": "x", "servings": 2}, {"id": "d", "ingredients": [{"name": "x"}], "servings": 0},
                              {"id": "e", "ingredients": [{"name": "x"}], "servings": True}])
        assert self.warns("recipes")[0]["message"].startswith("4 recipe(s)")

    def test_mealplan_problems(self, planner):
        import storage
        storage.save_mealplan([{"id": "a", "date": "2026-10-13", "slot": "dinner"}, {"id": "b", "date": "x", "slot": "dinner"},
                               {"id": "c", "date": "2026-10-13", "slot": "brunch"}])
        assert self.warns("mealplan")[0]["message"].startswith("2 planned meal(s)")

    def test_trip_problems(self, planner):
        import storage
        storage.save_trips([{"id": "a", "start": "2026-11-01", "end": "2026-11-03"}, {"id": "b", "start": "x", "end": "2026-11-03"},
                            {"id": "c", "start": "2026-11-05", "end": "2026-11-03"}])
        assert self.warns("trips")[0]["message"].startswith("2 trip(s)")

    @pytest.mark.parametrize("store", STORES)
    def test_shared_ids(self, planner, store):
        import storage
        storage.save_store(store, [{"id": "x"}, {"id": "x"}, {"id": "y"}])
        assert any("1 id(s) are shared" in f["message"] for f in self.warns(store))

    def test_the_doctor_never_assigns_ids(self, planner):
        import storage
        storage.save_trips([{"name": "x", "start": "2026-11-01", "end": "2026-11-02"}])
        self.check()
        assert "id" not in storage.load_trips()[0]


class TestAgendaAndNudges:
    def test_agenda_sections_and_order(self, planner):
        d = planner.dispatch_tool
        d("add_task", {"text": "t", "due": "today"})
        d("add_countdown", {"name": "Exam", "date": "2026-10-14"})
        d("add_time_block", {"title": "Deep work", "start": "09:00", "end": "10:00"})
        d("add_objective", {"name": "Ship", "start": "2026-10-01", "end": "2026-10-16", "key_results": [{"name": "t", "target": 10}]})
        d("add_trip", {"name": "Rome", "start": "2026-10-15", "template": "city"})
        out = d("get_today_agenda", {})
        heads = ("Tasks (", "Countdowns:", "Time blocks:", "Objectives about to end:", "Trips:")
        order = [out.index(h) for h in heads]
        assert order == sorted(order)
        assert "Rome starts in 2 days, 4 of 4 items still to pack" in out and "Ship: ends in 3 days, 0% done" in out

    @pytest.mark.parametrize("module,attr", [("timeblocks", "agenda_lines"), ("okrs", "agenda_lines"), ("trips", "agenda_lines")])
    def test_agenda_survives_a_failing_source(self, planner, monkeypatch, module, attr):
        mod = __import__(module)
        monkeypatch.setattr(mod, attr, lambda *a, **k: 1 / 0)
        assert planner.dispatch_tool("get_today_agenda", {}).startswith("Agenda for 2026-10-13")

    @pytest.mark.parametrize("module", ["timeblocks", "okrs", "trips"])
    def test_a_failing_nudge_source_is_ignored(self, planner, monkeypatch, module):
        import nudges
        mod = __import__(module)
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        monkeypatch.setattr(mod, "nudges", lambda *a, **k: 1 / 0)
        assert any("Ayse" in n for n in nudges._planner_nudges())

    def test_new_sources_show_when_the_old_ones_are_quiet(self, planner):
        import nudges
        from datetime import datetime
        d = planner.dispatch_tool
        planner.set_now(datetime(2026, 10, 13, 8, 50))
        d("add_time_block", {"title": "Standup", "start": "09:00", "end": "09:15"})
        d("add_objective", {"name": "Ship", "start": "2026-10-01", "end": "2026-10-16", "key_results": [{"name": "t", "target": 10}]})
        d("add_trip", {"name": "Rome", "start": "2026-10-15", "template": "city"})
        assert nudges._planner_nudges() == ["Standup starts in 10 min (09:00).", "Objective 'Ship' ends in 3 days and is 0% done.",
                                            "Rome starts in 2 days and 4 of 4 packing items are not packed yet."]

    def test_the_cap_still_holds(self, planner):
        import nudges
        d = planner.dispatch_tool
        d("add_task", {"text": "old", "due": "2026-10-01"})
        d("add_subscription", {"name": "N", "amount": 15, "next_date": "2026-10-14"})
        d("add_person", {"name": "Ayse", "birthday": "10-14"})
        d("add_trip", {"name": "Rome", "start": "2026-10-15", "template": "city"})
        got = nudges._planner_nudges()
        assert len(got) == 3 and not any("Rome" in n for n in got)


class TestCrossModule:
    def test_search_finds_every_new_store(self, planner):
        seed_all(planner)
        for query, area in (("deep", "timeblocks"), ("fit", "okrs"), ("carrots", "recipes"), ("soup", "mealplan"), ("rome", "trips")):
            assert f"{area} (" in planner.dispatch_tool("search_everything", {"query": query}), area

    def test_the_closing_summary_sees_the_new_stores(self, planner):
        seed_all(planner)
        out = planner.dispatch_tool("get_closing_summary", {})
        assert "unfinished block: 09:00-10:00 Deep work" in out

    def test_repair_suggestions_cover_the_new_stores(self, planner):
        import storage
        storage.save_trips([{"id": "z1", "name": "Rome", "start": "x", "end": "y"}])
        storage.save_mealplan([{"id": "m1", "date": "x", "slot": "dinner", "name": "n"}])
        out = planner.dispatch_tool("get_repair_suggestions", {})
        assert "update_trip(trip='z1'" in out and "clear_meals(meal='m1')" in out

    def test_shopping_list_round_trip(self, planner):
        seed_all(planner)
        planner.dispatch_tool("shopping_from_plan", {})
        assert planner.dispatch_tool("get_list", {}).count("carrots") == 1

    def test_schedule_a_task_then_finish_it_from_the_block(self, planner):
        d = planner.dispatch_tool
        d("add_task", {"text": "Write report"})
        d("schedule_task", {"task": "report", "duration_minutes": 30})
        d("finish_time_block", {"block": "report", "complete_task": True})
        assert d("get_task_summary", {}).startswith("0 open task(s)") or "done" in d("list_tasks", {"status": "done"}).lower()
        assert "Write report" in d("list_tasks", {"status": "done"})
