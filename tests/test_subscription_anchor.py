"""A renewal on the 29th to 31st keeps its day after a shorter month (issue #34)."""

from __future__ import annotations

from datetime import date, datetime

import pytest


def add(p, name="Gym", cycle="monthly", next_date="2027-01-31", **kw):
    out = p.dispatch_tool("add_subscription", {"name": name, "amount": 30, "cycle": cycle, "next_date": next_date, **kw})
    assert out.startswith("Subscription added: "), out


def pay(p, name="Gym"):
    out = p.dispatch_tool("pay_subscription", {"subscription": name, "log_expense": False})
    assert out.startswith("Recorded payment"), out
    return out


def rows():
    import storage
    return storage.load_subscriptions()


def nexts(p, count, name="Gym"):
    out = []
    for _ in range(count):
        pay(p, name)
        out.append(rows()[0]["next_date"])
    return out


class TestPayingKeepsTheAnchor:
    def test_monthly_31st_comes_back(self, planner):
        planner.set_now(datetime(2027, 1, 25, 9))
        add(planner)
        assert nexts(planner, 5) == ["2027-02-28", "2027-03-31", "2027-04-30", "2027-05-31", "2027-06-30"]

    def test_the_report_from_the_issue(self, planner):
        planner.set_now(datetime(2027, 1, 25, 9))
        add(planner)
        assert "Next renewal: 2027-02-28." in pay(planner)
        planner.set_now(datetime(2027, 3, 1, 9))
        assert "(renewal of 2027-02-28). Next renewal: 2027-03-31." in pay(planner)

    def test_quarterly_from_nov_30(self, planner):
        planner.set_now(datetime(2026, 11, 20, 9))
        add(planner, cycle="quarterly", next_date="2026-11-30")
        assert nexts(planner, 4) == ["2027-02-28", "2027-05-30", "2027-08-30", "2027-11-30"]

    def test_yearly_from_feb_29(self, planner):
        planner.set_now(datetime(2028, 2, 20, 9))
        add(planner, cycle="yearly", next_date="2028-02-29")
        assert nexts(planner, 4) == ["2029-02-28", "2030-02-28", "2031-02-28", "2032-02-29"]

    def test_weekly_and_ordinary_dates_are_unchanged(self, planner):
        planner.set_now(datetime(2027, 1, 1, 9))
        add(planner, "Week", "weekly", "2027-01-06")
        add(planner, "Mid", "monthly", "2027-01-15")
        assert nexts(planner, 2, "Week") == ["2027-01-13", "2027-01-20"]
        pay(planner, "Mid")
        assert [r for r in rows() if r["name"] == "Mid"][0]["next_date"] == "2027-02-15"

    def test_catching_up_after_missed_payments_keeps_the_day(self, planner):
        planner.set_now(datetime(2027, 1, 25, 9))
        add(planner)
        planner.set_now(datetime(2027, 4, 2, 9))
        out = pay(planner)
        assert "(renewal of 2027-01-31). Next renewal: 2027-04-30." in out
        planner.set_now(datetime(2027, 5, 1, 9))
        assert "Next renewal: 2027-05-31." in pay(planner)

    def test_paying_late_on_the_clamped_day(self, planner):
        planner.set_now(datetime(2027, 1, 25, 9))
        add(planner)
        pay(planner)
        planner.set_now(datetime(2027, 2, 28, 9))
        assert "(renewal of 2027-02-28). Next renewal: 2027-03-31." in pay(planner)

    def test_anchor_is_stored_and_not_editable(self, planner):
        add(planner)
        assert rows()[0]["anchor"] == "2027-01-31"
        assert "cannot change anchor" in planner.dispatch_tool("update_subscription", {"subscription": "gym", "fields": {"anchor": "2027-01-01"}})


