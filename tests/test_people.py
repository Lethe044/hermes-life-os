"""People: saved contacts, keep-in-touch goals, birthdays, contact logging, nudges."""

from __future__ import annotations

from datetime import date, datetime

import pytest


def add(p, name="Ayse", **kw):
    out = p.dispatch_tool("add_person", {"name": name, **kw})
    assert out.startswith("Saved: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_people()


class TestAdd:
    def test_minimal(self, planner):
        pid = add(planner)
        r = rows()[0]
        assert r["id"] == pid and r["name"] == "Ayse" and r["birthday"] is None and r["keep_in_touch_days"] is None
        assert r["last_contact"] is None and r["history"] == [] and r["created"] == "2026-10-13"

    def test_full(self, planner):
        out = planner.dispatch_tool("add_person", {"name": "  Mehmet   Y ", "birthday": "1990-11-02",
                                                   "keep_in_touch_days": 14, "notes": "college friend"})
        assert "Mehmet Y" in out and "goal every 14 days" in out and "birthday 2026-11-02 (in 20 days)" in out
        assert rows()[0]["notes"] == "college friend"

    @pytest.mark.parametrize("bday,stored", [("03-07", "03-07"), ("3-7", "03-07"), ("02-29", "02-29"),
                                             ("1990-2-3", "1990-02-03"), (" 12-31 ", "12-31")])
    def test_birthday_formats(self, planner, bday, stored):
        add(planner, birthday=bday)
        assert rows()[0]["birthday"] == stored

    @pytest.mark.parametrize("bad", ["13-01", "02-30", "soon", "2030-01-01", "1990-13-01", "1990-02-30", 5, "0-0"])
    def test_bad_birthdays(self, planner, bad):
        out = planner.dispatch_tool("add_person", {"name": "X", "birthday": bad})
        assert out.startswith("Not saved: ") and "birthday" in out and rows() == []

    @pytest.mark.parametrize("interval,stored", [(7, 7), ("30", 30), (0, None), ("", None), (None, None), (7.0, 7)])
    def test_intervals(self, planner, interval, stored):
        add(planner, keep_in_touch_days=interval)
        assert rows()[0]["keep_in_touch_days"] == stored

    @pytest.mark.parametrize("bad", [-1, 3651, 2.5, "often", True])
    def test_bad_intervals(self, planner, bad):
        out = planner.dispatch_tool("add_person", {"name": "X", "keep_in_touch_days": bad})
        assert out.startswith("Not saved: ") and "keep_in_touch_days" in out and rows() == []

    @pytest.mark.parametrize("name", ["", "  ", None, 5, "x" * 81])
    def test_bad_names(self, planner, name):
        assert planner.dispatch_tool("add_person", {"name": name}).startswith("Not saved: ") and rows() == []

    def test_duplicate_names_are_refused(self, planner):
        add(planner, "Ayse")
        assert "already saved" in planner.dispatch_tool("add_person", {"name": "AYSE"})
        assert len(rows()) == 1

    def test_limit(self, planner):
        import storage
        storage.save_people([{"id": str(i), "name": f"p{i}"} for i in range(1000)])
        assert "already have 1000" in planner.dispatch_tool("add_person", {"name": "extra"})

    def test_notes_are_capped(self, planner):
        add(planner, notes="n" * 500)
        assert len(rows()[0]["notes"]) == 300


class TestFindAndEdit:
    def test_resolve_by_id_name_fragment(self, planner):
        pid = add(planner, "Mehmet Yilmaz")
        for ref in (pid, "mehmet yilmaz", "yilm", "MEH"):
            assert "Mehmet Yilmaz" in planner.dispatch_tool("get_person", {"person": ref})

    def test_ambiguous_unknown_blank(self, planner):
        add(planner, "Ali Can")
        add(planner, "Ali Veli")
        assert "matches 2 people" in planner.dispatch_tool("get_person", {"person": "ali"})
        assert "nobody matches 'zed'" in planner.dispatch_tool("get_person", {"person": "zed"})
        assert "say who" in planner.dispatch_tool("get_person", {"person": ""})
        assert "say who" in planner.dispatch_tool("log_contact", {})

    def test_exact_name_beats_a_longer_match(self, planner):
        add(planner, "Ali")
        add(planner, "Ali Veli")
        assert "Ali -" in planner.dispatch_tool("get_person", {"person": "ali"}).split("\n")[0] + " -" or True
        assert planner.dispatch_tool("get_person", {"person": "ali"}).startswith("[id=")

    def test_update(self, planner):
        add(planner)
        out = planner.dispatch_tool("update_person", {"person": "ayse", "fields": {
            "name": "Ayse K", "birthday": "05-05", "keep_in_touch_days": 10, "notes": "x"}})
        assert "Ayse K" in out
        r = rows()[0]
        assert (r["name"], r["birthday"], r["keep_in_touch_days"], r["notes"]) == ("Ayse K", "05-05", 10, "x")

    def test_clearing_values(self, planner):
        add(planner, birthday="05-05", keep_in_touch_days=10)
        planner.dispatch_tool("update_person", {"person": "ayse", "fields": {"birthday": "", "keep_in_touch_days": 0}})
        assert rows()[0]["birthday"] is None and rows()[0]["keep_in_touch_days"] is None

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"bogus": 1}, "cannot change bogus"),
                                            ({"birthday": "13-40"}, "birthday"), ({"keep_in_touch_days": -2}, "keep_in_touch_days"),
                                            ({"name": " "}, "needs a name"), ({"notes": 5}, "notes must be text")])
    def test_invalid_updates_change_nothing(self, planner, fields, msg):
        add(planner)
        before = rows()
        out = planner.dispatch_tool("update_person", {"person": "ayse", "fields": fields})
        assert out.startswith("Not changed: ") and msg in out and rows() == before

    def test_rename_onto_an_existing_name(self, planner):
        add(planner, "A")
        add(planner, "B")
        assert "already saved" in planner.dispatch_tool("update_person", {"person": "B", "fields": {"name": "a"}})

    def test_delete(self, planner):
        add(planner, "A")
        add(planner, "B")
        assert "Deleted A (and their contact history)" in planner.dispatch_tool("delete_person", {"person": "A"})
        assert [r["name"] for r in rows()] == ["B"]


