"""Countdowns: days until and since."""

from __future__ import annotations

from datetime import datetime

import pytest


def add(p, name="Holiday", date="2026-12-20", **kw):
    out = p.dispatch_tool("add_countdown", {"name": name, "date": date, **kw})
    assert out.startswith("Countdown added: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_countdowns()


class TestAdd:
    def test_shape(self, planner):
        cid = add(planner)
        assert rows() == [{"id": cid, "name": "Holiday", "date": "2026-12-20", "repeat": None, "notes": "",
                           "created": "2026-10-13"}]

    def test_output_future_past_and_today(self, planner):
        assert planner.dispatch_tool("add_countdown", {"name": "A", "date": "2026-12-20"}).startswith(
            "Countdown added: A: in 68 days (Sun 2026-12-20) [id=")
        assert planner.dispatch_tool("add_countdown", {"name": "B", "date": "2026-08-01"}).startswith(
            "Countdown added: B: 73 days since 2026-08-01 [id=")
        assert planner.dispatch_tool("add_countdown", {"name": "C", "date": "2026-10-13"}).startswith(
            "Countdown added: C: today (Tue 2026-10-13) [id=")
        assert planner.dispatch_tool("add_countdown", {"name": "D", "date": "2026-10-14"}).startswith(
            "Countdown added: D: tomorrow")
        assert planner.dispatch_tool("add_countdown", {"name": "E", "date": "2026-10-12"}).startswith(
            "Countdown added: E: 1 day since 2026-10-12")

    def test_date_is_normalized(self, planner):
        add(planner, date="2026-1-5")
        assert rows()[0]["date"] == "2026-01-05"

    @pytest.mark.parametrize("word", ["yearly", "Annual", "every year", "annually"])
    def test_repeat_aliases(self, planner, word):
        add(planner, repeat=word)
        assert rows()[0]["repeat"] == "yearly"

    @pytest.mark.parametrize("word", [None, "", "none", "once"])
    def test_no_repeat(self, planner, word):
        add(planner, repeat=word)
        assert rows()[0]["repeat"] is None

    @pytest.mark.parametrize("args,msg", [({"name": "", "date": "2026-12-20"}, "needs a name"),
                                          ({"name": 5, "date": "2026-12-20"}, "needs a name"),
                                          ({"name": "x" * 61, "date": "2026-12-20"}, "at most 60"),
                                          ({"name": "x", "date": "soon"}, "not a valid date"),
                                          ({"name": "x", "date": None}, "date must be written"),
                                          ({"name": "x", "date": "2026-12-20", "repeat": "monthly"}, "repeat must be")])
    def test_invalid(self, planner, args, msg):
        out = planner.dispatch_tool("add_countdown", args)
        assert out.startswith("Countdown not added: ") and msg in out and rows() == []

    def test_duplicate_names(self, planner):
        add(planner)
        assert "already a countdown called 'HOLIDAY'" in planner.dispatch_tool("add_countdown", {"name": "HOLIDAY", "date": "2026-12-21"})

    def test_limit(self, planner):
        import storage
        storage.save_countdowns([{"id": str(i), "name": f"c{i}", "date": "2026-12-20"} for i in range(300)])
        assert "already have 300" in planner.dispatch_tool("add_countdown", {"name": "x", "date": "2026-12-20"})


class TestOccurrence:
    def test_yearly_next_occurrence_and_years(self, planner):
        import countdowns
        item = {"date": "2019-10-14", "repeat": "yearly"}
        assert countdowns.occurrence(item) == {"date": "2026-10-14", "in_days": 1, "years": 7}

    def test_yearly_today_counts_as_today(self, planner):
        import countdowns
        assert countdowns.occurrence({"date": "2020-10-13", "repeat": "yearly"})["in_days"] == 0

    def test_yearly_rolls_to_next_year_after_the_day(self, planner):
        import countdowns
        assert countdowns.occurrence({"date": "2020-10-12", "repeat": "yearly"}) == {"date": "2027-10-12", "in_days": 364, "years": 7}

    def test_yearly_with_a_future_original_date(self, planner):
        import countdowns
        occ = countdowns.occurrence({"date": "2030-11-01", "repeat": "yearly"})
        assert occ["date"] == "2026-11-01" and occ["years"] == -4

    def test_leap_day(self, planner):
        import countdowns
        assert countdowns.occurrence({"date": "2020-02-29", "repeat": "yearly"}, __import__("datetime").date(2027, 1, 1))["date"] == "2027-03-01"
        assert countdowns.occurrence({"date": "2020-02-29", "repeat": "yearly"}, __import__("datetime").date(2028, 1, 1))["date"] == "2028-02-29"

    @pytest.mark.parametrize("bad", [None, "", "garbage", 5, "2026-13-01"])
    def test_unreadable_dates(self, planner, bad):
        import countdowns
        assert countdowns.occurrence({"date": bad}) is None

    def test_a_yearly_one_never_counts_as_past(self, planner):
        import countdowns
        add(planner, "Anniv", "2019-10-12", repeat="yearly")
        assert all(x["in_days"] >= 0 for x in countdowns.listing())

    def test_year_wrap(self, planner):
        import countdowns
        planner.set_now(datetime(2026, 12, 30, 9, 0))
        assert countdowns.occurrence({"date": "2000-01-02", "repeat": "yearly"})["in_days"] == 3


class TestShow:
    def test_empty(self, planner):
        assert planner.dispatch_tool("get_countdowns", {}) == "No countdowns yet. Add one with add_countdown."

    def test_order_upcoming_then_past(self, planner):
        add(planner, "Far", "2027-01-01")
        add(planner, "Near", "2026-10-20")
        add(planner, "Old", "2026-01-01")
        add(planner, "Recent", "2026-10-01")
        out = planner.dispatch_tool("get_countdowns", {}).split("\n")
        assert out[0] == "4 countdowns:"
        assert [l[2:].split(":")[0] for l in out[1:]] == ["Near", "Far", "Recent", "Old"]

    def test_past_ones_can_be_hidden(self, planner):
        add(planner, "Future", "2026-12-01")
        add(planner, "Past", "2026-01-01")
        out = planner.dispatch_tool("get_countdowns", {"include_past": False})
        assert "Future" in out and "Past" not in out and out.startswith("1 countdown:")

    def test_yearly_label(self, planner):
        add(planner, "Anniv", "2019-10-14", repeat="yearly")
        assert "Anniv: tomorrow (Wed 2026-10-14), year 7, yearly [id=" in planner.dispatch_tool("get_countdowns", {})

    def test_unreadable_rows_are_skipped(self, planner):
        import storage
        storage.save_countdowns([{"id": "a", "name": "bad", "date": "x"}, "junk", None, {"id": "b", "name": "ok", "date": "2026-12-01"}])
        out = planner.dispatch_tool("get_countdowns", {})
        assert out.startswith("1 countdown:") and "ok" in out


class TestUpdateDelete:
    def test_update(self, planner):
        add(planner)
        out = planner.dispatch_tool("update_countdown", {"countdown": "holi", "fields": {
            "name": "Trip", "date": "2026-12-25", "repeat": "yearly", "notes": "n"}})
        assert out.startswith("Countdown updated: Trip: in 73 days (Fri 2026-12-25)")
        r = rows()[0]
        assert (r["name"], r["date"], r["repeat"], r["notes"]) == ("Trip", "2026-12-25", "yearly", "n")

    def test_clear_repeat(self, planner):
        add(planner, repeat="yearly")
        planner.dispatch_tool("update_countdown", {"countdown": "holiday", "fields": {"repeat": ""}})
        assert rows()[0]["repeat"] is None

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"id": "x"}, "cannot change id"),
                                            ({"name": ""}, "needs a name"), ({"date": "x"}, "not a valid date"),
                                            ({"repeat": "weekly"}, "repeat must be"), ({"notes": 5}, "notes must be text"),
                                            ("x", "nothing to change")])
    def test_invalid_updates_change_nothing(self, planner, fields, msg):
        add(planner)
        before = rows()
        out = planner.dispatch_tool("update_countdown", {"countdown": "holiday", "fields": fields})
        assert out.startswith("Countdown not changed: ") and msg in out and rows() == before

    def test_rename_onto_an_existing_name(self, planner):
        add(planner, "A")
        add(planner, "B")
        assert "already a countdown called 'a'" in planner.dispatch_tool("update_countdown", {"countdown": "B", "fields": {"name": "a"}})

    def test_resolve_ambiguous_exact_unknown(self, planner):
        add(planner, "Trip one")
        add(planner, "Trip two")
        assert "matches 2 countdowns" in planner.dispatch_tool("delete_countdown", {"countdown": "trip"})
        assert "no countdown matches 'zed'" in planner.dispatch_tool("delete_countdown", {"countdown": "zed"})
        assert "say which countdown" in planner.dispatch_tool("delete_countdown", {})
        add(planner, "Trip")
        assert planner.dispatch_tool("delete_countdown", {"countdown": "trip"}) == "Deleted countdown Trip. This can't be undone."
        assert len(rows()) == 2

    def test_delete_by_id(self, planner):
        cid = add(planner)
        planner.dispatch_tool("delete_countdown", {"countdown": cid})
        assert rows() == []


