"""Savings goals: target, contributions, pace, deadline maths, nudges."""

from __future__ import annotations

from datetime import datetime

import pytest


def goal(p, name="Holiday", target=2400, **kw):
    out = p.dispatch_tool("add_savings_goal", {"name": name, "target": target, **kw})
    assert out.startswith("Savings goal added: "), out
    return out.split("[id=")[1].split("]")[0]


def put(p, amount, ref="holiday", **kw):
    return p.dispatch_tool("contribute_to_savings", {"goal": ref, "amount": amount, **kw})


def rows():
    import storage
    return storage.load_savings()


class TestAdd:
    def test_minimal(self, planner):
        gid = goal(planner)
        assert rows() == [{"id": gid, "name": "Holiday", "target": 2400.0, "saved": 0.0, "deadline": None,
                           "created": "2026-10-13", "completed": None, "notes": "", "history": []}]

    def test_output(self, planner):
        out = planner.dispatch_tool("add_savings_goal", {"name": "Holiday", "target": 2400,
                                                         "deadline": "2027-06-01", "saved": 200})
        assert out.startswith("Savings goal added: Holiday: 200 of 2,400 (8.3%), 2,200 to go [id=")
        assert out.endswith("deadline 2027-06-01 (231 days)")

    def test_starting_balance_is_the_first_history_entry(self, planner):
        goal(planner, saved=150)
        r = rows()[0]
        assert r["saved"] == 150 and r["history"] == [
            {"date": "2026-10-13", "amount": 150.0, "note": "starting balance", "start": True}]

    def test_zero_starting_balance_means_none(self, planner):
        goal(planner, saved=0)
        assert rows()[0]["history"] == []

    def test_name_is_trimmed_and_collapsed(self, planner):
        goal(planner, name="  New   car ")
        assert rows()[0]["name"] == "New car"

    def test_duplicate_names_refused_case_insensitively(self, planner):
        goal(planner)
        assert "already a goal called 'HOLIDAY'" in planner.dispatch_tool("add_savings_goal", {"name": "HOLIDAY", "target": 5})
        assert len(rows()) == 1

    @pytest.mark.parametrize("args,msg", [
        ({"name": "", "target": 5}, "needs a name"), ({"name": 5, "target": 5}, "needs a name"),
        ({"name": "x" * 61, "target": 5}, "at most 60"), ({"name": "x", "target": 0}, "cannot be zero"),
        ({"name": "x", "target": -5}, "more than zero"), ({"name": "x", "target": "lots"}, "must be a number"),
        ({"name": "x", "target": True}, "must be a number"), ({"name": "x", "target": None}, "must be a number"),
        ({"name": "x", "target": float("inf")}, "not a sensible amount"), ({"name": "x", "target": 1e13}, "not a sensible amount"),
        ({"name": "x", "target": 5, "deadline": "soon"}, "not a valid date"),
        ({"name": "x", "target": 5, "saved": -1}, "cannot be negative"),
        ({"name": "x", "target": 5, "saved": "x"}, "must be a number")])
    def test_invalid(self, planner, args, msg):
        out = planner.dispatch_tool("add_savings_goal", args)
        assert out.startswith("Goal not added: ") and msg in out and rows() == []

    def test_amounts_are_rounded_to_cents(self, planner):
        goal(planner, target=100.456)
        assert rows()[0]["target"] == 100.46

    def test_limit(self, planner):
        import storage
        storage.save_savings([{"id": str(i), "name": f"g{i}", "target": 1} for i in range(100)])
        assert "already have 100" in planner.dispatch_tool("add_savings_goal", {"name": "x", "target": 1})


