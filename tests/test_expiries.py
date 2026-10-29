"""Expiry dates: passports, insurance and other things that run out on a date."""

from __future__ import annotations

import pytest


def exp(p, name="Passport", date="2026-11-10", **kw):
    out = p.dispatch_tool("add_expiry", {"name": name, "date": date, **kw})
    assert out.startswith("Expiry date added: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_expiries()


class TestAdd:
    def test_shape_and_output(self, planner):
        out = planner.dispatch_tool("add_expiry", {"name": " Passport ", "date": "2026-11-10", "category": "Passport", "notes": " n "})
        assert out.startswith("Expiry date added: Passport [document]: expires in 28 days (2026-11-10) - renew soon [id=")
        e = rows()[0]
        assert set(e) == {"id", "name", "date", "remind_days", "category", "notes", "created", "history"}
        assert (e["remind_days"], e["category"], e["notes"], e["created"], e["history"]) == (30, "document", "n", "2026-10-13", [])

    def test_far_item_has_no_flag_and_other_category_is_not_shown(self, planner):
        out = planner.dispatch_tool("add_expiry", {"name": "Gym", "date": "2027-05-01", "remind_days": 14})
        assert out.startswith("Expiry date added: Gym: expires in 200 days (2027-05-01) [id=")
        assert rows()[0]["remind_days"] == 14

    def test_expired_today_and_past(self, planner):
        a = planner.dispatch_tool("add_expiry", {"name": "A", "date": "2026-10-13"})
        b = planner.dispatch_tool("add_expiry", {"name": "B", "date": "2026-10-12"})
        assert "A: expires today (2026-10-13) - renew soon" in a
        assert "B: expired yesterday (2026-10-12) - renew now" in b

    def test_category_aliases(self, planner):
        exp(planner, "A", category="licence")
        exp(planner, "B", category="ID")
        assert [e["category"] for e in rows()] == ["license", "document"]

    @pytest.mark.parametrize("kw,msg", [
        ({"name": ""}, "cannot be empty"), ({"name": "n" * 61}, "at most 60"), ({"date": "soon"}, "not a valid date"),
        ({"date": None}, "must be written as YYYY-MM-DD"), ({"date": "2000-01-01"}, "within 10 years"),
        ({"date": "2050-01-01"}, "within 10 years"), ({"remind_days": 0}, "from 1 to 365"), ({"remind_days": 400}, "from 1 to 365"),
        ({"remind_days": True}, "from 1 to 365"), ({"remind_days": 2.5}, "from 1 to 365"), ({"remind_days": "x"}, "from 1 to 365"),
        ({"category": "toys"}, "category must be one of"), ({"notes": "n" * 161}, "at most 160")])
    def test_rejected(self, planner, kw, msg):
        out = planner.dispatch_tool("add_expiry", {"name": "X", "date": "2027-01-01", **kw})
        assert out.startswith("Expiry date not added: ") and msg in out
        assert rows() == []

    def test_duplicate_and_limit(self, planner):
        exp(planner)
        assert "already an expiry date called 'passport'" in planner.dispatch_tool("add_expiry", {"name": "passport", "date": "2027-01-01"})
        import storage
        storage.save_expiries([{"id": f"i{n}", "name": f"e{n}", "date": "2027-01-01"} for n in range(200)])
        assert "already have 200" in planner.dispatch_tool("add_expiry", {"name": "More", "date": "2027-01-01"})


class TestRenew:
    def test_extend_counts_from_the_current_date_when_not_expired(self, planner):
        exp(planner)
        out = planner.dispatch_tool("renew_expiry", {"item": "passport", "extend_months": 12})
        assert out.startswith("Renewed: Passport: expires in 393 days (2027-11-10)")
        h = rows()[0]["history"]
        assert h == [{"renewed_on": "2026-10-13", "from": "2026-11-10", "to": "2027-11-10"}]

    def test_extend_counts_from_today_when_expired(self, planner):
        exp(planner, "Ins", "2026-10-05")
        planner.dispatch_tool("renew_expiry", {"item": "ins", "extend_months": 12})
        assert rows()[0]["date"] == "2027-10-13"

    def test_new_date(self, planner):
        exp(planner)
        assert planner.dispatch_tool("renew_expiry", {"item": "passport", "new_date": "2031-11-10"}).startswith("Renewed: Passport")
        assert rows()[0]["date"] == "2031-11-10"

    @pytest.mark.parametrize("kw,msg", [
        ({}, "either new_date"), ({"new_date": "2030-01-01", "extend_months": 3}, "either new_date"),
        ({"new_date": "2026-11-10"}, "later than the current expiry"), ({"new_date": "2026-01-01"}, "later than"),
        ({"new_date": "x"}, "not a valid date"), ({"extend_months": 0}, "from 1 to 120"), ({"extend_months": 121}, "from 1 to 120"),
        ({"extend_months": 2.5}, "from 1 to 120"), ({"extend_months": True}, "from 1 to 120"), ({"extend_months": "x"}, "from 1 to 120")])
    def test_errors_change_nothing(self, planner, kw, msg):
        exp(planner)
        out = planner.dispatch_tool("renew_expiry", {"item": "passport", **kw})
        assert out.startswith("Not renewed: ") and msg in out
        assert rows()[0]["date"] == "2026-11-10" and rows()[0]["history"] == []

    def test_history_is_capped(self, planner):
        import expiries
        exp(planner, date="2026-11-10")
        for _ in range(25):
            expiries.renew_expiry("passport", extend_months=1)
        assert len(rows()[0]["history"]) == 20


class TestListAndNudges:
    def test_listing_order_and_filter(self, planner):
        exp(planner, "Far", "2028-01-01")
        exp(planner, "Soon", "2026-10-30")
        exp(planner, "Gone", "2026-10-01")
        out = planner.dispatch_tool("get_expiries", {})
        assert [l.split(":")[0].lstrip("- ").split(" [")[0] for l in out.splitlines()[1:]] == ["Gone", "Soon", "Far"]
        soon = planner.dispatch_tool("get_expiries", {"filter": "soon"})
        assert soon.startswith("2 expiry dates expired or expiring soon:") and "Far" not in soon
        assert planner.dispatch_tool("get_expiries", {"filter": "x"}) == "Cannot show expiry dates: filter must be all or soon."

    def test_empty(self, planner):
        assert planner.dispatch_tool("get_expiries", {}).startswith("No expiry dates yet.")
        assert planner.dispatch_tool("get_expiries", {"filter": "soon"}) == "Nothing is expiring soon."

    def test_nudge_and_agenda(self, planner):
        import expiries
        exp(planner, "Far", "2028-01-01")
        assert expiries.nudges() == []
        exp(planner, "Passport", "2026-11-10")
        exp(planner, "Ins", "2026-10-20")
        assert expiries.nudges() == ["Ins expires in 7 days (2026-10-20)."]
        assert expiries.agenda_lines() == ["Ins expires in 7 days (2026-10-20)"]   # the passport is 28 days away

    def test_long_expired_items_are_not_nudged(self, planner):
        import expiries
        exp(planner, "Old", "2026-08-01")
        exp(planner, "Recent", "2026-10-01")
        assert expiries.nudges(5) == ["Recent expired 12 days ago (2026-10-01)."]
        assert "Old" in planner.dispatch_tool("get_expiries", {})   # still listed

    def test_unreadable_rows_are_skipped(self, planner):
        import expiries, storage
        storage.save_expiries([{"id": "a", "name": "bad", "date": "x"}, "junk", {"id": "b", "name": "ok", "date": "2026-10-20"}])
        assert [x["item"]["name"] for x in expiries.listing()] == ["ok"]

    def test_custom_window(self, planner):
        import expiries
        exp(planner, "Gym", "2026-10-25", remind_days=5)
        assert expiries.nudges() == []
        exp(planner, "Pass", "2026-10-25", remind_days=20)
        assert expiries.nudges() == ["Pass expires in 12 days (2026-10-25)."]


class TestUpdateDelete:
    def test_update(self, planner):
        exp(planner)
        out = planner.dispatch_tool("update_expiry", {"item": "pass", "fields": {"name": "Passport 2", "date": "2027-01-01",
                                                                                 "remind_days": 60, "category": "license", "notes": "x"}})
        assert out.startswith("Expiry date updated: Passport 2 [license]: expires in 80 days (2027-01-01)")
        assert rows()[0]["remind_days"] == 60

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"id": "x"}, "cannot change id"),
                                            ({"date": "bad"}, "not a valid date"), ({"category": "x"}, "category must be")])
    def test_bad_updates(self, planner, fields, msg):
        exp(planner)
        before = rows()
        assert msg in planner.dispatch_tool("update_expiry", {"item": "pass", "fields": fields})
        assert rows() == before

    def test_delete(self, planner):
        exp(planner)
        assert planner.dispatch_tool("delete_expiry", {"item": "passport"}) == "Deleted expiry date Passport. This can't be undone."
        assert rows() == []
        assert "no expiry date matches" in planner.dispatch_tool("delete_expiry", {"item": "passport"})

    def test_update_of_an_unreadable_date_shows_the_name(self, planner):
        import storage
        storage.save_expiries([{"id": "a", "name": "bad", "date": "x"}])
        assert planner.dispatch_tool("update_expiry", {"item": "bad", "fields": {"notes": "n"}}) == "Expiry date updated: bad"
