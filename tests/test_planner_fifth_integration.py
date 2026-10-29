"""Chores, expiry dates, routines, gift ideas, decisions and the week ahead together with the shared systems."""

from __future__ import annotations

from datetime import datetime

import pytest

STORES = ["chores", "expiries", "routines", "gifts", "decisions"]
NEW_TOOLS = [
    "add_chore", "complete_chore", "get_chores", "update_chore", "delete_chore",
    "add_expiry", "get_expiries", "renew_expiry", "update_expiry", "delete_expiry",
    "add_routine", "get_routines", "check_routine_step", "update_routine", "delete_routine",
    "add_gift_idea", "get_gift_ideas", "update_gift_idea", "delete_gift_idea",
    "add_decision", "get_decisions", "review_decision", "update_decision", "delete_decision", "get_week_ahead"]


def seed_all(p):
    d = p.dispatch_tool
    d("add_chore", {"name": "Water plants", "every": "weekly"})
    d("add_expiry", {"name": "Passport", "date": "2026-11-01"})
    d("add_routine", {"name": "Morning", "steps": ["Stretch", "Water"]})
    d("add_gift_idea", {"person": "Ayse", "idea": "Poetry book"})
    d("add_decision", {"title": "Standing desk"})


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
        assert data["chores"][0]["name"] == "Water plants" and data["expiries"][0]["name"] == "Passport"
        assert data["routines"][0]["name"] == "Morning" and data["gifts"][0]["idea"] == "Poetry book"
        assert data["decisions"][0]["title"] == "Standing desk"

    def test_profiles_are_separate(self, planner):
        import storage
        seed_all(planner)
        storage.set_active_profile("alex")
        try:
            for tool, empty in (("get_chores", "No chores yet"), ("get_expiries", "No expiry dates yet"), ("get_routines", "No routines yet"),
                                ("get_gift_ideas", "No gift ideas yet"), ("get_decisions", "No decisions to show")):
                assert planner.dispatch_tool(tool, {}).startswith(empty), tool
        finally:
            storage.set_active_profile(None)
        assert planner.dispatch_tool("get_chores", {}).startswith("1 chore:")

    def test_backup_and_restore_round_trip(self, planner):
        import backup, restore, storage
        seed_all(planner)
        path = backup.run_backup()
        before = {s: storage.load_store(s) for s in STORES}
        for s in STORES:
            storage.save_store(s, [])
        restore.restore_backup(path)
        assert {s: storage.load_store(s) for s in STORES} == before and all(before.values())