class TestOldAndEditedRows:
    def test_a_row_without_an_anchor_gets_one_when_paid(self, planner):
        import storage
        planner.set_now(datetime(2027, 1, 25, 9))
        storage.save_subscriptions([{"id": "a", "name": "Gym", "amount": 30, "cycle": "monthly", "next_date": "2027-01-31", "active": True}])
        pay(planner)
        assert rows()[0]["next_date"] == "2027-02-28" and rows()[0]["anchor"] == "2027-01-31"
        planner.set_now(datetime(2027, 3, 1, 9))
        pay(planner)
        assert rows()[0]["next_date"] == "2027-03-31"

    def test_editing_the_date_starts_a_new_schedule(self, planner):
        planner.set_now(datetime(2027, 1, 25, 9))
        add(planner)
        pay(planner)                                              # now Feb 28, anchor Jan 31
        planner.dispatch_tool("update_subscription", {"subscription": "gym", "fields": {"next_date": "2027-03-15"}})
        assert rows()[0]["anchor"] == "2027-03-15"
        planner.set_now(datetime(2027, 3, 14, 9))
        pay(planner)
        assert rows()[0]["next_date"] == "2027-04-15"

    def test_the_drifted_date_of_an_old_row_can_be_corrected(self, planner):
        import storage
        planner.set_now(datetime(2027, 3, 1, 9))
        storage.save_subscriptions([{"id": "a", "name": "Gym", "amount": 30, "cycle": "monthly", "next_date": "2027-03-28", "active": True}])
        planner.dispatch_tool("update_subscription", {"subscription": "gym", "fields": {"next_date": "2027-03-31"}})
        assert nexts(planner, 2) == ["2027-04-30", "2027-05-31"]

    def test_changing_the_cycle_resets_the_anchor(self, planner):
        add(planner)
        planner.dispatch_tool("update_subscription", {"subscription": "gym", "fields": {"cycle": "quarterly"}})
        assert rows()[0]["anchor"] == "2027-01-31"
        planner.dispatch_tool("update_subscription", {"subscription": "gym", "fields": {"name": "Gym 2"}})
        assert rows()[0]["anchor"] == "2027-01-31"

    def test_an_anchor_that_does_not_lead_to_the_stored_date_is_ignored(self, planner):
        import subscriptions
        sub = {"next_date": "2027-02-10", "anchor": "2027-01-31", "cycle": "monthly"}
        assert subscriptions.schedule_base(sub, date(2027, 2, 10), "monthly") == date(2027, 2, 10)
        assert subscriptions.effective_next(sub, date(2027, 3, 1)) == date(2027, 3, 10)

    @pytest.mark.parametrize("anchor", [None, "", "garbage", 5, "2030-01-31", "2027-02-28"])
    def test_a_bad_or_later_anchor_falls_back_to_the_stored_date(self, planner, anchor):
        import subscriptions
        sub = {"next_date": "2027-02-28", "anchor": anchor, "cycle": "monthly"}
        assert subscriptions.schedule_base(sub, date(2027, 2, 28), "monthly") == date(2027, 2, 28)


class TestUnpaidRollForward:
    def test_unpaid_monthly_keeps_the_day(self, planner):
        import subscriptions
        sub = {"next_date": "2027-02-28", "anchor": "2027-01-31", "cycle": "monthly"}
        assert subscriptions.effective_next(sub, date(2027, 3, 1)) == date(2027, 3, 31)
        assert subscriptions.effective_next(sub, date(2027, 4, 1)) == date(2027, 4, 30)
        assert subscriptions.effective_next(sub, date(2027, 4, 30)) == date(2027, 4, 30)
        assert subscriptions.effective_next(sub, date(2027, 5, 1)) == date(2027, 5, 31)

    def test_the_stored_date_is_used_while_it_lies_ahead(self, planner):
        import subscriptions
        sub = {"next_date": "2027-02-28", "anchor": "2027-01-31", "cycle": "monthly"}
        assert subscriptions.effective_next(sub, date(2027, 2, 20)) == date(2027, 2, 28)

    def test_upcoming_and_the_nudge_follow_the_anchor(self, planner):
        import subscriptions
        planner.set_now(datetime(2027, 1, 25, 9))
        add(planner)
        pay(planner)
        planner.set_now(datetime(2027, 3, 1, 9))
        assert subscriptions.upcoming(40)[0]["date"] == "2027-03-31"
        planner.set_now(datetime(2027, 3, 28, 9))
        assert subscriptions.renewal_nudge(3) == "Gym renews in 3 days (30)."

    def test_resume_keeps_the_anchor(self, planner):
        planner.set_now(datetime(2027, 1, 25, 9))
        add(planner)
        pay(planner)
        planner.dispatch_tool("cancel_subscription", {"subscription": "gym"})
        planner.set_now(datetime(2027, 3, 2, 9))
        planner.dispatch_tool("resume_subscription", {"subscription": "gym"})
        assert rows()[0]["next_date"] == "2027-03-31" and rows()[0]["anchor"] == "2027-01-31"
        pay(planner)
        assert rows()[0]["next_date"] == "2027-04-30"

    def test_resume_with_a_date_starts_a_new_schedule(self, planner):
        add(planner)
        planner.dispatch_tool("cancel_subscription", {"subscription": "gym"})
        planner.dispatch_tool("resume_subscription", {"subscription": "gym", "next_date": "2027-06-15"})
        assert rows()[0]["anchor"] == "2027-06-15"
