"""Supplies: what is left and when it runs out."""

from __future__ import annotations

from datetime import datetime

import pytest


def add(p, name="Vitamin D", quantity=30, per_day=1, **kw):
    out = p.dispatch_tool("add_supply", {"name": name, "quantity": quantity, "per_day": per_day, **kw})
    assert out.startswith("Supply added: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_supplies()


def st(item):
    import supplies
    return supplies.status(item)


class TestAdd:
    def test_shape(self, planner):
        sid = add(planner, unit="pills", notes="with food")
        assert rows() == [{"id": sid, "name": "Vitamin D", "quantity": 30.0, "per_day": 1.0, "as_of": "2026-10-13",
                           "unit": "pills", "notes": "with food", "created": "2026-10-13"}]

    def test_output(self, planner):
        out = planner.dispatch_tool("add_supply", {"name": "Vitamin D", "quantity": 30, "per_day": 1,
                                                   "unit": "pills", "as_of": "2026-10-01"})
        assert out.startswith("Supply added: Vitamin D: 18 pills left, 18 days (1/day, runs out 2026-10-31) [id=")

    def test_singular_day(self, planner):
        out = planner.dispatch_tool("add_supply", {"name": "A", "quantity": 1, "per_day": 1})
        assert "1 day (1/day, runs out 2026-10-14)" in out

    def test_zero_quantity_is_allowed(self, planner):
        out = planner.dispatch_tool("add_supply", {"name": "Empty", "quantity": 0, "per_day": 1})
        assert "0 left, ran out" in out

    def test_fractional_use(self, planner):
        out = planner.dispatch_tool("add_supply", {"name": "Half", "quantity": 10, "per_day": 0.5})
        assert "20 days (0.5/day" in out

    @pytest.mark.parametrize("args,msg", [
        ({"name": "", "quantity": 1, "per_day": 1}, "needs a name"), ({"name": 5, "quantity": 1, "per_day": 1}, "needs a name"),
        ({"name": "x" * 61, "quantity": 1, "per_day": 1}, "at most 60"),
        ({"name": "x", "quantity": -1, "per_day": 1}, "cannot be negative"), ({"name": "x", "quantity": "lots", "per_day": 1}, "quantity must be a number"),
        ({"name": "x", "quantity": True, "per_day": 1}, "quantity must be a number"), ({"name": "x", "quantity": None, "per_day": 1}, "quantity must be a number"),
        ({"name": "x", "quantity": 1e9, "per_day": 1}, "not a sensible"),
        ({"name": "x", "quantity": 1, "per_day": 0}, "per_day must be above zero"), ({"name": "x", "quantity": 1, "per_day": -1}, "per_day must be above zero"),
        ({"name": "x", "quantity": 1, "per_day": None}, "per_day must be a number"),
        ({"name": "x", "quantity": 1, "per_day": 1, "unit": 5}, "unit must be text"),
        ({"name": "x", "quantity": 1, "per_day": 1, "unit": "u" * 21}, "at most 20"),
        ({"name": "x", "quantity": 1, "per_day": 1, "as_of": "2026-10-14"}, "in the future"),
        ({"name": "x", "quantity": 1, "per_day": 1, "as_of": "soon"}, "not a valid date")])
    def test_invalid(self, planner, args, msg):
        out = planner.dispatch_tool("add_supply", args)
        assert out.startswith("Supply not added: ") and msg in out and rows() == []

    def test_duplicate_names(self, planner):
        add(planner)
        assert "already a supply called 'VITAMIN D'" in planner.dispatch_tool("add_supply", {"name": "VITAMIN D", "quantity": 1, "per_day": 1})

    def test_limit(self, planner):
        import storage
        storage.save_supplies([{"id": str(i), "name": f"s{i}", "quantity": 1, "per_day": 1, "as_of": "2026-10-13"} for i in range(200)])
        assert "already have 200" in planner.dispatch_tool("add_supply", {"name": "x", "quantity": 1, "per_day": 1})


class TestStatus:
    def item(self, **kw):
        base = {"name": "x", "quantity": 30, "per_day": 1, "as_of": "2026-10-13"}
        base.update(kw)
        return base

    def test_today(self, planner):
        assert st(self.item()) == {"left": 30, "days_left": 30, "runs_out": "2026-11-12"}

    def test_days_pass(self, planner):
        assert st(self.item(as_of="2026-10-03")) == {"left": 20, "days_left": 20, "runs_out": "2026-11-02"}

    def test_the_day_it_runs_out(self, planner):
        assert st(self.item(as_of="2026-09-13")) == {"left": 0, "days_left": 0, "runs_out": "2026-10-13"}

    def test_already_out(self, planner):
        s = st(self.item(as_of="2026-09-01"))
        assert s["left"] == 0 and s["days_left"] == 0 and s["runs_out"] == "2026-10-01"

    def test_fractions_round_down_to_a_tenth(self, planner):
        assert st(self.item(quantity=10, per_day=0.3, as_of="2026-10-10"))["left"] == 9.1

    def test_a_non_whole_number_of_days(self, planner):
        s = st(self.item(quantity=10, per_day=3))
        assert s["days_left"] == 3 and s["runs_out"] == "2026-10-16"

    def test_zero_use_never_runs_out(self, planner):
        assert st(self.item(per_day=0)) == {"left": 30, "days_left": None, "runs_out": None}

    def test_a_future_as_of_does_not_add_stock(self, planner):
        assert st(self.item(as_of="2026-10-20"))["left"] == 30

    @pytest.mark.parametrize("bad", [{"as_of": "x"}, {"as_of": None}, {"quantity": "x"}, {"quantity": -1}, {"per_day": -1},
                                     {"per_day": None}])
    def test_unreadable(self, planner, bad):
        assert st(self.item(**bad)) is None


class TestRefill:
    def test_add_goes_on_top_of_what_is_left(self, planner):
        add(planner, as_of="2026-10-01")  # 18 left today
        out = planner.dispatch_tool("refill_supply", {"supply": "vitamin", "quantity": 30})
        assert out.startswith("Refilled: Vitamin D: 48 left, 48 days (1/day, runs out 2026-11-30)")
        r = rows()[0]
        assert r["quantity"] == 48 and r["as_of"] == "2026-10-13"

    def test_set_replaces_the_count(self, planner):
        add(planner, as_of="2026-10-01")
        planner.dispatch_tool("refill_supply", {"supply": "vitamin", "quantity": 10, "mode": "set"})
        assert rows()[0]["quantity"] == 10

    def test_set_zero(self, planner):
        add(planner)
        out = planner.dispatch_tool("refill_supply", {"supply": "vitamin", "quantity": 0, "mode": "set"})
        assert "ran out" in out and rows()[0]["quantity"] == 0

    def test_add_after_running_out(self, planner):
        add(planner, as_of="2026-09-01")  # ran out on 2026-10-01
        planner.dispatch_tool("refill_supply", {"supply": "vitamin", "quantity": 20})
        assert rows()[0]["quantity"] == 20

    def test_add_zero_is_refused(self, planner):
        add(planner)
        assert "quantity must be above zero" in planner.dispatch_tool("refill_supply", {"supply": "vitamin", "quantity": 0})

    @pytest.mark.parametrize("quantity,mode,msg", [(-1, "add", "above zero"), (5, "top up", "mode must be"),
                                                   ("x", "add", "must be a number"), (None, "set", "must be a number"),
                                                   (-1, "set", "cannot be negative")])
    def test_invalid_changes_nothing(self, planner, quantity, mode, msg):
        add(planner)
        before = rows()
        out = planner.dispatch_tool("refill_supply", {"supply": "vitamin", "quantity": quantity, "mode": mode})
        assert out.startswith("Not refilled: ") and msg in out and rows() == before

    def test_unreadable_item_cannot_be_refilled(self, planner):
        import storage
        storage.save_supplies([{"id": "a", "name": "broken", "quantity": "x", "per_day": 1, "as_of": "2026-10-01"}])
        assert "cannot be read" in planner.dispatch_tool("refill_supply", {"supply": "broken", "quantity": 5})

    def test_refill_moves_the_date_so_the_old_use_is_not_counted_twice(self, planner):
        add(planner, as_of="2026-10-03")  # 20 left
        planner.dispatch_tool("refill_supply", {"supply": "vitamin", "quantity": 10})
        planner.set_now(datetime(2026, 10, 14, 9, 0))
        assert st(rows()[0])["left"] == 29


class TestShow:
    def test_empty(self, planner):
        assert planner.dispatch_tool("get_supplies", {}) == "No supplies tracked yet. Add one with add_supply."

    def test_soonest_first(self, planner):
        add(planner, "Long", 100, 1)
        add(planner, "Soon", 5, 1)
        add(planner, "Middle", 20, 1)
        lines = planner.dispatch_tool("get_supplies", {}).split("\n")
        assert [l[2:].split(":")[0] for l in lines[1:]] == ["Soon", "Middle", "Long"]

    def test_header_counts_low_ones(self, planner):
        add(planner, "A", 3, 1)
        add(planner, "B", 100, 1)
        assert planner.dispatch_tool("get_supplies", {}).split("\n")[0] == "2 supplies, 1 running low (a week or less):"

    def test_header_without_low_ones(self, planner):
        add(planner, "A", 30, 1)
        assert planner.dispatch_tool("get_supplies", {}).split("\n")[0] == "1 supply:"

    def test_unused_items_go_last(self, planner):
        import storage
        add(planner, "Used", 100, 1)
        storage.save_supplies(rows() + [{"id": "z", "name": "Idle", "quantity": 5, "per_day": 0, "as_of": "2026-10-13"}])
        out = planner.dispatch_tool("get_supplies", {})
        assert out.index("Used") < out.index("Idle") and "(not being used)" in out

    def test_ran_out_wording(self, planner):
        add(planner, "Gone", 5, 1, as_of="2026-10-01")
        assert "Gone: 0 left, ran out" in planner.dispatch_tool("get_supplies", {})

    def test_unreadable_rows_are_skipped(self, planner):
        import storage
        storage.save_supplies([{"id": "a", "name": "bad", "quantity": "x", "per_day": 1, "as_of": "2026-10-13"}, "junk", None])
        assert planner.dispatch_tool("get_supplies", {}).startswith("No supplies tracked yet")


class TestUpdateDelete:
    def test_rate_change_applies_from_today(self, planner):
        add(planner, as_of="2026-10-03")  # 20 left at 1/day
        out = planner.dispatch_tool("update_supply", {"supply": "vitamin", "fields": {"per_day": 2}})
        r = rows()[0]
        assert (r["quantity"], r["as_of"], r["per_day"]) == (20, "2026-10-13", 2)
        assert out.startswith("Supply updated: Vitamin D: 20 left, 10 days (2/day")

    def test_other_fields(self, planner):
        add(planner)
        planner.dispatch_tool("update_supply", {"supply": "vitamin", "fields": {"name": "D3", "unit": "caps", "notes": "n"}})
        r = rows()[0]
        assert (r["name"], r["unit"], r["notes"], r["as_of"]) == ("D3", "caps", "n", "2026-10-13")

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"quantity": 5}, "cannot change quantity"),
                                            ({"name": ""}, "needs a name"), ({"per_day": 0}, "above zero"),
                                            ({"unit": 5}, "unit must be text"), ({"notes": 5}, "notes must be text"),
                                            ("x", "nothing to change")])
    def test_invalid_updates_change_nothing(self, planner, fields, msg):
        add(planner)
        before = rows()
        out = planner.dispatch_tool("update_supply", {"supply": "vitamin", "fields": fields})
        assert out.startswith("Supply not changed: ") and msg in out and rows() == before

    def test_rename_onto_an_existing_name(self, planner):
        add(planner, "A")
        add(planner, "B")
        assert "already a supply called 'a'" in planner.dispatch_tool("update_supply", {"supply": "B", "fields": {"name": "a"}})

    def test_resolve_ambiguous_unknown_blank(self, planner):
        add(planner, "Pills one")
        add(planner, "Pills two")
        assert "matches 2 supplies" in planner.dispatch_tool("delete_supply", {"supply": "pills"})
        assert "no supply matches 'zed'" in planner.dispatch_tool("delete_supply", {"supply": "zed"})
        assert "say which supply" in planner.dispatch_tool("refill_supply", {"quantity": 1})

    def test_delete(self, planner):
        add(planner, "A")
        add(planner, "B")
        assert planner.dispatch_tool("delete_supply", {"supply": "a"}) == "Deleted supply A. This can't be undone."
        assert [r["name"] for r in rows()] == ["B"]