class TestDispatch:
    @pytest.mark.parametrize("name", NEW_TOOLS)
    def test_every_tool_is_dispatched_and_never_raises_on_empty_input(self, planner, name):
        out = planner.dispatch_tool(name, {})
        assert isinstance(out, str) and out and not out.startswith("Unknown")

    @pytest.mark.parametrize("name", NEW_TOOLS)
    def test_every_tool_survives_junk_arguments(self, planner, name):
        keys = ("name", "every", "start", "date", "chore", "item", "routine", "step", "gift", "decision", "person", "idea", "title",
                "fields", "days", "steps", "outcome", "rating", "options", "price", "filter", "status", "new_date", "extend_months")
        junk = {k: [{"x": 1}] for k in keys}
        out = planner.dispatch_tool(name, junk)
        assert isinstance(out, str) and out

    def test_every_schema_is_wired_to_a_module(self, planner):
        import planner_schemas as ps
        for schemas, module in ((ps.CHORE_SCHEMAS, "chores"), (ps.EXPIRY_SCHEMAS, "expiries"), (ps.ROUTINE_SCHEMAS, "routines"),
                                (ps.GIFT_SCHEMAS, "gifts"), (ps.DECISION_SCHEMAS, "decisions"), (ps.WEEKAHEAD_SCHEMAS, "weekahead")):
            for s in schemas:
                assert ps.TOOL_MODULES[s["function"]["name"]] == module
        assert set(NEW_TOOLS) <= set(ps.TOOL_MODULES)

    def test_tool_names_are_unique(self, planner):
        names = [t["function"]["name"] for t in planner.TOOLS]
        assert len(names) == len(set(names)) and set(NEW_TOOLS) <= set(names)

    def test_schemas_are_well_formed(self, planner):
        for t in planner.TOOLS:
            f = t["function"]
            if f["name"] in NEW_TOOLS:
                assert len(f["description"]) > 10 and set(f["parameters"].get("required", [])) <= set(f["parameters"]["properties"])

    def test_unknown_tool_in_a_module(self, planner):
        import chores, expiries, routines, gifts, decisions, weekahead
        for mod in (chores, expiries, routines, gifts, decisions, weekahead):
            assert mod.run_tool("nope", {}).startswith("Unknown ")

    def test_date_properties_are_not_the_shared_backdate_text(self, planner):
        from planner_schemas import ENTRY_DATE_PROP
        for t in planner.TOOLS:
            if t["function"]["name"] in NEW_TOOLS:
                dp = t["function"]["parameters"]["properties"].get("date")
                assert dp is None or dp != ENTRY_DATE_PROP, t["function"]["name"]


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
        assert "trips, chores, expiry dates, routines, gift ideas and decisions" in f[0]["message"]

    def test_chore_problems(self, planner):
        import storage
        storage.save_chores([{"id": "a", "name": "ok", "every": 1, "unit": "days", "start": "2026-10-13"},
                             {"id": "b", "name": "x", "every": "weekly", "unit": "weeks", "start": "2026-10-13"},
                             {"id": "c", "name": "x", "every": 1, "unit": "fortnights", "start": "2026-10-13"},
                             {"id": "d", "name": "x", "every": 1, "unit": "days", "start": "nope"},
                             {"id": "e", "name": "x", "every": 1, "unit": "days", "last_done": "nope"}])
        assert self.warns("chores")[0]["message"].startswith("4 chore(s)")

    def test_expiry_problems(self, planner):
        import storage
        storage.save_expiries([{"id": "a", "date": "2026-11-01"}, {"id": "b", "date": "x"}, {"id": "c"}, {"id": "d", "date": 5}])
        assert self.warns("expiries")[0]["message"].startswith("3 expiry date(s)")

    def test_routine_problems(self, planner):
        import storage
        s = [{"id": "s", "text": "a"}]
        storage.save_routines([{"id": "a", "steps": s}, {"id": "b", "steps": []}, {"id": "c", "steps": "x"},
                               {"id": "d", "steps": s, "days": [9]}, {"id": "e", "steps": s, "days": "mon"}, {"id": "f", "steps": s, "days": [0, 2]}])
        assert self.warns("routines")[0]["message"].startswith("4 routine(s)")

    def test_gift_problems(self, planner):
        import storage
        storage.save_gifts([{"id": "a", "person": "p", "idea": "i", "status": "idea"}, {"id": "b", "person": "p", "idea": "i", "status": "lost"},
                            {"id": "c", "person": "", "idea": "i", "status": "idea"}, {"id": "d", "person": "p", "idea": " ", "status": "idea"}])
        assert self.warns("gifts")[0]["message"].startswith("3 gift idea(s)")

    def test_decision_problems(self, planner):
        import storage
        storage.save_decisions([{"id": "a", "title": "t", "status": "open", "review": "2026-12-01"},
                                {"id": "b", "title": "t", "status": "reviewed", "review": "zz"},
                                {"id": "c", "title": "t", "status": "open", "review": "zz"},
                                {"id": "d", "title": "t", "status": "weird", "review": "2026-12-01"},
                                {"id": "e", "title": "", "status": "open", "review": "2026-12-01"}])
        assert self.warns("decisions")[0]["message"].startswith("3 decision(s)")

    @pytest.mark.parametrize("store", STORES)
    def test_shared_ids(self, planner, store):
        import storage
        storage.save_store(store, [{"id": "x"}, {"id": "x"}, {"id": "y"}])
        assert any("1 id(s) are shared" in f["message"] for f in self.warns(store))

    def test_the_doctor_never_assigns_ids(self, planner):
        import storage
        storage.save_chores([{"name": "x", "every": 1, "unit": "days", "start": "2026-10-13"}])
        self.check()
        assert "id" not in storage.load_chores()[0]