class TestContribute:
    def test_adding_money(self, planner):
        goal(planner)
        out = put(planner, 300, note="bonus")
        assert out.startswith("Added 300 to savings. Holiday: 300 of 2,400 (12.5%), 2,100 to go")
        r = rows()[0]
        assert r["saved"] == 300 and r["history"] == [{"date": "2026-10-13", "amount": 300.0, "note": "bonus"}]

    def test_taking_money_out(self, planner):
        goal(planner, saved=500)
        out = put(planner, -200)
        assert out.startswith("Took 200 out of savings. Holiday: 300 of 2,400")
        assert rows()[0]["saved"] == 300

    def test_cannot_take_out_more_than_saved(self, planner):
        goal(planner, saved=100)
        out = put(planner, -150)
        assert out == "Not recorded: you only have 100 saved for Holiday, so 150 cannot be taken out."
        assert rows()[0]["saved"] == 100

    def test_taking_out_exactly_everything(self, planner):
        goal(planner, saved=100)
        put(planner, -100)
        assert rows()[0]["saved"] == 0

    def test_backdated_and_kept_in_order(self, planner):
        goal(planner)
        put(planner, 10)
        put(planner, 20, date="2026-09-01")
        assert [h["date"] for h in rows()[0]["history"]] == ["2026-09-01", "2026-10-13"]

    @pytest.mark.parametrize("date,msg", [("2026-10-14", "in the future"), ("soon", "not a valid date"),
                                         ("2020-01-01", "more than")])
    def test_bad_dates(self, planner, date, msg):
        goal(planner)
        out = put(planner, 10, date=date)
        assert out.startswith("Not recorded: ") and msg in out and rows()[0]["history"] == []

    @pytest.mark.parametrize("amount,msg", [(0, "cannot be zero"), ("x", "must be a number"), (None, "must be a number"),
                                           (True, "must be a number"), (1e13, "not a sensible amount"),
                                           (0.001, "cannot be zero")])
    def test_bad_amounts(self, planner, amount, msg):
        goal(planner)
        out = put(planner, amount)
        assert out.startswith("Not recorded: ") and msg in out

    def test_numeric_string_is_accepted(self, planner):
        goal(planner)
        assert put(planner, "50.5").startswith("Added 50.50 to savings.")
        assert rows()[0]["saved"] == 50.5

    def test_float_sums_do_not_drift(self, planner):
        goal(planner, target=1000)
        for _ in range(10):
            put(planner, 0.1)
        assert rows()[0]["saved"] == 1.0

    def test_reaching_the_target(self, planner):
        goal(planner, target=100, saved=60)
        out = put(planner, 40)
        assert out.endswith("Goal reached - well done!")
        assert rows()[0]["completed"] == "2026-10-13"

    def test_reached_message_only_once(self, planner):
        goal(planner, target=100, saved=100)
        assert "well done" not in put(planner, 10)

    def test_going_below_the_target_reopens_it(self, planner):
        goal(planner, target=100, saved=100)
        assert rows()[0]["completed"] == "2026-10-13"
        put(planner, -10)
        assert rows()[0]["completed"] is None
        assert put(planner, 10).endswith("Goal reached - well done!")

    def test_over_target_percentage(self, planner):
        goal(planner, target=100, saved=250)
        assert "250 of 100 (250%)" in planner.dispatch_tool("get_savings", {})

    def test_history_limit(self, planner):
        import storage
        goal(planner, target=10 ** 6)
        g = rows()
        g[0]["history"] = [{"date": "2026-10-01", "amount": 1.0}] * 1000
        storage.save_savings(g)
        assert "already has 1000 entries" in put(planner, 1)

    def test_unknown_and_ambiguous_goals(self, planner):
        goal(planner, "Holiday fund")
        goal(planner, "Holiday car")
        assert "matches 2 goals" in put(planner, 5, ref="holiday")
        assert "no savings goal matches 'zzz'" in put(planner, 5, ref="zzz")
        assert "say which savings goal" in put(planner, 5, ref="")
        assert all(r["saved"] == 0 for r in rows())

    def test_exact_name_beats_a_longer_match(self, planner):
        goal(planner, "Car")
        goal(planner, "Car repairs")
        assert put(planner, 5, ref="car").startswith("Added 5 to savings. Car: 5")