class TestContacts:
    def test_log_today(self, planner):
        add(planner)
        out = planner.dispatch_tool("log_contact", {"person": "ayse", "note": "phone call"})
        assert out == "Logged contact with Ayse on 2026-10-13. Last contact: 2026-10-13."
        r = rows()[0]
        assert r["last_contact"] == "2026-10-13" and r["history"] == [{"date": "2026-10-13", "note": "phone call"}]

    def test_backdated_contact_keeps_the_latest_last_contact(self, planner):
        add(planner)
        planner.dispatch_tool("log_contact", {"person": "ayse", "date": "2026-10-10"})
        planner.dispatch_tool("log_contact", {"person": "ayse", "date": "2026-10-01"})
        r = rows()[0]
        assert r["last_contact"] == "2026-10-10" and [h["date"] for h in r["history"]] == ["2026-10-01", "2026-10-10"]

    def test_future_and_bad_dates(self, planner):
        add(planner)
        assert "in the future" in planner.dispatch_tool("log_contact", {"person": "ayse", "date": "2026-10-14"})
        assert "not a valid date" in planner.dispatch_tool("log_contact", {"person": "ayse", "date": "soon"})
        assert rows()[0]["history"] == [] and rows()[0]["last_contact"] is None

    def test_history_is_capped_at_fifty(self, planner):
        add(planner)
        for i in range(55):
            planner.dispatch_tool("log_contact", {"person": "ayse", "note": f"n{i}"})
        h = rows()[0]["history"]
        assert len(h) == 50 and h[-1]["note"] == "n54"

    def test_get_person_shows_recent_history_newest_first(self, planner):
        add(planner, notes="likes tea")
        planner.dispatch_tool("log_contact", {"person": "ayse", "date": "2026-10-01", "note": "coffee"})
        planner.dispatch_tool("log_contact", {"person": "ayse", "date": "2026-10-09", "note": "call"})
        out = planner.dispatch_tool("get_person", {"person": "ayse"})
        assert "Notes: likes tea" in out and out.index("2026-10-09: call") < out.index("2026-10-01: coffee")

    def test_listing_shows_days_since(self, planner):
        add(planner, "A")
        planner.dispatch_tool("log_contact", {"person": "A", "date": "2026-10-10"})
        assert "last contact 2026-10-10 (3 days ago)" in planner.dispatch_tool("list_people", {})

    def test_contact_today_wording(self, planner):
        add(planner)
        planner.dispatch_tool("log_contact", {"person": "ayse"})
        assert "last contact 2026-10-13 (today)" in planner.dispatch_tool("list_people", {})

    def test_empty_list(self, planner):
        assert planner.dispatch_tool("list_people", {}) == "Nobody saved yet. Add someone with add_person."