class TestRepairHints:
    def test_each_store_gets_a_concrete_fix(self, planner):
        import storage
        s = [{"id": "s", "text": "a"}]
        storage.save_chores([{"id": "c1", "name": "x", "every": "?", "unit": "days"}])
        storage.save_expiries([{"id": "e1", "name": "x", "date": "zz"}])
        storage.save_routines([{"id": "r1", "name": "x", "steps": []}, {"id": "r2", "name": "y", "steps": s, "days": [9]}])
        storage.save_gifts([{"id": "g1", "person": "p", "idea": "i", "status": "lost"}, {"id": "g2", "person": "", "idea": "i", "status": "idea"}])
        storage.save_decisions([{"id": "d1", "title": "t", "status": "open", "review": "zz"}, {"id": "d2", "title": "t", "status": "x"}])
        out = planner.dispatch_tool("get_repair_suggestions", {})
        for fragment in ("update_chore(chore='c1'", "update_expiry(item='e1'", "update_routine(routine='r1'", "update_routine(routine='r2'",
                         "update_gift_idea(gift='g1'", "delete_gift_idea(gift='g2')", "update_decision(decision='d1'", "delete_decision(decision='d2')"):
            assert fragment in out, fragment


class TestAgendaAndNudges:
    def test_agenda_sections_and_order(self, planner):
        d = planner.dispatch_tool
        d("add_task", {"text": "t", "due": "today"})
        d("add_chore", {"name": "Water plants", "every": "weekly"})
        d("add_expiry", {"name": "Passport", "date": "2026-10-20"})
        d("add_routine", {"name": "Morning", "steps": ["Stretch", "Water"]})
        d("add_person", {"name": "Ayse", "birthday": "10-17"})
        d("add_gift_idea", {"person": "Ayse", "idea": "Book"})
        d("add_decision", {"title": "Desk", "review": "today"})
        out = d("get_today_agenda", {})
        heads = ("Tasks (", "Chores due:", "Expiring soon:", "Routines to finish:", "Gifts to buy:", "Decisions to review:")
        order = [out.index(h) for h in heads]
        assert order == sorted(order)
        assert "Water plants (due today)" in out and "Passport expires in 7 days (2026-10-20)" in out
        assert "Morning: 0 of 2 steps done (next: Stretch)" in out and "Ayse (in 4 days): 1 idea saved, none bought" in out
        assert "Desk (review due today)" in out

    @pytest.mark.parametrize("module", ["chores", "expiries", "routines", "gifts", "decisions"])
    def test_agenda_survives_a_failing_source(self, planner, monkeypatch, module):
        mod = __import__(module)
        monkeypatch.setattr(mod, "agenda_lines", lambda *a, **k: 1 / 0)
        planner.dispatch_tool("add_task", {"text": "t", "due": "today"})
        assert planner.dispatch_tool("get_today_agenda", {}).startswith("Agenda for 2026-10-13")

    @pytest.mark.parametrize("module", ["chores", "expiries", "gifts", "decisions"])
    def test_a_failing_nudge_source_is_ignored(self, planner, monkeypatch, module):
        import nudges
        mod = __import__(module)
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        monkeypatch.setattr(mod, "nudges", lambda *a, **k: 1 / 0)
        assert any("Ayse" in n for n in nudges._planner_nudges())

    def test_new_sources_show_when_the_old_ones_are_quiet(self, planner):
        import nudges
        d = planner.dispatch_tool
        d("add_chore", {"name": "Water plants", "every": "weekly"})
        d("add_expiry", {"name": "Passport", "date": "2026-10-20"})
        d("add_decision", {"title": "Desk", "review": "today"})
        assert nudges._planner_nudges() == ["Chore 'Water plants' is due today.", "Passport expires in 7 days (2026-10-20).",
                                            "Time to review your decision 'Desk'."]

    def test_the_cap_still_holds_and_old_sources_come_first(self, planner):
        import nudges
        d = planner.dispatch_tool
        d("add_task", {"text": "old", "due": "2026-10-01"})
        d("add_subscription", {"name": "N", "amount": 15, "next_date": "2026-10-14"})
        d("add_person", {"name": "Ayse", "birthday": "10-14"})
        d("add_chore", {"name": "Water plants", "every": "weekly"})
        got = nudges._planner_nudges()
        assert len(got) == 3 and not any("Chore" in n for n in got)