class TestProgress:
    def prog(self, planner, ref="holiday"):
        import savings
        return savings.progress(savings._resolve(savings._load(), ref))

    def test_no_history_has_no_pace(self, planner):
        goal(planner)
        p = self.prog(planner)
        assert p["pace_per_day"] is None and p["eta"] is None and p["status"] == "no_pace" and p["percent"] == 0

    def test_one_day_of_history_has_no_pace(self, planner):
        goal(planner)
        put(planner, 100)
        put(planner, 100)
        assert self.prog(planner)["pace_per_day"] is None

    def test_pace_and_eta(self, planner):
        goal(planner, target=1000)
        put(planner, 100, date="2026-09-13")
        put(planner, 100)  # 200 over 30 days
        p = self.prog(planner)
        assert p["pace_per_day"] == pytest.approx(200 / 30, abs=1e-3)
        assert p["remaining"] == 800 and p["eta"] == "2027-02-10"  # ceil(800 / 6.6667) = 120 days

    def test_starting_balance_is_not_pace(self, planner):
        goal(planner, target=1000, saved=500)
        put(planner, 30, date="2026-09-13")
        put(planner, 30)
        assert self.prog(planner)["pace_per_day"] == pytest.approx(2.0, abs=1e-3)  # 60 over 30 days

    def test_pace_window_is_90_days(self, planner):
        goal(planner, target=10000)
        put(planner, 1000, date="2026-03-01")   # outside the window
        put(planner, 90, date="2026-07-15")     # 90 days before today = 2026-07-15
        put(planner, 0.5)
        p = self.prog(planner)
        assert p["pace_per_day"] == pytest.approx(90.5 / 90, abs=1e-3)

    def test_withdrawals_reduce_pace(self, planner):
        goal(planner, target=1000)
        put(planner, 300, date="2026-09-13")
        put(planner, -300)
        p = self.prog(planner)
        assert p["pace_per_day"] == 0 and p["eta"] is None

    def test_on_track(self, planner):
        goal(planner, target=1000, deadline="2027-12-31")
        put(planner, 100, date="2026-09-13")
        put(planner, 100)
        assert self.prog(planner)["status"] == "on_track"

    def test_behind(self, planner):
        goal(planner, target=10000, deadline="2026-12-31")
        put(planner, 10, date="2026-09-13")
        put(planner, 10)
        p = self.prog(planner)
        assert p["status"] == "behind" and p["days_left"] == 79

    def test_needed_per_month(self, planner):
        goal(planner, target=2400, deadline="2027-10-13", saved=0)
        p = self.prog(planner)
        assert p["days_left"] == 365 and p["needed_per_month"] == pytest.approx(2400 / (365 / 30.4375), abs=0.01)

    def test_no_needed_per_month_without_a_future_deadline(self, planner):
        goal(planner, deadline="2026-10-13")
        assert self.prog(planner)["needed_per_month"] is None

    def test_overdue(self, planner):
        goal(planner, target=100, deadline="2026-10-01")
        assert self.prog(planner)["status"] == "overdue"

    def test_reached_beats_everything(self, planner):
        goal(planner, target=100, deadline="2026-10-01", saved=100)
        assert self.prog(planner)["status"] == "reached"

    def test_no_deadline_with_pace(self, planner):
        goal(planner, target=1000)
        put(planner, 100, date="2026-09-13")
        put(planner, 100)
        assert self.prog(planner)["status"] == "no_deadline"

    def test_unreadable_deadline_is_ignored(self, planner):
        import storage
        goal(planner)
        g = rows()
        g[0]["deadline"] = "garbage"
        storage.save_savings(g)
        p = self.prog(planner)
        assert p["days_left"] is None and p["status"] == "no_pace"

    def test_zero_target_does_not_divide_by_zero(self, planner):
        import savings
        assert savings.progress({"target": 0, "history": []})["percent"] == 0


