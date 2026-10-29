"""Routines: named checklists ticked per day, with streaks."""

from __future__ import annotations

from datetime import datetime

import pytest

# the frozen clock is Tuesday 2026-10-13


def routine(p, name="Morning", steps=("Drink water", "Stretch", "Journal"), **kw):
    out = p.dispatch_tool("add_routine", {"name": name, "steps": list(steps), **kw})
    assert out.startswith("Routine added: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_routines()


def tick(p, step="all", **kw):
    return p.dispatch_tool("check_routine_step", {"routine": "morning", "step": step, **kw})


class TestParseDays:
    @pytest.mark.parametrize("value,expected", [
        (None, None), ("", None), ("daily", None), ("Every day", None), ("weekdays", [0, 1, 2, 3, 4]), ("weekends", [5, 6]),
        ("mon, wed, fri", [0, 2, 4]), ("Monday;Wednesday", [0, 2]), (["sat", "sun"], [5, 6]), ("fri mon", [0, 4]),
        ("mon,tue,wed,thu,fri,sat,sun", None), ([], None), (["mon", "mon"], [0])])
    def test_good(self, planner, value, expected):
        import routines
        assert routines.parse_days(value) == expected

    @pytest.mark.parametrize("value", ["funday", ["mon", 3], 3, {"a": 1}, "mon, xyz", True])
    def test_bad(self, planner, value):
        import routines
        with pytest.raises(ValueError):
            routines.parse_days(value)


class TestAdd:
    def test_shape_and_output(self, planner):
        out = planner.dispatch_tool("add_routine", {"name": " Morning ", "steps": [" Drink  water ", "Stretch"], "days": "weekdays"})
        assert out.startswith("Routine added: Morning (weekdays): 0/2 today [id=")
        assert out.splitlines()[1:] == ["  [ ] Drink water", "  [ ] Stretch"]
        r = rows()[0]
        assert set(r) == {"id", "name", "steps", "days", "created", "log"}
        assert [s["text"] for s in r["steps"]] == ["Drink water", "Stretch"] and r["days"] == [0, 1, 2, 3, 4] and r["log"] == {}
        assert all(len(s["id"]) == 8 for s in r["steps"]) and len({s["id"] for s in r["steps"]}) == 2

    def test_steps_as_text(self, planner):
        out = planner.dispatch_tool("add_routine", {"name": "Evening", "steps": "Dishes; Lights off\nLock door"})
        assert out.startswith("Routine added: Evening (daily)")
        assert [s["text"] for s in rows()[0]["steps"]] == ["Dishes", "Lights off", "Lock door"]

    @pytest.mark.parametrize("kw,msg", [
        ({"name": ""}, "cannot be empty"), ({"name": "n" * 41}, "at most 40"), ({"steps": []}, "at least one step"),
        ({"steps": ["", "  "]}, "at least one step"), ({"steps": None}, "steps must be a list"), ({"steps": [1, 2]}, "steps must be a list"),
        ({"steps": ["a", "A"]}, "same text"), ({"steps": ["x" * 81]}, "at most 80"), ({"steps": [str(n) for n in range(21)]}, "at most 20 steps"),
        ({"days": "funday"}, "not a weekday")])
    def test_rejected(self, planner, kw, msg):
        out = planner.dispatch_tool("add_routine", {"name": "R", "steps": ["a"], **kw})
        assert out.startswith("Routine not added: ") and msg in out
        assert rows() == []

    def test_duplicate_and_limit(self, planner):
        routine(planner)
        assert "already a routine called 'morning'" in planner.dispatch_tool("add_routine", {"name": "morning", "steps": ["a"]})
        import storage
        storage.save_routines([{"id": f"i{n}", "name": f"r{n}", "steps": [{"id": "s", "text": "a"}]} for n in range(20)])
        assert "already have 20 routines" in planner.dispatch_tool("add_routine", {"name": "More", "steps": ["a"]})


class TestTicking:
    def test_tick_one_then_all(self, planner):
        routine(planner)
        out = tick(planner, "water")
        assert out.startswith("Ticked on 2026-10-13: 1/3 steps done.\nMorning (daily): 1/3 today [id=")
        assert "[x] Drink water" in out and "[ ] Stretch" in out
        out = tick(planner)
        assert out.startswith("Ticked on 2026-10-13: 3/3 steps done. 'Morning' is complete - streak 1 day.")

    def test_untick(self, planner):
        routine(planner)
        tick(planner)
        assert tick(planner, "stretch", undo=True).startswith("Unticked on 2026-10-13: 2/3 steps done.")
        assert tick(planner, "all", undo=True).startswith("Unticked on 2026-10-13: 0/3 steps done.")
        assert rows()[0]["log"] == {}

    def test_ticking_twice_is_harmless(self, planner):
        routine(planner)
        tick(planner, "water")
        assert tick(planner, "water").startswith("Ticked on 2026-10-13: 1/3")

    def test_backdated_tick(self, planner):
        routine(planner)
        out = tick(planner, "all", date="2026-10-12")
        assert out == "Ticked on 2026-10-12: 3/3 steps done."
        assert list(rows()[0]["log"]) == ["2026-10-12"]

    @pytest.mark.parametrize("kw,msg", [({"date": "2026-10-14"}, "has not happened yet"), ({"date": "2026-10-01"}, "up to 7 days back"),
                                        ({"date": "x"}, "not a valid date"), ({"step": "zzz"}, "no step matches 'zzz'"),
                                        ({"step": ""}, "say which step"), ({"step": None}, "say which step")])
    def test_errors(self, planner, kw, msg):
        routine(planner)
        out = planner.dispatch_tool("check_routine_step", {"routine": "morning", "step": "water", **kw})
        assert out.startswith("Step not changed: ") and msg in out
        assert rows()[0]["log"] == {}

    def test_ambiguous_step(self, planner):
        routine(planner, steps=["Read book", "Read news"])
        assert "matches 2 steps" in tick(planner, "read")

    def test_old_log_days_are_pruned(self, planner):
        import storage
        routine(planner)
        r = storage.load_routines()
        r[0]["log"] = {"2025-01-01": ["x"], "2026-10-12": ["y"]}
        storage.save_routines(r)
        tick(planner, "water")
        assert "2025-01-01" not in rows()[0]["log"] and "2026-10-12" in rows()[0]["log"]


class TestStreak:
    def fill(self, days_back):
        import storage
        r = storage.load_routines()
        ids = [s["id"] for s in r[0]["steps"]]
        for b in days_back:
            r[0]["log"][f"2026-10-{13 - b:02d}"] = list(ids)
        storage.save_routines(r)

    def test_streak_counts_complete_days_and_incomplete_today_does_not_break(self, planner):
        import routines
        routine(planner)
        self.fill([1, 2, 3])
        assert routines.streak(rows()[0]) == 3
        tick(planner, "all")
        assert routines.streak(rows()[0]) == 4
        assert "streak 4 days" in planner.dispatch_tool("get_routines", {})

    def test_a_missed_day_breaks_it(self, planner):
        import routines
        routine(planner)
        self.fill([1, 3, 4])
        assert routines.streak(rows()[0]) == 1

    def test_unscheduled_days_are_skipped(self, planner):
        import routines
        routine(planner, days="weekdays")
        # Fri 9th and Mon 12th are done, the weekend between them is not scheduled
        import storage
        r = storage.load_routines()
        ids = [s["id"] for s in r[0]["steps"]]
        r[0]["log"] = {"2026-10-12": ids, "2026-10-09": ids}
        storage.save_routines(r)
        assert routines.streak(rows()[0]) == 2

    def test_not_scheduled_today_note(self, planner):
        routine(planner, days="weekends")
        assert "(weekends): 0/3 today, not scheduled today" in planner.dispatch_tool("get_routines", {})

    def test_removed_steps_do_not_count_as_done(self, planner):
        import routines
        routine(planner)
        tick(planner)
        planner.dispatch_tool("update_routine", {"routine": "morning", "fields": {"steps": ["Stretch", "New one"]}})
        assert routines.progress(rows()[0]) == (1, 2)


class TestAgendaAndUpdate:
    def test_agenda_lines(self, planner):
        import routines
        routine(planner)
        routine(planner, "Weekend", ["a"], days="weekends")
        assert routines.agenda_lines() == ["Morning: 0 of 3 steps done (next: Drink water)"]
        tick(planner, "water")
        assert routines.agenda_lines() == ["Morning: 1 of 3 steps done (next: Stretch)"]
        tick(planner)
        assert routines.agenda_lines() == []

    def test_update_keeps_ticks_of_unchanged_steps(self, planner):
        routine(planner)
        tick(planner, "stretch")
        out = planner.dispatch_tool("update_routine", {"routine": "morning", "fields": {"name": "AM", "days": "weekdays",
                                                                                      "steps": ["Stretch", "Coffee"]}})
        assert out.startswith("Routine updated: AM (weekdays): 1/2 today")
        assert "[x] Stretch" in out and "[ ] Coffee" in out

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"x": 1}, "cannot change x"), ({"steps": []}, "at least one step"),
                                            ({"days": "nope"}, "not a weekday"), ({"name": ""}, "cannot be empty")])
    def test_bad_updates(self, planner, fields, msg):
        routine(planner)
        before = rows()
        assert msg in planner.dispatch_tool("update_routine", {"routine": "morning", "fields": fields})
        assert rows() == before

    def test_rename_clash_and_delete(self, planner):
        routine(planner)
        routine(planner, "Evening", ["a"])
        assert "already a routine called 'morning'" in planner.dispatch_tool("update_routine", {"routine": "evening", "fields": {"name": "morning"}})
        assert planner.dispatch_tool("delete_routine", {"routine": "evening"}) == "Deleted routine Evening. This can't be undone."
        assert len(rows()) == 1

    def test_get_one_and_empty(self, planner):
        assert planner.dispatch_tool("get_routines", {}).startswith("No routines yet.")
        routine(planner)
        assert planner.dispatch_tool("get_routines", {"routine": "morn"}).splitlines()[1] == "  [ ] Drink water"
        assert "no routine matches" in planner.dispatch_tool("get_routines", {"routine": "zzz"})

    def test_hand_edited_rows_do_not_crash(self, planner):
        import storage
        storage.save_routines([{"id": "a", "name": "bad", "steps": "x", "log": 5, "days": "x"}, "junk",
                               {"id": "b", "name": "ok", "steps": [{"id": "s", "text": "a"}], "log": {"2026-10-13": "x"}}])
        out = planner.dispatch_tool("get_routines", {})
        assert out.startswith("2 routines:")
        assert isinstance(planner.dispatch_tool("get_today_agenda", {}), str)
