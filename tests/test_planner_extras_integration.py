"""Lists, savings, symptoms and notes together: doctor, registry, export, profiles, rekey."""

from __future__ import annotations

import json

import pytest

NEW_STORES = ["lists", "savings", "symptoms", "notes"]


class TestDoctor:
    def check(self):
        import doctor
        return doctor.check_planner_data()

    def warns(self, area):
        return [f for f in self.check() if f["area"] == area and f["level"] == "warn"]

    def test_clean_data_is_ok(self, planner):
        planner.dispatch_tool("add_list_items", {"items": "milk"})
        planner.dispatch_tool("add_savings_goal", {"name": "g", "target": 10, "deadline": "2027-01-01"})
        planner.dispatch_tool("log_symptom", {"symptom": "headache", "severity": 3})
        planner.dispatch_tool("add_note", {"text": "hello"})
        f = self.check()
        assert [x["level"] for x in f] == ["ok"]
        assert "countdowns, supplies, time blocks, objectives, recipes, the meal plan, trips, chores, expiry dates, routines, gift ideas and decisions are all readable" in f[0]["message"]

    def test_savings_problems(self, planner):
        import storage
        storage.save_savings([
            {"id": "a", "name": "ok", "target": 10, "deadline": "2027-01-01"},
            {"id": "b", "name": "bad target", "target": 0},
            {"id": "c", "name": "text target", "target": "lots"},
            {"id": "d", "name": "bad deadline", "target": 5, "deadline": "soon"}])
        w = self.warns("savings")
        assert len(w) == 1 and w[0]["message"].startswith("3 savings goal(s)")

    def test_symptom_problems(self, planner):
        import storage
        storage.save_symptoms([
            {"id": "a", "date": "2026-10-01", "symptom": "x", "severity": 5},
            {"id": "b", "date": "2026-10-01", "symptom": "x", "severity": 11},
            {"id": "c", "date": "2026-10-01", "symptom": "x", "severity": 0},
            {"id": "d", "date": "nope", "symptom": "x", "severity": 3},
            {"id": "e", "date": "2026-10-01", "severity": 3},
            {"id": "f", "date": "2026-10-01", "symptom": "x", "severity": "high"}])
        w = self.warns("symptoms")
        assert len(w) == 1 and w[0]["message"].startswith("5 symptom entries")

    def test_list_items_and_notes_without_text(self, planner):
        import storage
        storage.save_lists([{"id": "a", "list": "x", "text": "ok"}, {"id": "b", "list": "x", "text": " "},
                            {"id": "c", "list": "x"}])
        storage.save_notes([{"id": "a", "text": "ok"}, {"id": "b", "text": ""}])
        assert self.warns("lists")[0]["message"].startswith("2 list item(s)")
        assert self.warns("notes")[0]["message"].startswith("1 note(s)")

    @pytest.mark.parametrize("store", NEW_STORES)
    def test_shared_ids(self, planner, store):
        import storage
        storage.save_store(store, [{"id": "a", "text": "1"}, {"id": "a", "text": "2"}])
        w = self.warns(store)
        assert any("shared by more than one entry" in x["message"] for x in w)

    @pytest.mark.parametrize("store", NEW_STORES)
    def test_malformed_stores_do_not_crash(self, planner, store):
        import storage
        storage.save_store(store, {"not": "a list"})
        assert [x["level"] for x in self.check()] == ["ok"]
        storage.save_store(store, ["junk", None, 5])
        assert [x["level"] for x in self.check()] == ["ok"]

    def test_read_only(self, planner):
        import storage
        storage.save_lists([{"list": "x", "text": "no id"}])
        storage.save_notes([{"text": "no id"}])
        self.check()
        assert "id" not in storage.load_lists()[0] and "id" not in storage.load_notes()[0]

    def test_symptom_journal_links_are_not_orphans(self, planner):
        import doctor
        planner.dispatch_tool("log_symptom", {"symptom": "headache", "severity": 3})
        assert [f["level"] for f in doctor.check_entry_ids()] == ["ok"]

    def test_deleting_a_symptom_row_by_hand_orphans_its_journal_entry(self, planner):
        import doctor, storage
        planner.dispatch_tool("log_symptom", {"symptom": "headache", "severity": 3})
        storage.save_symptoms([])
        assert any(f["level"] == "warn" for f in doctor.check_entry_ids())

    def test_future_dated_symptoms_and_body_readings_are_flagged(self, planner):
        import doctor, storage
        storage.save_symptoms([{"id": "a", "date": "2030-01-01", "symptom": "x", "severity": 3}])
        storage.save_body([{"id": "b", "date": "2031-01-01", "metric": "weight", "value": 80}])
        f = doctor.check_future_dates()
        assert {x["area"] for x in f if x["level"] == "warn"} == {"symptoms", "body"}

    def test_run_checks_includes_it(self, planner):
        import doctor, storage
        storage.save_savings([{"id": "b", "name": "x", "target": 0}])
        assert any(f["area"] == "savings" and f["level"] == "warn" for f in doctor.run_checks())


