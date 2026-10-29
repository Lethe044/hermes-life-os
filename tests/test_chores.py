"""Chores: recurring maintenance with intervals counted from the last completion."""

from __future__ import annotations

import pytest


def chore(p, name="Water plants", every="weekly", **kw):
    out = p.dispatch_tool("add_chore", {"name": name, "every": every, **kw})
    assert out.startswith("Chore added: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_chores()


class TestParseEvery:
    @pytest.mark.parametrize("value,expected", [
        ("daily", (1, "days")), ("weekly", (1, "weeks")), ("biweekly", (2, "weeks")), ("fortnightly", (2, "weeks")),
        ("monthly", (1, "months")), ("quarterly", (3, "months")), ("yearly", (12, "months")), ("Annually", (12, "months")),
        ("every 10 days", (10, "days")), ("10 days", (10, "days")), ("every 2 weeks", (2, "weeks")),
        ("3 months", (3, "months")), ("every month", (1, "months")), ("every week", (1, "weeks")),
        ("2 years", (24, "months")), ("every 5d", (5, "days")), ("  EVERY   3  Months ", (3, "months")),
        (7, (7, "days")), (7.0, (7, "days")), ("every year", (12, "months"))])
    def test_good(self, planner, value, expected):
        import chores
        assert chores.parse_every(value) == expected

    def test_number_with_unit(self, planner):
        import chores
        assert chores.parse_every(2, "weeks") == (2, "weeks")
        assert chores.parse_every(1, "years") == (12, "months")

    @pytest.mark.parametrize("value", [None, True, "", "sometimes", "every", "0 days", 0, -3, 2.5, "every 1.5 weeks", [], {}, "5",
                                       "every 2 fortnights", "weekly!"])
    def test_bad(self, planner, value):
        import chores
        with pytest.raises(ValueError):
            chores.parse_every(value)

    @pytest.mark.parametrize("value", ["366 days", "53 weeks", "25 months", "3 years"])
    def test_limits(self, planner, value):
        import chores
        with pytest.raises(ValueError, match="can be 1 to"):
            chores.parse_every(value)

    def test_bad_unit_for_a_number(self, planner):
        import chores
        with pytest.raises(ValueError):
            chores.parse_every(2, "fortnights")


class TestAdd:
    def test_shape_and_output(self, planner):
        out = planner.dispatch_tool("add_chore", {"name": " Water   plants ", "every": "weekly", "notes": " n "})
        assert out.startswith("Chore added: Water plants (every week): due today (2026-10-13), never done [id=")
        c = rows()[0]
        assert set(c) == {"id", "name", "every", "unit", "start", "last_done", "notes", "created", "history"}
        assert (c["every"], c["unit"], c["start"], c["last_done"], c["notes"], c["created"], c["history"]) == \
               (1, "weeks", "2026-10-13", None, "n", "2026-10-13", [])
        assert len(c["id"]) == 8

    def test_start_dates(self, planner):
        chore(planner, "A", "monthly", start="2026-10-10")
        chore(planner, "B", "monthly", start="in 3 days")
        chore(planner, "C", "monthly", start="friday")
        assert [c["start"] for c in rows()] == ["2026-10-10", "2026-10-16", "2026-10-16"]
        assert planner.dispatch_tool("get_chores", {}).splitlines()[1].startswith("- A (every month): overdue by 3 days")

    @pytest.mark.parametrize("kw,msg", [
        ({"name": ""}, "cannot be empty"), ({"name": None}, "cannot be empty"), ({"name": "n" * 61}, "at most 60"),
        ({"name": 5}, "must be text"), ({"every": "sometimes"}, "say how often"), ({"every": None}, "say how often"),
        ({"start": "never"}, "couldn't understand the start date"), ({"start": "2020-01-01"}, "more than 365 days back"),
        ({"notes": "n" * 161}, "at most 160"), ({"notes": 3}, "must be text")])
    def test_rejected(self, planner, kw, msg):
        args = {"name": "X", "every": "weekly", **kw}
        out = planner.dispatch_tool("add_chore", args)
        assert out.startswith("Chore not added: ") and msg in out
        assert rows() == []

    def test_duplicate_name_any_case(self, planner):
        chore(planner)
        assert "already a chore called 'water plants'" in planner.dispatch_tool("add_chore", {"name": "water plants", "every": "daily"})
        assert len(rows()) == 1

    def test_limit(self, planner):
        import storage
        storage.save_chores([{"id": f"i{n}", "name": f"c{n}", "every": 1, "unit": "days", "start": "2026-10-13"} for n in range(200)])
        assert "already have 200 chores" in planner.dispatch_tool("add_chore", {"name": "More", "every": "daily"})


class TestComplete:
    def test_next_due_counts_from_the_completion(self, planner):
        chore(planner, "Filter", "every 3 months", start="2026-10-01")
        out = planner.dispatch_tool("complete_chore", {"chore": "filter"})
        assert out.startswith("Marked 'Filter' done on 2026-10-13. Next: Filter (every 3 months): due in 92 days (2027-01-13), last done 2026-10-13")
        assert rows()[0]["last_done"] == "2026-10-13" and rows()[0]["history"] == ["2026-10-13"]

    @pytest.mark.parametrize("every,expected", [("daily", "2026-10-13"), ("weekly", "2026-10-19"), ("every 10 days", "2026-10-22"),
                                                 ("monthly", "2026-11-12"), ("yearly", "2027-10-12")])
    def test_intervals(self, planner, every, expected):
        chore(planner, "X", every)
        planner.dispatch_tool("complete_chore", {"chore": "X", "date": "yesterday"})
        import chores
        assert chores.status(rows()[0])["due"] == expected

    def test_month_end_is_clamped(self, planner):
        chore(planner, "X", "monthly")
        planner.dispatch_tool("update_chore", {"chore": "X", "fields": {"last_done": "2026-10-01"}})
        planner.set_now(__import__("datetime").datetime(2026, 10, 13, 9))
        import chores, storage
        r = storage.load_chores()
        r[0]["last_done"] = "2026-01-31"
        assert chores.status(r[0])["due"] == "2026-02-28"

    def test_a_late_chore_does_not_pile_up(self, planner):
        chore(planner, "X", "weekly", start="2026-09-01")
        planner.dispatch_tool("complete_chore", {"chore": "X"})
        import chores
        assert chores.status(rows()[0])["in_days"] == 7

    def test_errors(self, planner):
        chore(planner)
        planner.dispatch_tool("complete_chore", {"chore": "water", "date": "2026-10-10"})
        assert "already marked done on 2026-10-10" in planner.dispatch_tool("complete_chore", {"chore": "water", "date": "2026-10-10"})
        assert "already done later, on 2026-10-10" in planner.dispatch_tool("complete_chore", {"chore": "water", "date": "2026-10-09"})
        assert "cannot be in the future" in planner.dispatch_tool("complete_chore", {"chore": "water", "date": "tomorrow"})
        assert "couldn't understand the date" in planner.dispatch_tool("complete_chore", {"chore": "water", "date": "soon"})
        assert "Chore not completed: no chore matches 'zzz'" in planner.dispatch_tool("complete_chore", {"chore": "zzz"})
        assert "say which chore" in planner.dispatch_tool("complete_chore", {})

    def test_history_is_capped(self, planner):
        import chores, storage
        chore(planner)
        r = storage.load_chores()
        r[0]["history"] = [f"2026-01-{n:02d}" for n in range(1, 29)] * 3
        storage.save_chores(r)
        chores.complete_chore("water")
        assert len(rows()[0]["history"]) == 60 and rows()[0]["history"][-1] == "2026-10-13"


class TestListAndNudges:
    def test_order_and_filter(self, planner):
        chore(planner, "Late", "weekly", start="2026-10-10")
        chore(planner, "Today", "weekly")
        chore(planner, "Soon", "weekly", start="2026-10-18")
        chore(planner, "Far", "weekly", start="2026-12-01")
        out = planner.dispatch_tool("get_chores", {})
        assert [l.split(" (")[0] for l in out.splitlines()[1:]] == ["- Late", "- Today", "- Soon", "- Far"]
        due = planner.dispatch_tool("get_chores", {"filter": "due"})
        assert due.startswith("3 chores due within 7 days or overdue:") and "Far" not in due
        assert planner.dispatch_tool("get_chores", {"filter": "x"}) == "Cannot show chores: filter must be all or due."

    def test_empty(self, planner):
        assert planner.dispatch_tool("get_chores", {}).startswith("No chores yet.")
        assert planner.dispatch_tool("get_chores", {"filter": "due"}) == "Nothing is due in the next 7 days."

    def test_nudge_only_for_due_or_overdue(self, planner):
        import chores
        chore(planner, "Far", "weekly", start="2026-10-20")
        assert chores.nudges() == [] and chores.agenda_lines() == []
        chore(planner, "Today", "weekly")
        chore(planner, "Late", "weekly", start="2026-10-11")
        assert chores.nudges() == ["Chore 'Late' is overdue by 2 days."]
        assert chores.nudges(2)[1] == "Chore 'Today' is due today."
        assert chores.agenda_lines() == ["Late (overdue by 2 days)", "Today (due today)"]

    def test_unreadable_rows_are_skipped(self, planner):
        import chores, storage
        storage.save_chores([{"id": "a", "name": "bad", "every": "x", "unit": "days"}, "junk", 5,
                             {"id": "b", "name": "ok", "every": 1, "unit": "days", "start": "2026-10-13"}])
        assert [x["item"]["name"] for x in chores.listing()] == ["ok"]


class TestUpdateDelete:
    def test_update_fields(self, planner):
        chore(planner)
        out = planner.dispatch_tool("update_chore", {"chore": "water", "fields": {"name": "Water the plants", "every": "every 2 weeks",
                                                                                "start": "2026-10-20", "notes": "x"}})
        assert out.startswith("Chore updated: Water the plants (every 2 weeks): due in 7 days (2026-10-20)")
        c = rows()[0]
        assert (c["every"], c["unit"], c["notes"]) == (2, "weeks", "x")

    def test_last_done_can_be_set_and_cleared(self, planner):
        chore(planner)
        planner.dispatch_tool("update_chore", {"chore": "water", "fields": {"last_done": "2026-10-10"}})
        assert rows()[0]["last_done"] == "2026-10-10"
        planner.dispatch_tool("update_chore", {"chore": "water", "fields": {"last_done": ""}})
        assert rows()[0]["last_done"] is None
        assert "cannot be in the future" in planner.dispatch_tool("update_chore", {"chore": "water", "fields": {"last_done": "tomorrow"}})

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ("x", "nothing to change"), ({"color": 1}, "cannot change color"),
                                            ({"every": "never"}, "say how often"), ({"name": ""}, "cannot be empty")])
    def test_bad_updates_change_nothing(self, planner, fields, msg):
        chore(planner)
        before = rows()
        assert msg in planner.dispatch_tool("update_chore", {"chore": "water", "fields": fields})
        assert rows() == before

    def test_rename_clash(self, planner):
        chore(planner, "A")
        chore(planner, "B")
        assert "already a chore called 'a'" in planner.dispatch_tool("update_chore", {"chore": "B", "fields": {"name": "a"}})

    def test_delete(self, planner):
        cid = chore(planner)
        assert planner.dispatch_tool("delete_chore", {"chore": cid}) == "Deleted chore Water plants. This can't be undone."
        assert rows() == []

    def test_ambiguous_reference(self, planner):
        chore(planner, "Water plants")
        chore(planner, "Water lawn")
        assert "matches 2 chores" in planner.dispatch_tool("complete_chore", {"chore": "water"})

    def test_missing_ids_are_assigned_on_first_use(self, planner):
        import storage
        storage.save_chores([{"name": "x", "every": 1, "unit": "days", "start": "2026-10-13"}])
        planner.dispatch_tool("get_chores", {})
        assert len(rows()[0]["id"]) == 8
