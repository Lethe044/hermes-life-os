"""Repair suggestions: which entries are broken and the call that fixes each. Read-only."""

from __future__ import annotations

import pytest


def suggestions(p):
    return p.dispatch_tool("get_repair_suggestions", {})


def problems():
    import repair_hints
    return repair_hints.find_problems()


class TestFindProblems:
    def test_clean_data(self, planner):
        planner.dispatch_tool("add_task", {"text": "x", "due": "tomorrow"})
        planner.dispatch_tool("add_trip", {"name": "T", "start": "2026-11-01"})
        assert suggestions(planner) == "No problems found in the planner data, so there is nothing to repair."

    CASES = [
        ("tasks", {"id": "t1", "text": "Buy milk", "due": "soon", "done": False}, "the due date 'soon' cannot be read",
         "update_task(task='t1', fields={'due': 'YYYY-MM-DD'})"),
        ("subscriptions", {"id": "s1", "name": "Gym", "active": True, "next_date": "x", "cycle": "monthly", "amount": 5},
         "no readable renewal date", "update_subscription(subscription='s1', fields={'next_date': 'YYYY-MM-DD'})"),
        ("subscriptions", {"id": "s2", "name": "Gym", "next_date": "2026-11-01", "cycle": "daily", "amount": 5},
         "the cycle 'daily' is not one of", "fields={'cycle': 'monthly'}"),
        ("subscriptions", {"id": "s3", "name": "Gym", "next_date": "2026-11-01", "cycle": "monthly", "amount": -5},
         "the amount is not a positive number", "fields={'amount': 9.99}"),
        ("people", {"id": "p1", "name": "Ana", "birthday": "13-45"}, "the birthday '13-45' cannot be read", "update_person(person='p1'"),
        ("savings", {"id": "g1", "name": "Car", "target": 0}, "the target is not a positive number", "update_savings_goal(goal='g1'"),
        ("savings", {"id": "g2", "name": "Car", "target": 5, "deadline": "later"}, "the deadline 'later' cannot be read", "fields={'deadline': ''}"),
        ("symptoms", {"id": "y1", "symptom": "x", "severity": 11, "date": "2026-10-01"}, "a severity outside 1-10",
         "edit_log(tracker='symptoms', log_id='y1'"),
        ("income", {"id": "i1", "date": "2026-10-01", "amount": 0}, "an amount that is not positive", "delete_log(tracker='income', log_id='i1')"),
        ("body", {"id": "b1", "metric": "mood", "value": 5, "date": "2026-10-01"}, "an unknown metric", "edit_log(tracker='body', log_id='b1'"),
        ("lists", {"id": "l1", "list": "shopping", "text": "  "}, "an item without text", "remove_list_items(item='l1')"),
        ("notes", {"id": "n1", "text": 5}, "a note without text", "delete_note(note='n1')"),
        ("debts", {"id": "d1", "who": "Sam", "amount": 5, "direction": "sideways"}, "an unusable amount or direction", "delete_debt(debt='d1')"),
        ("debts", {"id": "d2", "who": "Sam", "amount": 5, "direction": "owe", "due": "x"}, "the due date 'x' cannot be read", "update_debt(debt='d2'"),
        ("countdowns", {"id": "c1", "name": "Exam", "date": "nope"}, "the date cannot be read", "update_countdown(countdown='c1'"),
        ("supplies", {"id": "u1", "name": "Pills", "quantity": 5, "per_day": 1, "as_of": "x"}, "a count or count date that cannot be read",
         "refill_supply(supply='u1', quantity=10, mode='set')"),
        ("supplies", {"id": "u2", "name": "Pills", "quantity": 5, "per_day": -1, "as_of": "2026-10-01"}, "a daily use that cannot be read",
         "update_supply(supply='u2'"),
        ("timeblocks", {"id": "k1", "date": "2026-10-13", "start": "11:00", "end": "10:00", "title": "Back"}, "an unreadable date, start or end",
         "delete_time_block(block='k1')"),
        ("okrs", {"id": "o1", "name": "Fit", "start": "2026-10-01", "end": "x", "key_results": []}, "an unreadable period", "update_okr(objective='o1'"),
        ("okrs", {"id": "o2", "name": "Fit", "start": "2026-10-01", "end": "2026-12-31",
                  "key_results": [{"id": "r9", "name": "Run", "start_value": 5, "target": 5, "current": 5}]},
         "the key result 'Run' has numbers that cannot be used", "delete_okr(objective='o2', key_result='r9')"),
        ("recipes", {"id": "r1", "name": "Empty", "ingredients": [], "servings": 2}, "no usable ingredients", "delete_recipe(recipe='r1')"),
        ("recipes", {"id": "r2", "name": "Odd", "ingredients": [{"name": "x"}], "servings": 0}, "servings that are not a positive number",
         "fields={'servings': 2}"),
        ("mealplan", {"id": "m1", "date": "2026-10-13", "slot": "brunch", "name": "x"}, "an unreadable date or an unknown slot", "clear_meals(meal='m1')"),
        ("trips", {"id": "z1", "name": "Rome", "start": "2026-10-20", "end": "2026-10-10"}, "unreadable or reversed dates", "update_trip(trip='z1'"),
    ]

    @pytest.mark.parametrize("store,row,problem,fix", CASES, ids=[f"{c[0]}-{c[1]['id']}" for c in CASES])
    def test_each_check(self, planner, store, row, problem, fix):
        import storage
        storage.save_store(store, [row])
        found = problems()
        assert len(found) == 1, found
        p = found[0]
        assert p["area"] == store and p["id"] == row["id"] and problem in p["problem"] and fix in p["fix"]

    @pytest.mark.parametrize("store,row", [(c[0], c[1]) for c in CASES], ids=[f"{c[0]}-{c[1]['id']}" for c in CASES])
    def test_the_doctor_agrees_these_are_problems(self, planner, store, row):
        import storage, doctor
        storage.save_store(store, [row])
        findings = [f for f in doctor.check_planner_data() if f["level"] == "warn"]
        assert findings, f"doctor sees nothing wrong with {row}"

    def test_finished_task_with_a_bad_due_date_is_fine(self, planner):
        import storage
        storage.save_store("tasks", [{"id": "t", "text": "x", "due": "soon", "done": True}])
        assert problems() == []

    def test_cancelled_subscription_is_fine(self, planner):
        import storage
        storage.save_store("subscriptions", [{"id": "s", "name": "x", "active": False, "next_date": "x", "cycle": "?", "amount": 0}])
        assert problems() == []

    def test_goal_rows_of_body_are_fine(self, planner):
        import storage
        storage.save_store("body", [{"id": "b", "type": "goal", "metric": "weight", "target": 70}])
        assert problems() == []

    def test_shared_ids(self, planner):
        import storage
        storage.save_store("notes", [{"id": "same", "text": "a"}, {"id": "same", "text": "b"}, {"id": "other", "text": "c"}])
        p = problems()
        assert len(p) == 1 and p[0]["area"] == "notes" and p[0]["id"] == "same" and "2 entries share this id" in p[0]["problem"]

    def test_entries_without_an_id_are_described_and_not_given_one(self, planner):
        import storage
        storage.save_store("countdowns", [{"name": "Exam", "date": "nope"}])
        p = problems()
        assert p[0]["id"] == "-" and "has no id yet" in p[0]["fix"] and "update_countdown(countdown='(no id yet)'" in p[0]["fix"]
        assert storage.load_store("countdowns") == [{"name": "Exam", "date": "nope"}]

    def test_unreadable_rows(self, planner):
        import storage
        storage.save_store("tasks", ["junk", None, 5])
        storage.save_store("notes", {"not": "a list"})
        assert problems() == []

    def test_a_check_that_crashes_is_reported_not_raised(self, planner):
        import storage
        storage.save_store("okrs", [{"id": "o", "name": "x", "start": "2026-10-01", "end": "2026-10-31", "key_results": [{"id": "k", "start_value": [1]}]}])
        assert len(problems()) == 1

    def test_never_writes(self, planner):
        import storage
        storage.save_store("tasks", [{"text": "no id", "due": "soon"}, {"id": "a", "text": "ok", "due": "x", "done": False}])
        storage.save_store("countdowns", [{"id": "c", "name": "n", "date": "nope"}])
        before = {n: storage.load_store(n) for n in storage.data_store_names()}
        suggestions(planner)
        assert {n: storage.load_store(n) for n in storage.data_store_names()} == before