class TestNudgesAndAgenda:
    def test_window(self, planner):
        import supplies
        add(planner, "Today", 1.5, 1, as_of="2026-10-12")    # 0.5 left, runs out today
        add(planner, "Tomorrow", 1, 1)                        # runs out tomorrow
        add(planner, "Week", 7, 1)                            # 7 days
        add(planner, "Later", 8, 1)                           # 8 days
        assert supplies.nudges(5) == ["Today runs out today (0.5 left).", "Tomorrow runs out tomorrow (1 left).",
                                      "Week runs out in 7 days (7 left)."]

    def test_already_out(self, planner):
        import supplies
        add(planner, "Gone", 1, 1, as_of="2026-10-01")
        assert supplies.nudges() == ["You have run out of Gone."]

    def test_max_items(self, planner):
        import supplies
        add(planner, "A", 2, 1)
        add(planner, "B", 3, 1)
        assert len(supplies.nudges(1)) == 1

    def test_unused_items_never_nudge(self, planner):
        import supplies
        import storage
        storage.save_supplies([{"id": "z", "name": "Idle", "quantity": 0, "per_day": 0, "as_of": "2026-10-13"}])
        assert supplies.nudges() == []

    def test_agenda_window_is_three_days(self, planner):
        add(planner, "Soon", 3, 1)
        add(planner, "Later", 4, 1)
        out = planner.dispatch_tool("get_today_agenda", {})
        assert "Supplies running out:" in out and "Soon: 3 left" in out and "Later" not in out

    def test_agenda_without_supplies_has_no_section(self, planner):
        assert "Supplies" not in planner.dispatch_tool("get_today_agenda", {})

    def test_in_the_planner_nudges(self, planner):
        import nudges
        add(planner, "Soon", 2, 1)
        assert nudges._planner_nudges() == ["Soon runs out in 2 days (2 left)."]

    def test_time_passing_creates_the_nudge(self, planner):
        import supplies
        add(planner, "Slow", 20, 1)
        assert supplies.nudges() == []
        planner.set_now(datetime(2026, 10, 27, 9, 0))
        assert supplies.nudges() == ["Slow runs out in 6 days (6 left)."]


class TestRobustness:
    def test_not_a_list_store(self, planner):
        import storage
        storage.save_supplies({"x": 1})
        assert planner.dispatch_tool("get_supplies", {}).startswith("No supplies tracked yet")

    def test_handwritten_rows_get_ids(self, planner):
        import storage
        storage.save_supplies([{"name": "legacy", "quantity": 5, "per_day": 1, "as_of": "2026-10-13"}])
        planner.dispatch_tool("get_supplies", {})
        assert storage.load_supplies()[0]["id"]

    def test_not_linked_to_medication_logs(self, planner):
        import storage
        add(planner)
        planner.dispatch_tool("log_medication", {"name": "Vitamin D", "taken": True})
        assert rows()[0]["quantity"] == 30 and len(storage.load_medication()) == 1

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        add(planner)
        path = backup.run_backup()
        storage.save_supplies([])
        restore.restore_backup(path, only="supplies", safety_backup=False)
        assert rows()[0]["name"] == "Vitamin D"

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        assert schemas["add_supply"]["parameters"]["required"] == ["name", "quantity", "per_day"]
        assert schemas["refill_supply"]["parameters"]["required"] == ["supply", "quantity"]