class TestNudgesAndAgenda:
    def test_nudge_window(self, planner):
        import countdowns
        add(planner, "Today", "2026-10-13")
        add(planner, "Tomorrow", "2026-10-14")
        add(planner, "Edge", "2026-10-15")
        add(planner, "Far", "2026-10-16")
        add(planner, "Past", "2026-10-01")
        assert countdowns.nudges(5) == ["Today is today.", "Tomorrow is tomorrow.", "Edge is in 2 days."]
        assert countdowns.nudges(1) == ["Today is today."]

    def test_agenda_window_is_a_week(self, planner):
        add(planner, "In week", "2026-10-20")
        add(planner, "Beyond", "2026-10-21")
        add(planner, "Past", "2026-10-01")
        out = planner.dispatch_tool("get_today_agenda", {})
        assert "Countdowns:" in out and "In week: in 7 days" in out and "Beyond" not in out and "Past" not in out

    def test_agenda_without_countdowns_has_no_section(self, planner):
        assert "Countdowns" not in planner.dispatch_tool("get_today_agenda", {})

    def test_in_the_planner_nudges(self, planner):
        import nudges
        add(planner, "Exam", "2026-10-14")
        assert nudges._planner_nudges() == ["Exam is tomorrow."]

    def test_failing_source_does_not_block_others(self, planner, monkeypatch):
        import nudges, countdowns
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        monkeypatch.setattr(countdowns, "nudges", lambda *a, **k: 1 / 0)
        assert any("Ayse" in n for n in nudges._planner_nudges())


class TestRobustness:
    def test_not_a_list_store(self, planner):
        import storage
        storage.save_countdowns({"x": 1})
        assert planner.dispatch_tool("get_countdowns", {}).startswith("No countdowns yet")

    def test_handwritten_rows_get_ids(self, planner):
        import storage
        storage.save_countdowns([{"name": "legacy", "date": "2026-12-01"}])
        planner.dispatch_tool("get_countdowns", {})
        assert storage.load_countdowns()[0]["id"]

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        add(planner)
        path = backup.run_backup()
        storage.save_countdowns([])
        restore.restore_backup(path, only="countdowns", safety_backup=False)
        assert rows()[0]["name"] == "Holiday"

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        assert schemas["add_countdown"]["parameters"]["required"] == ["name", "date"]
        assert schemas["delete_countdown"]["parameters"]["required"] == ["countdown"]
