"""Debts and IOUs."""

from __future__ import annotations

import pytest


def add(p, who="Ali", amount=500, direction="owe", **kw):
    out = p.dispatch_tool("add_debt", {"who": who, "amount": amount, "direction": direction, **kw})
    assert out.startswith("Debt added: "), out
    return out.split("[id=")[1].split("]")[0]


def pay(p, ref="ali", amount=100, **kw):
    return p.dispatch_tool("record_debt_payment", {"debt": ref, "amount": amount, **kw})


def rows():
    import storage
    return storage.load_debts()


class TestAdd:
    def test_shape(self, planner):
        did = add(planner, due="2026-10-15", notes="car")
        assert rows() == [{"id": did, "who": "Ali", "direction": "owe", "amount": 500.0, "paid": 0.0,
                           "due": "2026-10-15", "created": "2026-10-13", "notes": "car", "payments": [], "settled": None}]

    def test_output_and_due_wording(self, planner):
        out = planner.dispatch_tool("add_debt", {"who": "Ali", "amount": 500, "direction": "owe", "due": "2026-10-15"})
        assert out.startswith("Debt added: you owe Ali 500, due 2026-10-15 (due in 2 day(s)) [id=")
        out = planner.dispatch_tool("add_debt", {"who": "Mehmet", "amount": 120.5, "direction": "owed"})
        assert out.startswith("Debt added: Mehmet owes you 120.50 [id=")

    @pytest.mark.parametrize("word,stored", [("owe", "owe"), ("I owe", "owe"), ("borrowed", "owe"), ("DEBT", "owe"),
                                             ("owed", "owed"), ("they_owe", "owed"), ("lent", "owed"), ("Loan", "owed")])
    def test_direction_aliases(self, planner, word, stored):
        add(planner, direction=word)
        assert rows()[0]["direction"] == stored

    @pytest.mark.parametrize("args,msg", [
        ({"who": "", "amount": 5, "direction": "owe"}, "say who"), ({"who": 5, "amount": 5, "direction": "owe"}, "say who"),
        ({"who": "x" * 61, "amount": 5, "direction": "owe"}, "at most 60"),
        ({"who": "x", "amount": 0, "direction": "owe"}, "above zero"), ({"who": "x", "amount": -5, "direction": "owe"}, "above zero"),
        ({"who": "x", "amount": "lots", "direction": "owe"}, "above zero"), ({"who": "x", "amount": True, "direction": "owe"}, "above zero"),
        ({"who": "x", "amount": 1e13, "direction": "owe"}, "not a sensible"),
        ({"who": "x", "amount": 5, "direction": "maybe"}, "direction must be"), ({"who": "x", "amount": 5}, "direction must be"),
        ({"who": "x", "amount": 5, "direction": "owe", "due": "soon"}, "not a valid date")])
    def test_invalid(self, planner, args, msg):
        out = planner.dispatch_tool("add_debt", args)
        assert out.startswith("Debt not added: ") and msg in out and rows() == []

    def test_same_person_can_have_several_debts(self, planner):
        add(planner)
        add(planner, amount=20)
        assert len(rows()) == 2

    def test_limit(self, planner):
        import storage
        storage.save_debts([{"id": str(i), "who": "x", "direction": "owe", "amount": 1} for i in range(500)])
        assert "already have 500" in planner.dispatch_tool("add_debt", {"who": "x", "amount": 1, "direction": "owe"})