class TestRegistry:
    @pytest.mark.parametrize("store", NEW_STORES)
    def test_registered_with_a_file_and_a_loader(self, planner, store):
        import storage
        assert store in storage.DATA_STORES
        assert storage.data_store_path(store).name == f"{store}.json"
        assert storage.load_store(store) == []

    def test_export_contains_them(self, planner):
        import data_export
        planner.dispatch_tool("add_note", {"text": "export me"})
        planner.dispatch_tool("log_symptom", {"symptom": "x", "severity": 2})
        data = data_export.build_backup_payload()
        assert data["notes"][0]["text"] == "export me" and data["symptoms"][0]["symptom"] == "x"
        assert data["lists"] == [] and data["savings"] == []

    def test_profiles_are_separate(self, planner):
        import storage
        planner.dispatch_tool("add_note", {"text": "default profile"})
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("list_notes", {}) == "No notes yet."
            planner.dispatch_tool("add_list_items", {"items": "alex only"})
        finally:
            storage.set_active_profile(None)
        assert planner.dispatch_tool("get_lists", {}) == "No lists yet. Add items with add_list_items."
        assert planner.dispatch_tool("list_notes", {}).startswith("1 note:")

    def test_backup_contains_every_new_store(self, planner):
        import backup
        planner.dispatch_tool("add_note", {"text": "n"})
        planner.dispatch_tool("add_list_items", {"items": "i"})
        planner.dispatch_tool("add_savings_goal", {"name": "g", "target": 5})
        planner.dispatch_tool("log_symptom", {"symptom": "x", "severity": 2})
        info = backup.describe_backup(backup.run_backup())
        assert info["readable"]
        text = json.dumps(info, default=str)
        for store in NEW_STORES:
            assert store in text


class TestDispatch:
    @pytest.mark.parametrize("name", ["add_list_items", "get_list", "get_lists", "check_list_item",
                                      "remove_list_items", "clear_checked_items", "delete_list",
                                      "add_savings_goal", "contribute_to_savings", "get_savings",
                                      "update_savings_goal", "delete_savings_goal", "log_symptom",
                                      "get_symptom_summary", "add_note", "list_notes", "search_notes",
                                      "update_note", "delete_note"])
    def test_every_tool_is_dispatched_and_never_raises_on_empty_input(self, planner, name):
        out = planner.dispatch_tool(name, {})
        assert isinstance(out, str) and out and not out.startswith("Unknown")

    def test_every_new_schema_is_wired_to_a_module(self, planner):
        from planner_schemas import LIST_SCHEMAS, SAVINGS_SCHEMAS, SYMPTOM_SCHEMAS, NOTE_SCHEMAS, TOOL_MODULES
        for schemas, module in ((LIST_SCHEMAS, "lists"), (SAVINGS_SCHEMAS, "savings"),
                                (SYMPTOM_SCHEMAS, "symptoms"), (NOTE_SCHEMAS, "notes")):
            for s in schemas:
                assert TOOL_MODULES[s["function"]["name"]] == module

    def test_tool_names_are_unique(self, planner):
        names = [t["function"]["name"] for t in planner.TOOLS]
        assert len(names) == len(set(names))

    def test_unknown_tool_in_a_module(self, planner):
        import lists, notes, savings, symptoms
        for mod in (lists, notes, savings, symptoms):
            assert mod.run_tool("nope", {}).startswith("Unknown ")

    def test_everything_declared_required_is_a_property(self, planner):
        for t in planner.TOOLS:
            params = t["function"]["parameters"]
            assert set(params.get("required", [])) <= set(params.get("properties", {})), t["function"]["name"]


class TestAgendaAndNudgesStillWork:
    def test_cap_with_four_sources(self, planner):
        import nudges
        planner.dispatch_tool("add_task", {"text": "old", "due": "2026-10-01"})
        planner.dispatch_tool("add_subscription", {"name": "Netflix", "amount": 15, "next_date": "2026-10-14"})
        planner.dispatch_tool("add_savings_goal", {"name": "g", "target": 10, "deadline": "2026-10-20"})
        assert len(nudges._planner_nudges()) == nudges.MAX_PLANNER_NUDGES

    def test_savings_nudge_alone(self, planner):
        import nudges
        planner.dispatch_tool("add_savings_goal", {"name": "g", "target": 10, "deadline": "2026-10-20"})
        assert nudges._planner_nudges() == ["Savings goal 'g' is 0% there with 7 days left: 10 to go."]

    def test_a_failing_savings_source_is_ignored(self, planner, monkeypatch):
        import nudges, savings
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        monkeypatch.setattr(savings, "nudges", lambda *a, **k: 1 / 0)
        assert any("Ayse" in n for n in nudges._planner_nudges())

    def test_agenda_survives_a_failing_savings_source(self, planner, monkeypatch):
        import savings
        monkeypatch.setattr(savings, "nudges", lambda *a, **k: 1 / 0)
        assert planner.dispatch_tool("get_today_agenda", {}).startswith("Agenda for 2026-10-13")