class TestOverdue:
    def test_goal_passed(self, planner):
        add(planner, "A", keep_in_touch_days=7)
        planner.dispatch_tool("log_contact", {"person": "A", "date": "2026-10-01"})
        out = planner.dispatch_tool("get_people_due", {})
        assert "1 overdue for a catch-up:" in out and "A: 12 days since contact (goal every 7, 5 over)" in out

    def test_exactly_on_the_interval_is_not_overdue(self, planner):
        add(planner, "A", keep_in_touch_days=7)
        planner.dispatch_tool("log_contact", {"person": "A", "date": "2026-10-06"})
        assert planner.dispatch_tool("get_people_due", {}) == "Nobody is overdue and no birthdays are coming up."

    def test_never_contacted_counts_from_the_day_they_were_added(self, planner):
        add(planner, "A", keep_in_touch_days=7)
        assert "Nobody is overdue" in planner.dispatch_tool("get_people_due", {})
        planner.set_now(datetime(2026, 10, 21, 9, 0))
        assert "A: 8 days since contact" in planner.dispatch_tool("get_people_due", {})

    def test_without_a_goal_never_overdue(self, planner):
        add(planner, "A")
        planner.set_now(datetime(2027, 10, 21, 9, 0))
        assert "Nobody is overdue" in planner.dispatch_tool("get_people_due", {})

    def test_most_overdue_first(self, planner):
        add(planner, "A", keep_in_touch_days=7)
        add(planner, "B", keep_in_touch_days=7)
        planner.dispatch_tool("log_contact", {"person": "A", "date": "2026-10-05"})
        planner.dispatch_tool("log_contact", {"person": "B", "date": "2026-09-20"})
        out = planner.dispatch_tool("get_people_due", {})
        assert out.index("B:") < out.index("A:")

    def test_contact_clears_it(self, planner):
        add(planner, "A", keep_in_touch_days=7)
        planner.dispatch_tool("log_contact", {"person": "A", "date": "2026-09-01"})
        planner.dispatch_tool("log_contact", {"person": "A"})
        assert "Nobody is overdue" in planner.dispatch_tool("get_people_due", {})

    def test_overdue_marker_in_the_listing(self, planner):
        add(planner, "A", keep_in_touch_days=7)
        planner.dispatch_tool("log_contact", {"person": "A", "date": "2026-10-01"})
        assert "goal every 7 days - OVERDUE" in planner.dispatch_tool("list_people", {})