class TestPayments:
    def test_partial_payment(self, planner):
        add(planner)
        out = pay(planner, amount=200, note="cash")
        assert out.startswith("Recorded 200. you owe Ali 300 (of 500, 200 paid)")
        d = rows()[0]
        assert d["paid"] == 200 and d["settled"] is None
        assert d["payments"] == [{"date": "2026-10-13", "amount": 200.0, "note": "cash"}]

    def test_paying_it_off(self, planner):
        add(planner)
        pay(planner, amount=200)
        out = pay(planner, amount=300)
        assert out.endswith("Fully settled.") and "you paid Ali in full (500), settled 2026-10-13" in out
        assert rows()[0]["settled"] == "2026-10-13"

    def test_they_paid_wording(self, planner):
        add(planner, "Mehmet", 120, "owed")
        assert "they paid Mehmet in full (120)" in pay(planner, "mehmet", 120)

    def test_overpaying_is_refused(self, planner):
        add(planner)
        pay(planner, amount=450)
        out = pay(planner, amount=100)
        assert out == "Not recorded: only 50 is still open with Ali, so 100 is too much."
        assert rows()[0]["paid"] == 450

    def test_paying_a_settled_debt(self, planner):
        add(planner)
        pay(planner, amount=500)
        assert "already settled" in pay(planner, amount=1)

    def test_floating_point_sums(self, planner):
        add(planner, amount=1)
        for _ in range(10):
            pay(planner, amount=0.1)
        assert rows()[0]["settled"] == "2026-10-13" and rows()[0]["paid"] == 1.0

    def test_backdated_payments_stay_sorted(self, planner):
        add(planner)
        pay(planner, amount=10)
        pay(planner, amount=10, date="2026-10-01")
        assert [p["date"] for p in rows()[0]["payments"]] == ["2026-10-01", "2026-10-13"]

    @pytest.mark.parametrize("date,msg", [("2026-10-14", "in the future"), ("soon", "not a valid date")])
    def test_bad_dates(self, planner, date, msg):
        add(planner)
        assert msg in pay(planner, date=date) and rows()[0]["payments"] == []

    @pytest.mark.parametrize("amount", [0, -5, "x", None, True])
    def test_bad_amounts(self, planner, amount):
        add(planner)
        assert pay(planner, amount=amount).startswith("Not recorded: amount ")

    def test_payment_limit(self, planner):
        import storage
        add(planner, amount=10 ** 6)
        d = rows()
        d[0]["payments"] = [{"date": "2026-10-01", "amount": 1.0}] * 500
        storage.save_debts(d)
        assert "already has 500 payments" in pay(planner, amount=1)

    def test_a_reduced_amount_can_settle_it(self, planner):
        add(planner)
        pay(planner, amount=200)
        planner.dispatch_tool("update_debt", {"debt": "ali", "fields": {"amount": 200}})
        assert rows()[0]["settled"] == "2026-10-13"

    def test_raising_the_amount_reopens_it(self, planner):
        add(planner)
        pay(planner, amount=500)
        planner.dispatch_tool("update_debt", {"debt": rows()[0]["id"], "fields": {"amount": 800}})
        assert rows()[0]["settled"] is None


class TestResolve:
    def test_by_name_fragment_and_id(self, planner):
        did = add(planner, "Ali Can")
        for ref in (did, "ali", "CAN", "ali can"):
            assert pay(planner, ref, 1).startswith("Recorded 1.")

    def test_ambiguous_names_need_the_id(self, planner):
        add(planner, "Ali", 100)
        add(planner, "Ali", 200)
        out = pay(planner, "ali")
        assert out.startswith("Not recorded: 'ali' matches 2 debts (") and "Use the id" in out

    def test_a_settled_debt_does_not_make_the_name_ambiguous(self, planner):
        add(planner, "Ali", 100)
        pay(planner, "ali", 100)
        add(planner, "Ali", 200)
        assert pay(planner, "ali", 50).startswith("Recorded 50. you owe Ali 150")

    def test_unknown_and_blank(self, planner):
        add(planner)
        assert "no debt matches 'zed'" in pay(planner, "zed")
        assert "say which debt" in pay(planner, "")


class TestShow:
    def test_empty(self, planner):
        assert planner.dispatch_tool("get_debts", {}) == "No open debts. Add one with add_debt."
        assert planner.dispatch_tool("get_debts", {"include_settled": True}) == "No debts recorded."

    def test_totals_sides_and_order(self, planner):
        add(planner, "Later", 100, due="2026-12-01")
        add(planner, "Soon", 50, due="2026-10-20")
        add(planner, "NoDue", 10)
        add(planner, "Mehmet", 300, "owed")
        out = planner.dispatch_tool("get_debts", {}).split("\n")
        assert out[0] == "Open: you owe 160, you are owed 300 (net +140)."
        assert out[1] == "You owe:"
        assert [l.split(" ")[3] for l in out[2:5]] == ["Soon", "Later", "NoDue"]
        assert out[5] == "Owed to you:" and "Mehmet owes you 300" in out[6]

    def test_overdue_and_due_today_tags(self, planner):
        add(planner, "A", 5, due="2026-10-10")
        add(planner, "B", 5, due="2026-10-13")
        out = planner.dispatch_tool("get_debts", {})
        assert "due 2026-10-10 (OVERDUE by 3 day(s))" in out and "due 2026-10-13 (due today)" in out

    def test_settled_are_hidden_unless_asked(self, planner):
        add(planner, "A", 5)
        pay(planner, "a", 5)
        assert planner.dispatch_tool("get_debts", {}) == "No open debts. Add one with add_debt."
        assert "you paid A in full (5), settled 2026-10-13" in planner.dispatch_tool("get_debts", {"include_settled": True})

    def test_net_negative(self, planner):
        add(planner, "A", 100)
        assert "(net -100)" in planner.dispatch_tool("get_debts", {})


