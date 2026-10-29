"""Income, debts, countdowns and supplies together: doctor, registry, dispatch, nudge ordering."""

from __future__ import annotations

import pytest

STORES = ["income", "debts", "countdowns", "supplies"]


class TestDoctor:
    def check(self):
        import doctor
        return doctor.check_planner_data()

    def warns(self, area):
        return [f for f in self.check() if f["area"] == area and f["level"] == "warn"]

    def test_clean_data_is_ok(self, planner):
        planner.dispatch_tool("log_income", {"amount": 5})
        planner.dispatch_tool("add_debt", {"who": "A", "amount": 5, "direction": "owe", "due": "2026-11-01"})
        planner.dispatch_tool("add_countdown", {"name": "x", "date": "2026-12-01"})
        planner.dispatch_tool("add_supply", {"name": "s", "quantity": 5, "per_day": 1})
        f = self.check()
        assert [x["level"] for x in f] == ["ok"]
        assert "countdowns, supplies, time blocks, objectives, recipes, the meal plan and trips are all readable" in f[0]["message"]

    def test_income_problems(self, planner):
        import storage
        storage.save_income([{"id": "a", "date": "2026-10-01", "amount": 5},
                             {"id": "b", "date": "2026-10-01", "amount": 0}, {"id": "c", "date": "2026-10-01", "amount": -3},
                             {"id": "d", "date": "2026-10-01", "amount": "x"}, {"id": "e", "date": "nope", "amount": 5},
                             {"id": "f", "date": "2026-10-01", "amount": True}])
        w = self.warns("income")
        assert len(w) == 1 and w[0]["message"].startswith("5 income entries")

    def test_debt_problems(self, planner):
        import storage
        storage.save_debts([{"id": "a", "who": "x", "direction": "owe", "amount": 5, "due": "2026-11-01"},
                            {"id": "b", "who": "x", "direction": "owe", "amount": 0},
                            {"id": "c", "who": "x", "direction": "sideways", "amount": 5},
                            {"id": "d", "who": "x", "direction": "owed", "amount": 5, "due": "soon"},
                            {"id": "e", "who": "x", "direction": "owed", "amount": "x"}])
        w = self.warns("debts")
        assert len(w) == 1 and w[0]["message"].startswith("4 debt(s)")

    def test_countdown_problems(self, planner):
        import storage
        storage.save_countdowns([{"id": "a", "name": "ok", "date": "2026-12-01"}, {"id": "b", "name": "bad", "date": "x"},
                                 {"id": "c", "name": "none"}])
        assert self.warns("countdowns")[0]["message"].startswith("2 countdown(s)")

    def test_supply_problems(self, planner):
        import storage
        storage.save_supplies([{"id": "a", "name": "ok", "quantity": 5, "per_day": 1, "as_of": "2026-10-13"},
                               {"id": "b", "name": "x", "quantity": "x", "per_day": 1, "as_of": "2026-10-13"},
                               {"id": "c", "name": "x", "quantity": 5, "per_day": -1, "as_of": "2026-10-13"},
                               {"id": "d", "name": "x", "quantity": 5, "per_day": 1, "as_of": "nope"},
                               {"id": "e", "name": "x", "quantity": -5, "per_day": 1, "as_of": "2026-10-13"}])
        assert self.warns("supplies")[0]["message"].startswith("4 supply item(s)")

    @pytest.mark.parametrize("store", STORES)
    def test_shared_ids(self, planner, store):
        import storage
        storage.save_store(store, [{"id": "a"}, {"id": "a"}])
        assert any("shared by more than one entry" in x["message"] for x in self.warns(store))

    @pytest.mark.parametrize("store", STORES)
    def test_malformed_stores_do_not_crash(self, planner, store):
        import storage
        storage.save_store(store, {"not": "a list"})
        assert [x["level"] for x in self.check()] == ["ok"]
        storage.save_store(store, ["junk", None, 5])
        assert [x["level"] for x in self.check()] == ["ok"]

    def test_read_only(self, planner):
        import storage
        for name in STORES:
            storage.save_store(name, [{"note": "no id"}])
        self.check()
        assert all("id" not in storage.load_store(n)[0] for n in STORES)

    def test_income_journal_links_are_not_orphans(self, planner):
        import doctor
        planner.dispatch_tool("log_income", {"amount": 5})
        assert [f["level"] for f in doctor.check_entry_ids()] == ["ok"]

    def test_a_removed_income_row_orphans_its_journal_entry(self, planner):
        import doctor, storage
        planner.dispatch_tool("log_income", {"amount": 5})
        storage.save_income([])
        assert any(f["level"] == "warn" for f in doctor.check_entry_ids())

    def test_future_dated_income_is_flagged(self, planner):
        import doctor, storage
        storage.save_income([{"id": "a", "date": "2031-01-01", "amount": 5}])
        assert any(x["area"] == "income" and x["level"] == "warn" for x in doctor.check_future_dates())


