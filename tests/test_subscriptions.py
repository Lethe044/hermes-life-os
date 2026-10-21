"""Subscriptions: add / update / cancel / resume / delete, monthly equivalents, renewals, paying."""

from __future__ import annotations

from datetime import date, datetime

import pytest


def add(p, name="Netflix", amount=15, **kw):
    out = p.dispatch_tool("add_subscription", {"name": name, "amount": amount, **kw})
    assert out.startswith("Subscription added: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_subscriptions()


class TestAdd:
    def test_defaults(self, planner):
        sid = add(planner)
        r = rows()[0]
        assert r["id"] == sid and r["cycle"] == "monthly" and r["amount"] == 15 and r["category"] == "subscriptions"
        assert r["next_date"] == "2026-11-13" and r["active"] is True and r["created"] == "2026-10-13"

    @pytest.mark.parametrize("cycle,expected", [("weekly", "2026-10-20"), ("quarterly", "2027-01-13"),
                                                ("yearly", "2027-10-13"), ("annual", "2027-10-13"),
                                                ("per month", "2026-11-13")])
    def test_default_next_date_is_one_cycle_away(self, planner, cycle, expected):
        add(planner, cycle=cycle)
        assert rows()[0]["next_date"] == expected

    def test_explicit_date_category_notes(self, planner):
        out = planner.dispatch_tool("add_subscription", {"name": "  Gym  ", "amount": 30.456, "cycle": "monthly",
                                                         "next_date": "2026-10-20", "category": " Health ", "notes": "n"})
        assert "Gym: 30.46 monthly (30.46/month, health), renews 2026-10-20" in out
        assert rows()[0]["category"] == "health" and rows()[0]["notes"] == "n"

    @pytest.mark.parametrize("kw,msg", [
        ({"name": ""}, "needs a name"), ({"name": "  "}, "needs a name"), ({"name": 5}, "needs a name"),
        ({"amount": 0}, "above 0"), ({"amount": -5}, "above 0"), ({"amount": "lots"}, "must be a number"),
        ({"amount": float("nan")}, "above 0"), ({"amount": float("inf")}, "above 0"), ({"amount": True}, "above 0"),
        ({"amount": 10 ** 9}, "above 0"), ({"cycle": "daily"}, "cycle must be one of"),
        ({"next_date": "soon"}, "not a valid date"), ({"next_date": "2026-13-01"}, "not a valid date"),
        ({"name": "x" * 81}, "at most 80"),
    ])
    def test_invalid_adds_write_nothing(self, planner, kw, msg):
        args = {"name": "Netflix", "amount": 15, **kw}
        out = planner.dispatch_tool("add_subscription", args)
        assert out.startswith("Subscription not added: ") and msg in out and rows() == []

    def test_duplicate_active_name_is_refused_case_insensitively(self, planner):
        add(planner)
        assert "already exists" in planner.dispatch_tool("add_subscription", {"name": "NETFLIX", "amount": 1})
        assert len(rows()) == 1

    def test_a_cancelled_name_can_be_added_again(self, planner):
        add(planner)
        planner.dispatch_tool("cancel_subscription", {"subscription": "netflix"})
        add(planner)
        assert len(rows()) == 2

    def test_limit(self, planner):
        import storage
        storage.save_subscriptions([{"id": str(i), "name": f"s{i}", "amount": 1, "cycle": "monthly",
                                     "next_date": "2026-11-01", "active": True} for i in range(500)])
        out = planner.dispatch_tool("add_subscription", {"name": "one more", "amount": 1})
        assert "already track 500" in out


class TestMonthlyEquivalent:
    @pytest.mark.parametrize("amount,cycle,monthly", [(12, "monthly", 12), (36, "quarterly", 12),
                                                      (120, "yearly", 10), (10, "weekly", 10 * 52 / 12)])
    def test_values(self, planner, amount, cycle, monthly):
        import subscriptions
        assert subscriptions.monthly_equivalent(amount, cycle) == pytest.approx(monthly)

    def test_listed(self, planner):
        add(planner, "Insurance", 240, cycle="yearly")
        assert "(20.00/month" in planner.dispatch_tool("list_subscriptions", {})


class TestRenewalDates:
    def test_future_date_is_kept(self, planner):
        import subscriptions
        sub = {"next_date": "2026-12-01", "cycle": "monthly"}
        assert subscriptions.effective_next(sub, date(2026, 10, 13)) == date(2026, 12, 1)

    def test_today_counts(self, planner):
        import subscriptions
        assert subscriptions.effective_next({"next_date": "2026-10-13", "cycle": "monthly"}, date(2026, 10, 13)) \
            == date(2026, 10, 13)

    def test_past_date_rolls_forward_by_whole_cycles(self, planner):
        import subscriptions
        assert subscriptions.effective_next({"next_date": "2026-07-20", "cycle": "monthly"}, date(2026, 10, 13)) \
            == date(2026, 10, 20)
        assert subscriptions.effective_next({"next_date": "2026-09-01", "cycle": "weekly"}, date(2026, 10, 13)) \
            == date(2026, 10, 13)

    def test_month_end_anchor_sticks(self, planner):
        import subscriptions
        sub = {"next_date": "2026-01-31", "cycle": "monthly"}
        assert subscriptions.effective_next(sub, date(2026, 2, 15)) == date(2026, 2, 28)
        assert subscriptions.effective_next(sub, date(2026, 3, 1)) == date(2026, 3, 31)

    def test_leap_day_yearly(self, planner):
        import subscriptions
        sub = {"next_date": "2024-02-29", "cycle": "yearly"}
        assert subscriptions.effective_next(sub, date(2025, 3, 1)) == date(2026, 2, 28)
        assert subscriptions.effective_next(sub, date(2027, 3, 1)) == date(2028, 2, 29)

    @pytest.mark.parametrize("sub", [{"next_date": "garbage", "cycle": "monthly"}, {"cycle": "monthly"},
                                     {"next_date": "2020-01-01", "cycle": "daily"}])
    def test_unreadable_gives_none(self, planner, sub):
        import subscriptions
        assert subscriptions.effective_next(sub) is None

    def test_listing_shows_the_rolled_forward_date(self, planner):
        add(planner, next_date="2026-07-20")
        assert "renews 2026-10-20" in planner.dispatch_tool("list_subscriptions", {})


class TestUpdate:
    def test_changes(self, planner):
        add(planner)
        out = planner.dispatch_tool("update_subscription", {"subscription": "net", "fields": {
            "amount": 20, "cycle": "yearly", "next_date": "2027-01-01", "category": "Fun", "notes": "x", "name": "Netflix HD"}})
        assert "Netflix HD: 20 yearly" in out
        r = rows()[0]
        assert (r["amount"], r["cycle"], r["next_date"], r["category"], r["notes"]) == (20, "yearly", "2027-01-01", "fun", "x")

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"bogus": 1}, "cannot change bogus"),
                                            ({"amount": 0}, "above 0"), ({"cycle": "daily"}, "cycle must"),
                                            ({"next_date": "x"}, "not a valid date"), ({"category": " "}, "category cannot"),
                                            ({"name": ""}, "needs a name"), ({"notes": 5}, "notes must be text")])
    def test_invalid_changes_leave_everything(self, planner, fields, msg):
        add(planner)
        before = rows()
        out = planner.dispatch_tool("update_subscription", {"subscription": "netflix", "fields": fields})
        assert out.startswith("Subscription not changed: ") and msg in out and rows() == before

    def test_rename_onto_an_existing_name_is_refused(self, planner):
        add(planner, "A")
        add(planner, "B")
        out = planner.dispatch_tool("update_subscription", {"subscription": "B", "fields": {"name": "a"}})
        assert "already exists" in out and [r["name"] for r in rows()] == ["A", "B"]

    def test_rename_to_itself_is_fine(self, planner):
        add(planner, "A")
        assert planner.dispatch_tool("update_subscription", {"subscription": "A", "fields": {"name": "A"}}).startswith("Subscription updated")

    def test_partial_invalid_applies_nothing(self, planner):
        add(planner)
        planner.dispatch_tool("update_subscription", {"subscription": "netflix", "fields": {"amount": 99, "cycle": "daily"}})
        assert rows()[0]["amount"] == 15