class TestShow:
    def test_empty(self, planner):
        assert planner.dispatch_tool("get_savings", {}) == "No savings goals yet. Start one with add_savings_goal."

    def test_overview_totals_and_order(self, planner):
        goal(planner, "Later", 1000, deadline="2028-01-01", saved=100)
        goal(planner, "Soon", 500, deadline="2026-12-01", saved=50)
        goal(planner, "Done", 10, saved=10)
        lines = planner.dispatch_tool("get_savings", {}).split("\n")
        assert lines[0] == "3 savings goals - 160 saved of 1,510:"
        assert [l.split(":")[0] for l in lines[1:]] == ["- Soon", "- Later", "- Done"]

    def test_detail(self, planner):
        goal(planner, target=2400, deadline="2027-06-01")
        put(planner, 300, date="2026-09-13", note="bonus")
        put(planner, 100)
        out = planner.dispatch_tool("get_savings", {"goal": "holiday"})
        assert "Status: on track for the deadline." in out
        assert "Pace: 405.83 per month." in out
        assert "At this pace you reach it on 2027-03-12." in out
        assert "To make the deadline put aside 263.53 per month." in out
        assert "Recent: 2026-10-13 +100; 2026-09-13 +300 (bonus)" in out

    def test_detail_for_a_reached_goal(self, planner):
        goal(planner, target=100, saved=100)
        out = planner.dispatch_tool("get_savings", {"goal": "holiday"})
        assert "Status: goal reached." in out and "Reached on 2026-10-13." in out

    def test_detail_for_an_unknown_goal(self, planner):
        assert planner.dispatch_tool("get_savings", {"goal": "zzz"}).startswith("Cannot show savings: no savings goal")

    def test_a_stalled_pace_is_flagged(self, planner):
        goal(planner, target=1000)
        put(planner, 100, date="2026-09-13")
        put(planner, -100)
        assert "(not moving forward)" in planner.dispatch_tool("get_savings", {"goal": "holiday"})


class TestUpdateDelete:
    def test_update(self, planner):
        goal(planner)
        out = planner.dispatch_tool("update_savings_goal", {"goal": "holiday", "fields": {
            "name": "Trip", "target": 3000, "deadline": "2027-01-01", "notes": "n"}})
        assert out.startswith("Savings goal updated: Trip: 0 of 3,000")
        r = rows()[0]
        assert (r["name"], r["target"], r["deadline"], r["notes"]) == ("Trip", 3000.0, "2027-01-01", "n")

    def test_clear_deadline(self, planner):
        goal(planner, deadline="2027-01-01")
        planner.dispatch_tool("update_savings_goal", {"goal": "holiday", "fields": {"deadline": ""}})
        assert rows()[0]["deadline"] is None

    def test_lowering_the_target_completes_the_goal(self, planner):
        goal(planner, target=1000, saved=300)
        planner.dispatch_tool("update_savings_goal", {"goal": "holiday", "fields": {"target": 250}})
        assert rows()[0]["completed"] == "2026-10-13"

    def test_raising_the_target_reopens_it(self, planner):
        goal(planner, target=100, saved=100)
        planner.dispatch_tool("update_savings_goal", {"goal": "holiday", "fields": {"target": 500}})
        assert rows()[0]["completed"] is None

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"saved": 5}, "cannot change saved"),
                                            ({"name": ""}, "needs a name"), ({"target": 0}, "cannot be zero"),
                                            ({"target": -1}, "more than zero"), ({"deadline": "x"}, "not a valid date"),
                                            ({"notes": 5}, "notes must be text"), ("x", "nothing to change")])
    def test_invalid_updates_change_nothing(self, planner, fields, msg):
        goal(planner)
        before = rows()
        out = planner.dispatch_tool("update_savings_goal", {"goal": "holiday", "fields": fields})
        assert out.startswith("Goal not changed: ") and msg in out and rows() == before

    def test_rename_onto_an_existing_name(self, planner):
        goal(planner, "A")
        goal(planner, "B")
        assert "already a goal called 'a'" in planner.dispatch_tool("update_savings_goal", {"goal": "B", "fields": {"name": "a"}})

    def test_rename_to_its_own_name_in_another_case(self, planner):
        goal(planner, "Holiday")
        planner.dispatch_tool("update_savings_goal", {"goal": "holiday", "fields": {"name": "HOLIDAY"}})
        assert rows()[0]["name"] == "HOLIDAY"

    def test_delete(self, planner):
        goal(planner, "A")
        goal(planner, "B")
        assert planner.dispatch_tool("delete_savings_goal", {"goal": "a"}) == "Deleted savings goal A. This can't be undone."
        assert [r["name"] for r in rows()] == ["B"]