class TestRegistry:
    @pytest.mark.parametrize("store", STORES)
    def test_registered(self, planner, store):
        import storage
        assert store in storage.DATA_STORES and storage.data_store_path(store).name == f"{store}.json"
        assert storage.load_store(store) == []

    def test_export_contains_them(self, planner):
        import data_export
        planner.dispatch_tool("log_income", {"amount": 5})
        planner.dispatch_tool("add_countdown", {"name": "x", "date": "2026-12-01"})
        data = data_export.build_backup_payload()
        assert data["income"][0]["amount"] == 5 and data["countdowns"][0]["name"] == "x"
        assert data["debts"] == [] and data["supplies"] == []

    def test_profiles_are_separate(self, planner):
        import storage
        planner.dispatch_tool("add_countdown", {"name": "default", "date": "2026-12-01"})
        storage.set_active_profile("alex")
        try:
            assert planner.dispatch_tool("get_countdowns", {}).startswith("No countdowns yet")
        finally:
            storage.set_active_profile(None)
        assert planner.dispatch_tool("get_countdowns", {}).startswith("1 countdown:")


class TestDispatch:
    @pytest.mark.parametrize("name", ["log_income", "get_cash_flow", "add_debt", "record_debt_payment", "get_debts",
                                      "update_debt", "delete_debt", "add_countdown", "get_countdowns",
                                      "update_countdown", "delete_countdown", "add_supply", "refill_supply",
                                      "get_supplies", "update_supply", "delete_supply"])
    def test_every_tool_is_dispatched_and_never_raises_on_empty_input(self, planner, name):
        out = planner.dispatch_tool(name, {})
        assert isinstance(out, str) and out and not out.startswith("Unknown")

    def test_every_new_schema_is_wired_to_a_module(self, planner):
        from planner_schemas import INCOME_SCHEMAS, DEBT_SCHEMAS, COUNTDOWN_SCHEMAS, SUPPLY_SCHEMAS, TOOL_MODULES
        for schemas, module in ((INCOME_SCHEMAS, "income"), (DEBT_SCHEMAS, "debts"),
                                (COUNTDOWN_SCHEMAS, "countdowns"), (SUPPLY_SCHEMAS, "supplies")):
            for s in schemas:
                assert TOOL_MODULES[s["function"]["name"]] == module

    def test_tool_names_are_unique_and_required_are_properties(self, planner):
        names = [t["function"]["name"] for t in planner.TOOLS]
        assert len(names) == len(set(names))
        for t in planner.TOOLS:
            params = t["function"]["parameters"]
            assert set(params.get("required", [])) <= set(params.get("properties", {})), t["function"]["name"]

    def test_unknown_tool_in_a_module(self, planner):
        import income, debts, countdowns, supplies
        for mod in (income, debts, countdowns, supplies):
            assert mod.run_tool("nope", {}).startswith("Unknown ")


class TestNudgeOrdering:
    def test_cap_is_three(self, planner):
        import nudges
        assert nudges.MAX_PLANNER_NUDGES == 3
        planner.dispatch_tool("add_task", {"text": "old", "due": "2026-10-01"})
        planner.dispatch_tool("add_subscription", {"name": "N", "amount": 15, "next_date": "2026-10-14"})
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        planner.dispatch_tool("add_debt", {"who": "Ali", "amount": 5, "direction": "owe", "due": "2026-10-14"})
        planner.dispatch_tool("add_countdown", {"name": "Exam", "date": "2026-10-14"})
        planner.dispatch_tool("add_supply", {"name": "S", "quantity": 2, "per_day": 1})
        got = nudges._planner_nudges()
        assert len(got) == 3 and "old" in got[0] and "N renews" in got[1] and "Ayse" in got[2]

    def test_new_sources_show_when_the_old_ones_are_quiet(self, planner):
        import nudges
        planner.dispatch_tool("add_debt", {"who": "Ali", "amount": 5, "direction": "owe", "due": "2026-10-14"})
        planner.dispatch_tool("add_countdown", {"name": "Exam", "date": "2026-10-14"})
        planner.dispatch_tool("add_supply", {"name": "S", "quantity": 2, "per_day": 1})
        assert nudges._planner_nudges() == ["You owe Ali 5: due tomorrow.", "Exam is tomorrow.",
                                            "S runs out in 2 days (2 left)."]

    @pytest.mark.parametrize("module", ["debts", "countdowns", "supplies"])
    def test_a_failing_source_is_ignored(self, planner, monkeypatch, module):
        import nudges
        mod = __import__(module)
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        monkeypatch.setattr(mod, "nudges", lambda *a, **k: 1 / 0)
        assert any("Ayse" in n for n in nudges._planner_nudges())

    @pytest.mark.parametrize("module", ["debts", "countdowns", "supplies"])
    def test_agenda_survives_a_failing_source(self, planner, monkeypatch, module):
        mod = __import__(module)
        for attr in ("due_soon", "within", "running_low"):
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, lambda *a, **k: 1 / 0)
        assert planner.dispatch_tool("get_today_agenda", {}).startswith("Agenda for 2026-10-13")

    def test_agenda_section_order(self, planner):
        planner.dispatch_tool("add_task", {"text": "t", "due": "today"})
        planner.dispatch_tool("add_savings_goal", {"name": "g", "target": 10, "deadline": "2026-10-20"})
        planner.dispatch_tool("add_debt", {"who": "Ali", "amount": 5, "direction": "owe", "due": "2026-10-14"})
        planner.dispatch_tool("add_countdown", {"name": "Exam", "date": "2026-10-14"})
        planner.dispatch_tool("add_supply", {"name": "S", "quantity": 2, "per_day": 1})
        out = planner.dispatch_tool("get_today_agenda", {})
        order = [out.index(h) for h in ("Tasks (", "Savings goals", "Debts due:", "Countdowns:", "Supplies running out:")]
        assert order == sorted(order)