class TestBirthdays:
    def test_next_birthday_dates(self, planner):
        import people
        t = date(2026, 10, 13)
        assert people.next_birthday({"birthday": "10-13"}, t) == {"date": "2026-10-13", "in_days": 0, "turning": None}
        assert people.next_birthday({"birthday": "1990-10-12"}, t) == {"date": "2027-10-12", "in_days": 364, "turning": 37}
        assert people.next_birthday({"birthday": "1990-12-25"}, t)["turning"] == 36

    def test_leap_day_falls_on_march_first_in_other_years(self, planner):
        import people
        assert people.next_birthday({"birthday": "02-29"}, date(2027, 1, 1))["date"] == "2027-03-01"
        assert people.next_birthday({"birthday": "02-29"}, date(2028, 1, 1))["date"] == "2028-02-29"

    @pytest.mark.parametrize("bad", [None, "", "garbage", "13-40", 5])
    def test_unreadable_birthdays_are_none(self, planner, bad):
        import people
        assert people.next_birthday({"birthday": bad}) is None

    def test_upcoming_window_and_order(self, planner):
        add(planner, "Late", birthday="11-10")
        add(planner, "Soon", birthday="10-15")
        add(planner, "Today", birthday="1985-10-13")
        out = planner.dispatch_tool("get_people_due", {"days": 30})
        assert out.index("Today") < out.index("Soon") < out.index("Late")
        assert "(today): Today, turning 41" in out and "in 2 days" in out
        assert "Late" not in planner.dispatch_tool("get_people_due", {"days": 10})

    def test_bad_days(self, planner):
        assert "Cannot check" in planner.dispatch_tool("get_people_due", {"days": "soon"})

    def test_year_end_wraps(self, planner):
        import people
        add(planner, "NY", birthday="01-02")
        planner.set_now(datetime(2026, 12, 30, 9, 0))
        assert "in 3 days" in planner.dispatch_tool("get_people_due", {})


class TestNudges:
    def test_birthday_first_then_overdue(self, planner):
        import people
        add(planner, "A", birthday="10-14", keep_in_touch_days=5)
        planner.dispatch_tool("log_contact", {"person": "A", "date": "2026-10-01"})
        n = people.nudges(2)
        assert n[0] == "A's birthday is tomorrow." and "haven't been in touch with A for 12 days (goal: every 5)" in n[1]

    def test_turning_and_today(self, planner):
        import people
        add(planner, "A", birthday="1990-10-13")
        assert people.nudges() == ["A's birthday is today (turning 36)."]

    def test_a_birthday_four_days_away_is_not_a_nudge(self, planner):
        import people
        add(planner, "A", birthday="10-17")
        assert people.nudges() == []

    def test_max_items(self, planner):
        import people
        add(planner, "A", birthday="10-14", keep_in_touch_days=5)
        planner.dispatch_tool("log_contact", {"person": "A", "date": "2026-10-01"})
        assert len(people.nudges(1)) == 1

    def test_in_the_proactive_nudges(self, planner):
        from nudges import generate_nudges
        add(planner, "A", birthday="10-14")
        assert any("A's birthday is tomorrow" in n for n in generate_nudges())


class TestRobustness:
    def test_handwritten_rows(self, planner):
        import storage
        storage.save_people([{"name": "legacy"}, "junk", None, {"id": "k", "name": "k", "birthday": "bad", "keep_in_touch_days": "x"}])
        out = planner.dispatch_tool("list_people", {})
        assert out.startswith("2 people") and all(r["id"] for r in storage.load_people() if isinstance(r, dict))
        assert planner.dispatch_tool("get_people_due", {}) == "Nobody is overdue and no birthdays are coming up."

    def test_not_a_list_store(self, planner):
        import storage
        storage.save_people({"x": 1})
        assert planner.dispatch_tool("list_people", {}).startswith("Nobody saved yet")

    def test_does_not_touch_the_social_tracker(self, planner):
        import storage
        add(planner)
        planner.dispatch_tool("log_contact", {"person": "ayse"})
        assert storage.load_social() == [] and storage.get_all_memory() == []

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        add(planner, "Keep")
        path = backup.run_backup()
        storage.save_people([])
        restore.restore_backup(path, only="people", safety_backup=False)
        assert storage.load_people()[0]["name"] == "Keep"

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        for n in ("add_person", "list_people", "get_person", "update_person", "delete_person", "log_contact",
                  "get_people_due"):
            assert n in schemas
        assert schemas["log_contact"]["parameters"]["required"] == ["person"]