class TestUpdateDelete:
    def test_update(self, planner):
        add(planner)
        out = planner.dispatch_tool("update_debt", {"debt": "ali", "fields": {
            "who": "Ali K", "amount": 600, "due": "2026-11-01", "notes": "x"}})
        assert out.startswith("Debt updated: you owe Ali K 600, due 2026-11-01")
        d = rows()[0]
        assert (d["who"], d["amount"], d["due"], d["notes"]) == ("Ali K", 600, "2026-11-01", "x")

    def test_clear_due(self, planner):
        add(planner, due="2026-11-01")
        planner.dispatch_tool("update_debt", {"debt": "ali", "fields": {"due": ""}})
        assert rows()[0]["due"] is None

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"direction": "owed"}, "cannot change direction"),
                                            ({"who": ""}, "say who"), ({"amount": 0}, "above zero"),
                                            ({"due": "x"}, "not a valid date"), ({"notes": 5}, "notes must be text"),
                                            ({"amount": 50}, "already been paid"), ("x", "nothing to change")])
    def test_invalid_updates_change_nothing(self, planner, fields, msg):
        add(planner)
        pay(planner, amount=100)
        before = rows()
        out = planner.dispatch_tool("update_debt", {"debt": "ali", "fields": fields})
        assert out.startswith("Debt not changed: ") and msg in out and rows() == before

    def test_delete(self, planner):
        add(planner, "A")
        add(planner, "B")
        assert planner.dispatch_tool("delete_debt", {"debt": "a"}) == "Deleted debt with A. This can't be undone."
        assert [r["who"] for r in rows()] == ["B"]


class TestDueSoonAndNudges:
    def test_due_soon_window_and_order(self, planner):
        import debts
        add(planner, "Over", 5, due="2026-10-01")
        add(planner, "Today", 5, due="2026-10-13")
        add(planner, "Edge", 5, due="2026-10-16")
        add(planner, "Far", 5, due="2026-10-17")
        add(planner, "None", 5)
        assert [x["debt"]["who"] for x in debts.due_soon()] == ["Over", "Today", "Edge"]
        assert [x["in_days"] for x in debts.due_soon()] == [-12, 0, 3]

    def test_settled_debts_are_not_due(self, planner):
        import debts
        add(planner, "A", 5, due="2026-10-01")
        pay(planner, "a", 5)
        assert debts.due_soon() == []

    @pytest.mark.parametrize("due,direction,expected", [
        ("2026-10-10", "owe", "You owe Ali 500: 3 day(s) overdue."),
        ("2026-10-13", "owe", "You owe Ali 500: due today."),
        ("2026-10-14", "owe", "You owe Ali 500: due tomorrow."),
        ("2026-10-16", "owe", "You owe Ali 500: due in 3 days."),
        ("2026-10-14", "owed", "Ali owes you 500: due tomorrow.")])
    def test_nudge_wording(self, planner, due, direction, expected):
        import debts
        add(planner, direction=direction, due=due)
        assert debts.nudges() == [expected]

    def test_nudge_uses_the_remaining_amount(self, planner):
        import debts
        add(planner, due="2026-10-14")
        pay(planner, amount=200)
        assert debts.nudges() == ["You owe Ali 300: due tomorrow."]

    def test_max_items(self, planner):
        import debts
        add(planner, "A", 5, due="2026-10-14")
        add(planner, "B", 5, due="2026-10-15")
        assert len(debts.nudges(1)) == 1 and len(debts.nudges(5)) == 2

    def test_in_the_planner_nudges_and_the_agenda(self, planner):
        import nudges
        add(planner, due="2026-10-14")
        assert nudges._planner_nudges() == ["You owe Ali 500: due tomorrow."]
        out = planner.dispatch_tool("get_today_agenda", {})
        assert "Debts due:" in out and "you owe Ali 500 (due 2026-10-14)" in out

    def test_overdue_in_the_agenda(self, planner):
        add(planner, due="2026-10-01")
        assert "OVERDUE you owe Ali 500 (due 2026-10-01)" in planner.dispatch_tool("get_today_agenda", {})


class TestRobustness:
    def test_handwritten_rows(self, planner):
        import storage
        storage.save_debts([{"who": "legacy", "direction": "owe", "amount": 5}, "junk", None,
                            {"id": "k", "who": "k", "direction": "owed", "amount": "bad"},
                            {"id": "j", "who": "j", "direction": "owe", "amount": 7, "due": "garbage",
                             "payments": ["x", {"amount": "y"}, {"date": "2026-10-01", "amount": 2}]}])
        out = planner.dispatch_tool("get_debts", {})
        assert out.startswith("Open: you owe 10,") and "k" not in out.replace("Open", "").replace("legacy", "")
        assert all(r["id"] for r in storage.load_debts() if isinstance(r, dict))
        import debts
        assert debts.due_soon() == []

    def test_not_a_list_store(self, planner):
        import storage
        storage.save_debts({"x": 1})
        assert planner.dispatch_tool("get_debts", {}).startswith("No open debts")

    def test_does_not_touch_expenses_or_the_journal(self, planner):
        import storage
        add(planner)
        pay(planner)
        assert storage.load_spending() == [] and storage.get_all_memory() == []

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        add(planner)
        path = backup.run_backup()
        storage.save_debts([])
        restore.restore_backup(path, only="debts", safety_backup=False)
        assert rows()[0]["who"] == "Ali"

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        assert schemas["add_debt"]["parameters"]["required"] == ["who", "amount", "direction"]
        assert schemas["record_debt_payment"]["parameters"]["required"] == ["debt", "amount"]