class TestResolve:
    def test_by_id_name_and_fragment(self, planner):
        sid = add(planner, "Spotify Family")
        for ref in (sid, "spotify family", "SPOT", sid.upper()):
            assert "Spotify Family" in planner.dispatch_tool("update_subscription", {"subscription": ref, "fields": {"notes": "x"}})

    def test_ambiguous_and_unknown_and_blank(self, planner):
        add(planner, "Spotify")
        add(planner, "Spotify Kids")
        assert "matches 2 subscriptions" in planner.dispatch_tool("cancel_subscription", {"subscription": "spot"})
        assert "no subscription matches 'zzz'" in planner.dispatch_tool("cancel_subscription", {"subscription": "zzz"})
        assert "say which subscription" in planner.dispatch_tool("cancel_subscription", {"subscription": " "})
        assert "say which subscription" in planner.dispatch_tool("cancel_subscription", {})

    def test_exact_name_beats_a_longer_match(self, planner):
        add(planner, "Spotify")
        add(planner, "Spotify Kids")
        assert "Cancelled Spotify:" in planner.dispatch_tool("cancel_subscription", {"subscription": "spotify"})


class TestCancelResumeDelete:
    def test_cancel_drops_from_totals_and_list(self, planner):
        add(planner, "A", 10)
        add(planner, "B", 20)
        out = planner.dispatch_tool("cancel_subscription", {"subscription": "A"})
        assert out == "Cancelled A: it no longer counts in your totals (10.00 per month saved)."
        assert "1 active subscription(s): 20.00 per month" in planner.dispatch_tool("get_subscription_summary", {})
        assert "A:" not in planner.dispatch_tool("list_subscriptions", {})
        assert "cancelled 2026-10-13" in planner.dispatch_tool("list_subscriptions", {"include_cancelled": True})

    def test_cancel_twice(self, planner):
        add(planner)
        planner.dispatch_tool("cancel_subscription", {"subscription": "netflix"})
        assert "already cancelled" in planner.dispatch_tool("cancel_subscription", {"subscription": "netflix"})

    def test_resume_with_and_without_a_date(self, planner):
        add(planner, next_date="2026-07-20")
        planner.dispatch_tool("cancel_subscription", {"subscription": "netflix"})
        out = planner.dispatch_tool("resume_subscription", {"subscription": "netflix"})
        assert "renews 2026-10-20" in out and rows()[0]["active"] is True and rows()[0]["cancelled"] is None
        planner.dispatch_tool("cancel_subscription", {"subscription": "netflix"})
        assert "renews 2026-12-01" in planner.dispatch_tool("resume_subscription", {"subscription": "netflix", "next_date": "2026-12-01"})

    def test_resume_of_an_active_one_and_a_bad_date(self, planner):
        add(planner)
        assert "is not cancelled" in planner.dispatch_tool("resume_subscription", {"subscription": "netflix"})
        planner.dispatch_tool("cancel_subscription", {"subscription": "netflix"})
        assert "not a valid date" in planner.dispatch_tool("resume_subscription", {"subscription": "netflix", "next_date": "x"})
        assert rows()[0]["active"] is False

    def test_delete(self, planner):
        add(planner, "A")
        add(planner, "B")
        assert planner.dispatch_tool("delete_subscription", {"subscription": "A"}) == "Deleted subscription: A. This can't be undone."
        assert [r["name"] for r in rows()] == ["B"]