class TestOutput:
    def test_format(self, planner):
        import storage
        storage.save_store("tasks", [{"id": "t1", "text": "Buy milk", "due": "soon", "done": False}])
        storage.save_store("countdowns", [{"id": "c1", "name": "Exam", "date": "nope"}])
        assert suggestions(planner) == (
            "2 problems found in your planner data. Nothing was changed; each fix is a normal tool call:\n"
            "- tasks [id=t1] 'Buy milk': the due date 'soon' cannot be read.\n"
            "    Fix: update_task(task='t1', fields={'due': 'YYYY-MM-DD'}) or fields={'due': ''} to clear it\n"
            "- countdowns [id=c1] 'Exam': the date cannot be read.\n"
            "    Fix: update_countdown(countdown='c1', fields={'date': 'YYYY-MM-DD'})")

    def test_one_problem_is_singular(self, planner):
        import storage
        storage.save_store("notes", [{"id": "n", "text": ""}])
        assert suggestions(planner).startswith("1 problem found in your planner data.")

    def test_long_names_are_shortened(self, planner):
        import repair_hints
        assert repair_hints.label({"name": "n" * 60}) == "'" + "n" * 40 + "'..."
        assert repair_hints.label({}) == "(no name)"

    def test_long_lists_are_cut(self, planner):
        import storage
        storage.save_store("notes", [{"id": f"n{i}", "text": ""} for i in range(35)])
        out = suggestions(planner)
        assert out.startswith("35 problems found") and out.count("\n- notes") == 30 and out.endswith("... and 5 more.")

    def test_doctor_points_at_the_tool(self, planner):
        planner.dispatch_tool("add_note", {"text": "x"})
        import doctor
        assert "get_repair_suggestions" in doctor.check_planner_data()[0]["message"]