class TestCrossModule:
    def test_search_finds_every_new_store(self, planner):
        seed_all(planner)
        for query, area in (("plants", "chores"), ("passport", "expiries"), ("stretch", "routines"), ("poetry", "gifts"), ("desk", "decisions")):
            assert f"{area} (" in planner.dispatch_tool("search_everything", {"query": query}), area

    def test_the_closing_summary_sees_chores_and_decisions(self, planner):
        d = planner.dispatch_tool
        d("add_chore", {"name": "Water plants", "every": "weekly"})
        d("add_decision", {"title": "Desk", "review": "today"})
        out = d("get_closing_summary", {})
        assert "chore: Water plants (due today)" in out and "review decision: Desk" in out
        week = d("get_closing_summary", {"period": "week"})
        assert "1 chore(s) due or overdue" in week

    def test_tomorrows_chores_are_previewed(self, planner):
        planner.dispatch_tool("add_chore", {"name": "Bins", "every": "weekly", "start": "tomorrow"})
        assert "Tomorrow:\n  chore: Bins" in planner.dispatch_tool("get_closing_summary", {})

    def test_week_ahead_sees_the_new_stores(self, planner):
        d = planner.dispatch_tool
        d("add_chore", {"name": "Bins", "every": "weekly", "start": "2026-10-15"})
        d("add_expiry", {"name": "Passport", "date": "2026-10-16"})
        d("add_decision", {"title": "Desk", "review": "2026-10-17"})
        out = d("get_week_ahead", {})
        assert "Chore: Bins" in out and "Expires: Passport" in out and "Review decision: Desk" in out

    def test_gift_bought_flow_with_the_people_list(self, planner):
        d = planner.dispatch_tool
        d("add_person", {"name": "Ayse", "birthday": "10-17"})
        gid = d("add_gift_idea", {"person": "ayse", "idea": "Book"}).split("[id=")[1].split("]")[0]
        assert "no gift is bought yet" in "".join(__import__("nudges")._planner_nudges())
        d("update_gift_idea", {"gift": gid, "fields": {"status": "bought"}})
        assert "no gift is bought yet" not in "".join(__import__("nudges")._planner_nudges())

    def test_completing_a_chore_clears_its_agenda_line(self, planner):
        d = planner.dispatch_tool
        d("add_chore", {"name": "Water plants", "every": "weekly"})
        assert "Chores due:" in d("get_today_agenda", {})
        d("complete_chore", {"chore": "water"})
        assert "Chores due:" not in d("get_today_agenda", {})
        planner.set_now(datetime(2026, 10, 20, 9))
        assert "Water plants (due today)" in d("get_today_agenda", {})

    def test_routine_streak_over_several_days(self, planner):
        d = planner.dispatch_tool
        d("add_routine", {"name": "Morning", "steps": ["Stretch"]})
        for day in (13, 14, 15):
            planner.set_now(datetime(2026, 10, day, 9))
            d("check_routine_step", {"routine": "morning", "step": "all"})
        assert "streak 3 days" in d("get_routines", {})
        planner.set_now(datetime(2026, 10, 17, 9))
        assert "streak" not in d("get_routines", {})