class TestSummary:
    def test_empty(self, planner):
        assert planner.dispatch_tool("get_subscription_summary", {}) == "No active subscriptions. Add one with add_subscription."
        assert planner.dispatch_tool("list_subscriptions", {}) == "No subscriptions tracked yet. Add one with add_subscription."

    def test_totals_categories_and_biggest(self, planner):
        add(planner, "Netflix", 15, category="fun", next_date="2026-10-14")
        add(planner, "Gym", 30, category="health", next_date="2026-12-01")
        add(planner, "Insurance", 600, cycle="yearly", category="health", next_date="2027-03-01")
        out = planner.dispatch_tool("get_subscription_summary", {})
        assert "3 active subscription(s): 95.00 per month, 1140.00 per year." in out
        assert "By category (per month): health 80.00, fun 15.00" in out
        assert "Biggest: Insurance (50.00/month), Gym (30.00/month), Netflix (15.00/month)" in out
        assert "2026-10-14 (in 1 day(s)): Netflix 15" in out

    def test_nothing_renewing(self, planner):
        add(planner, next_date="2026-12-01")
        assert "Nothing renews in the next 14 days." in planner.dispatch_tool("get_subscription_summary", {})

    def test_window_argument(self, planner):
        add(planner, next_date="2026-10-30")
        assert "Nothing renews" in planner.dispatch_tool("get_subscription_summary", {"days": 3})
        assert "2026-10-30" in planner.dispatch_tool("get_subscription_summary", {"days": 30})
        assert "Cannot summarize" in planner.dispatch_tool("get_subscription_summary", {"days": "soon"})

    def test_incomplete_entries_are_left_out(self, planner):
        import storage
        storage.save_subscriptions([{"id": "a", "name": "odd", "amount": "x", "cycle": "monthly", "active": True},
                                    {"id": "b", "name": "ok", "amount": 5, "cycle": "monthly", "next_date": "2026-11-01", "active": True}])
        assert "1 active subscription(s): 5.00 per month" in planner.dispatch_tool("get_subscription_summary", {})
        assert "(incomplete entry)" in planner.dispatch_tool("list_subscriptions", {})