class TestNudges:
    def test_close_deadline(self, planner):
        import savings
        goal(planner, target=1000, deadline="2026-10-20", saved=400)
        assert savings.nudges() == ["Savings goal 'Holiday' is 40% there with 7 days left: 600 to go."]

    def test_one_day_left_wording(self, planner):
        import savings
        goal(planner, target=100, deadline="2026-10-14")
        assert "with 1 day left" in savings.nudges()[0]

    def test_far_deadline_no_deadline_and_reached_are_quiet(self, planner):
        import savings
        goal(planner, "far", 100, deadline="2026-12-31")
        goal(planner, "none", 100)
        goal(planner, "done", 100, deadline="2026-10-14", saved=100)
        assert savings.nudges() == []

    def test_recently_passed_deadline(self, planner):
        import savings
        goal(planner, target=100, deadline="2026-10-10")
        assert "3 day(s) past its deadline" in savings.nudges()[0]

    def test_long_passed_deadline_is_quiet(self, planner):
        import savings
        goal(planner, target=100, deadline="2026-09-01")
        assert savings.nudges() == []

    def test_closest_deadline_first_and_limited(self, planner):
        import savings
        goal(planner, "b", 100, deadline="2026-10-25")
        goal(planner, "a", 100, deadline="2026-10-15")
        out = savings.nudges(5)
        assert "'a'" in out[0] and "'b'" in out[1]
        assert len(savings.nudges(1)) == 1

    def test_agenda_section(self, planner):
        goal(planner, target=1000, deadline="2026-10-20", saved=400)
        out = planner.dispatch_tool("get_today_agenda", {})
        assert "Savings goals with a close deadline:" in out and "40% there with 7 days left" in out

    def test_agenda_without_savings_is_unchanged(self, planner):
        assert "Savings" not in planner.dispatch_tool("get_today_agenda", {})

    def test_proactive_nudges_include_it(self, planner):
        import nudges
        goal(planner, target=1000, deadline="2026-10-20", saved=400)
        assert any("Savings goal 'Holiday'" in n for n in nudges.generate_nudges())


class TestRobustness:
    def test_handwritten_rows(self, planner):
        import storage
        storage.save_savings([{"name": "legacy", "target": 100}, "junk", None,
                              {"id": "k", "name": "k", "target": 50, "history": ["x", {"amount": "y"}, {"date": "2026-10-01", "amount": 5}]}])
        out = planner.dispatch_tool("get_savings", {})
        assert out.startswith("2 savings goals - 5 saved of 150:")
        assert all(r["id"] for r in storage.load_savings() if isinstance(r, dict))

    def test_not_a_list_store(self, planner):
        import storage
        storage.save_savings({"x": 1})
        assert planner.dispatch_tool("get_savings", {}).startswith("No savings goals yet")

    def test_does_not_touch_expenses_or_the_journal(self, planner):
        import storage
        goal(planner, saved=100)
        put(planner, 50)
        assert storage.load_spending() == [] and storage.get_all_memory() == []

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        goal(planner, saved=10)
        path = backup.run_backup()
        storage.save_savings([])
        restore.restore_backup(path, only="savings", safety_backup=False)
        assert rows()[0]["name"] == "Holiday"

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        for n in ("add_savings_goal", "contribute_to_savings", "get_savings", "update_savings_goal",
                  "delete_savings_goal"):
            assert n in schemas
        assert schemas["contribute_to_savings"]["parameters"]["required"] == ["goal", "amount"]
        assert "date" in schemas["contribute_to_savings"]["parameters"]["properties"]