class TestPay:
    def test_logs_an_expense_and_moves_the_date(self, planner):
        import storage
        add(planner, "Gym", 30, category="health", next_date="2026-10-15")
        out = planner.dispatch_tool("pay_subscription", {"subscription": "gym"})
        assert out.startswith("Recorded payment for Gym (renewal of 2026-10-15). Next renewal: 2026-11-15.")
        assert "Expense logged: 30.0 (health)" in out
        e = storage.load_spending()[0]
        assert (e["amount"], e["category"], e["notes"], e["date"]) == (30.0, "health", "Gym subscription", "2026-10-13")
        assert rows()[0]["next_date"] == "2026-11-15"

    def test_without_logging_the_expense(self, planner):
        import storage
        add(planner, next_date="2026-10-15")
        out = planner.dispatch_tool("pay_subscription", {"subscription": "netflix", "log_expense": False})
        assert "Expense logged" not in out and storage.load_spending() == [] and rows()[0]["next_date"] == "2026-11-15"

    def test_catching_up_after_missed_payments(self, planner):
        add(planner, next_date="2026-07-20")
        out = planner.dispatch_tool("pay_subscription", {"subscription": "netflix"})
        assert "(renewal of 2026-07-20)" in out and "Next renewal: 2026-10-20." in out

    def test_month_end_anchor(self, planner):
        add(planner, next_date="2026-10-31")
        planner.dispatch_tool("pay_subscription", {"subscription": "netflix"})
        assert rows()[0]["next_date"] == "2026-11-30"

    def test_cancelled_and_unreadable(self, planner):
        import storage
        add(planner)
        planner.dispatch_tool("cancel_subscription", {"subscription": "netflix"})
        assert "is cancelled - resume it first" in planner.dispatch_tool("pay_subscription", {"subscription": "netflix"})
        storage.save_subscriptions([{"id": "a", "name": "odd", "amount": 5, "cycle": "monthly", "next_date": "x", "active": True}])
        assert "no readable renewal date" in planner.dispatch_tool("pay_subscription", {"subscription": "odd"})

    def test_paid_expense_counts_in_the_budget(self, planner):
        planner.dispatch_tool("set_budget", {"category": "health", "limit": 100})
        add(planner, "Gym", 30, category="health", next_date="2026-10-15")
        planner.dispatch_tool("pay_subscription", {"subscription": "gym"})
        assert "30" in planner.dispatch_tool("get_budget_status", {"category": "health"})


class TestNudge:
    def test_renewal_nudge_wording(self, planner):
        import subscriptions
        add(planner, "Netflix", 15, next_date="2026-10-13")
        assert subscriptions.renewal_nudge(3) == "Netflix renews today (15)."
        add(planner, "Gym", 30, next_date="2026-10-14")
        assert subscriptions.renewal_nudge(3) == "Netflix renews today (15), plus 1 more renewal within 3 days."
        add(planner, "Cloud", 3, next_date="2026-10-15")
        assert "plus 2 more renewals within 3 days" in subscriptions.renewal_nudge(3)

    def test_none_when_nothing_is_near(self, planner):
        import subscriptions
        add(planner, next_date="2026-12-01")
        assert subscriptions.renewal_nudge(3) is None

    def test_cancelled_ones_do_not_nudge(self, planner):
        import subscriptions
        add(planner, next_date="2026-10-14")
        planner.dispatch_tool("cancel_subscription", {"subscription": "netflix"})
        assert subscriptions.renewal_nudge(3) is None

    def test_in_the_proactive_nudges(self, planner):
        from nudges import generate_nudges
        add(planner, "Netflix", 15, next_date="2026-10-14")
        assert any("Netflix renews tomorrow" in n for n in generate_nudges())


class TestRobustness:
    def test_handwritten_rows(self, planner):
        import storage
        storage.save_subscriptions([{"name": "legacy", "amount": 5, "cycle": "monthly", "next_date": "2026-11-01"}, "junk", None])
        assert "legacy" in planner.dispatch_tool("list_subscriptions", {})
        assert storage.load_subscriptions()[0]["id"]

    def test_not_a_list_store(self, planner):
        import storage
        storage.save_subscriptions({"x": 1})
        assert planner.dispatch_tool("list_subscriptions", {}).startswith("No subscriptions tracked yet")

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        add(planner, "Keep", 5)
        path = backup.run_backup()
        storage.save_subscriptions([])
        restore.restore_backup(path, only="subscriptions", safety_backup=False)
        assert storage.load_subscriptions()[0]["name"] == "Keep"

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        for n in ("add_subscription", "list_subscriptions", "update_subscription", "cancel_subscription",
                  "resume_subscription", "delete_subscription", "get_subscription_summary", "pay_subscription"):
            assert n in schemas
        assert schemas["add_subscription"]["parameters"]["required"] == ["name", "amount"]
