"""Time blocks: the day planner."""

from __future__ import annotations

from datetime import datetime

import pytest


def add(p, title="Deep work", start="09:30", end="11:00", **kw):
    out = p.dispatch_tool("add_time_block", {"title": title, "start": start, "end": end, **kw})
    assert out.startswith("Time block added on "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_timeblocks()


class TestParseTime:
    @pytest.mark.parametrize("text,minutes", [("9", 540), ("09:30", 570), ("9:05", 545), ("2pm", 840), ("2:30 PM", 870),
                                              ("12am", 0), ("12pm", 720), ("23:59", 1439), ("0:00", 0)])
    def test_good(self, planner, text, minutes):
        import timeblocks
        assert timeblocks.parse_time(text) == minutes

    @pytest.mark.parametrize("bad", ["", "  ", "25:00", "9:60", "13pm", "0pm", "noon", "9:5", None, 9, True, "24:00", "-1"])
    def test_bad(self, planner, bad):
        import timeblocks
        with pytest.raises(ValueError):
            timeblocks.parse_time(bad)

    def test_24_only_when_allowed(self, planner):
        import timeblocks
        assert timeblocks.parse_time("24:00", allow_24=True) == 1440
        with pytest.raises(ValueError):
            timeblocks.parse_time("24:30", allow_24=True)

    def test_formats(self, planner):
        import timeblocks
        assert [timeblocks.fmt_duration(m) for m in (5, 59, 60, 90, 125, 600)] == ["5min", "59min", "1h", "1h30", "2h05", "10h"]
        assert timeblocks.fmt_time(1440) == "24:00" and timeblocks.fmt_time(65) == "01:05"


class TestAdd:
    def test_shape_and_output(self, planner):
        out = planner.dispatch_tool("add_time_block", {"title": " Deep   work ", "start": "9:30", "end": "11am", "category": " Work "})
        assert out.startswith("Time block added on 2026-10-13: 09:30-11:00 Deep work [work] (1h30) [id=")
        r = rows()
        assert len(r) == 1 and r[0]["category"] == "work" and r[0]["done"] is False and r[0]["task_id"] is None
        assert set(r[0]) == {"id", "date", "start", "end", "title", "category", "task_id", "notes", "done"}

    def test_duration_instead_of_end(self, planner):
        add(planner, start="10:00", end=None, duration_minutes=45)
        assert rows()[0]["end"] == "10:45"

    def test_end_to_midnight(self, planner):
        add(planner, start="23:00", end="24:00")
        assert rows()[0]["end"] == "24:00"

    def test_default_category(self, planner):
        add(planner)
        assert rows()[0]["category"] == "general"

    @pytest.mark.parametrize("args,msg", [
        ({"title": "x", "start": "09:00"}, "give an end time or duration_minutes"),
        ({"title": "x", "start": "09:00", "end": "10:00", "duration_minutes": 30}, "either an end time or duration_minutes"),
        ({"title": "x", "start": "10:00", "end": "09:00"}, "end must be after the start"),
        ({"title": "x", "start": "10:00", "end": "10:00"}, "end must be after the start"),
        ({"title": "x", "start": "10:00", "end": "10:03"}, "lasts from 5 minutes"),
        ({"title": "x", "start": "10:00", "duration_minutes": 2}, "duration_minutes must be a whole number"),
        ({"title": "x", "start": "10:00", "duration_minutes": 30.5}, "duration_minutes must be a whole number"),
        ({"title": "x", "start": "10:00", "duration_minutes": True}, "duration_minutes must be a whole number"),
        ({"title": "x", "start": "23:00", "duration_minutes": 90}, "past midnight"),
        ({"title": "x", "start": "06:00", "end": "23:30"}, "lasts from 5 minutes"),
        ({"title": "", "start": "10:00", "end": "11:00"}, "needs a title"),
        ({"title": "t" * 81, "start": "10:00", "end": "11:00"}, "at most 80"),
        ({"title": "x", "start": "later", "end": "11:00"}, "start must be a time"),
        ({"title": "x", "start": "10:00", "end": "soon"}, "end must be a time"),
        ({"title": "x", "start": "10:00", "end": "11:00", "date": "never"}, "couldn't understand"),
        ({"title": "x", "start": "10:00", "end": "11:00", "date": "2030-01-01"}, "within 730 days"),
        ({"title": "x", "start": "10:00", "end": "11:00", "category": "c" * 21}, "at most 20"),
        ({"title": "x", "start": "10:00", "end": "11:00", "category": 5}, "category must be text"),
        ({"title": "x", "start": "10:00", "end": "11:00", "notes": 5}, "notes must be text"),
        ({"title": "x", "start": "10:00", "end": "11:00", "task": "nothing like it"}, "no open task matches"),
    ])
    def test_rejected_and_nothing_stored(self, planner, args, msg):
        out = planner.dispatch_tool("add_time_block", args)
        assert out.startswith("Time block not added: ") and msg in out, out
        assert rows() == []

    def test_overlap_rejected_edges_allowed(self, planner):
        add(planner, start="09:00", end="10:00")
        out = planner.dispatch_tool("add_time_block", {"title": "b", "start": "09:30", "end": "10:30"})
        assert "overlaps 'Deep work' (09:00-10:00) on 2026-10-13" in out
        assert "overlaps" in planner.dispatch_tool("add_time_block", {"title": "b", "start": "08:00", "end": "09:01"})
        assert "overlaps" in planner.dispatch_tool("add_time_block", {"title": "b", "start": "09:10", "end": "09:20"})
        add(planner, "before", "08:00", "09:00")   # touching is fine
        add(planner, "after", "10:00", "11:00")
        assert len(rows()) == 3

    def test_same_time_other_day_is_fine(self, planner):
        add(planner)
        add(planner, date="tomorrow")
        assert sorted(r["date"] for r in rows()) == ["2026-10-13", "2026-10-14"]

    def test_dates(self, planner):
        add(planner, date="friday")
        add(planner, "past", date="2026-10-10")
        assert sorted(r["date"] for r in rows()) == ["2026-10-10", "2026-10-16"]

    def test_task_link_and_default_title(self, planner):
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        out = planner.dispatch_tool("add_time_block", {"task": "report", "start": "13:00", "duration_minutes": 60})
        assert "Write the report [general] (1h), linked to a task" in out
        import storage
        assert rows()[0]["task_id"] == storage.load_tasks()[0]["id"]

    def test_done_task_cannot_be_linked(self, planner):
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        planner.dispatch_tool("complete_task", {"task": "report"})
        assert "no open task matches" in planner.dispatch_tool("add_time_block", {"task": "report", "start": "13:00", "duration_minutes": 60})

    def test_per_day_and_total_limits(self, planner, monkeypatch):
        import timeblocks
        monkeypatch.setattr(timeblocks, "MAX_PER_DAY", 2)
        add(planner, "a", "08:00", "08:30"); add(planner, "b", "09:00", "09:30")
        assert "already has 2 blocks" in planner.dispatch_tool("add_time_block", {"title": "c", "start": "10:00", "end": "10:30"})
        add(planner, "c", "10:00", "10:30", date="tomorrow")
        monkeypatch.setattr(timeblocks, "MAX_BLOCKS", 3)
        assert "already have 3 time blocks" in planner.dispatch_tool("add_time_block", {"title": "d", "start": "10:00", "end": "10:30", "date": "friday"})


class TestDayPlan:
    def test_empty_day(self, planner):
        assert planner.dispatch_tool("get_day_plan", {}) == (
            "Nothing planned for Tue 2026-10-13: 15h free between 07:00 and 22:00. Add a block with add_time_block.")

    def test_gaps_totals_and_next(self, planner):
        add(planner, "Deep work", "09:30", "11:00")
        add(planner, "Gym", "17:00", "18:00", category="health")
        out = planner.dispatch_tool("get_day_plan", {}).split("\n")
        assert out[0] == "Plan for Tue 2026-10-13: 2 blocks, 2h30 planned, 0min done, 12h30 free (07:00-22:00)."
        assert out[1] == "  free 07:00-09:30 (2h30)"
        assert out[2].startswith("- 09:30-11:00 Deep work [general] (1h30)")
        assert out[3] == "  free 11:00-17:00 (6h)"
        assert out[4].startswith("- 17:00-18:00 Gym [health] (1h)")
        assert out[5] == "  free 18:00-22:00 (4h)"
        assert out[6] == "Next: Deep work at 09:30, in 30min."

    def test_now_marker(self, planner):
        add(planner, "Deep work", "09:30", "11:00")
        planner.set_now(datetime(2026, 10, 13, 10, 0))
        assert planner.dispatch_tool("get_day_plan", {}).endswith("Now: Deep work until 11:00.")
        planner.set_now(datetime(2026, 10, 13, 12, 0))
        assert "Now:" not in planner.dispatch_tool("get_day_plan", {}) and "Next:" not in planner.dispatch_tool("get_day_plan", {})

    def test_no_markers_for_other_days(self, planner):
        add(planner, date="tomorrow")
        out = planner.dispatch_tool("get_day_plan", {"date": "tomorrow"})
        assert "Plan for Wed 2026-10-14" in out and "Next:" not in out and "Now:" not in out

    def test_short_gaps_hidden_but_blocks_outside_window_kept(self, planner):
        add(planner, "a", "07:00", "09:00"); add(planner, "b", "09:10", "21:50")
        add(planner, "early", "05:00", "06:00")
        out = planner.dispatch_tool("get_day_plan", {})
        assert "free 09:00" not in out and "free 21:50" not in out and "05:00-06:00 early" in out
        assert "0min free" in out

    def test_done_counts(self, planner):
        add(planner, "a", "09:00", "10:00")
        planner.dispatch_tool("finish_time_block", {"block": "a"})
        assert "1h planned, 1h done" in planner.dispatch_tool("get_day_plan", {})

    def test_bad_date(self, planner):
        assert planner.dispatch_tool("get_day_plan", {"date": "x"}).startswith("Cannot show the plan: ")

    def test_unreadable_rows_are_skipped(self, planner):
        import storage
        add(planner)
        storage.save_timeblocks(storage.load_timeblocks() + [
            {"id": "z1", "date": "2026-10-13", "start": "bad", "end": "10:00", "title": "x"}, "junk", None,
            {"id": "z2", "date": "2026-10-13", "start": "11:00", "end": "10:00", "title": "backwards"}])
        out = planner.dispatch_tool("get_day_plan", {})
        assert "1 block," in out and "backwards" not in out

    def test_not_a_list(self, planner):
        import storage
        storage.save_timeblocks({"oops": 1})
        assert planner.dispatch_tool("get_day_plan", {}).startswith("Nothing planned")


class TestUpdateDeleteFinish:
    def test_update_fields(self, planner):
        add(planner)
        out = planner.dispatch_tool("update_time_block", {"block": "deep", "fields": {
            "title": "Focus", "start": "10:00", "end": "11:30", "category": "Study", "notes": "n", "date": "tomorrow"}})
        assert out.startswith("Time block updated: 10:00-11:30 Focus [study] (1h30)")
        r = rows()[0]
        assert (r["date"], r["notes"]) == ("2026-10-14", "n")

    def test_update_overlap_rejected_and_unchanged(self, planner):
        add(planner, "a", "09:00", "10:00"); add(planner, "b", "11:00", "12:00")
        out = planner.dispatch_tool("update_time_block", {"block": "b", "fields": {"start": "09:30"}})
        assert "overlaps 'a'" in out
        assert [r["start"] for r in rows()] == ["09:00", "11:00"]

    def test_update_does_not_clash_with_itself(self, planner):
        add(planner, "a", "09:00", "10:00")
        assert planner.dispatch_tool("update_time_block", {"block": "a", "fields": {"end": "10:30"}}).startswith("Time block updated")

    def test_update_all_or_nothing(self, planner):
        add(planner)
        out = planner.dispatch_tool("update_time_block", {"block": "deep", "fields": {"title": "New", "end": "08:00"}})
        assert "end must be after the start" in out and rows()[0]["title"] == "Deep work"

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ("x", "nothing to change"),
                                            ({"color": "red"}, "cannot change color"), ({"done": "yes"}, "done must be true or false"),
                                            ({"title": ""}, "needs a title"), ({"date": "never"}, "couldn't understand")])
    def test_update_rejected(self, planner, fields, msg):
        add(planner)
        out = planner.dispatch_tool("update_time_block", {"block": "deep", "fields": fields})
        assert out.startswith("Time block not changed: ") and msg in out

    def test_only_done_ignores_existing_overlap(self, planner):
        import storage
        add(planner, "a", "09:00", "10:00")
        storage.save_timeblocks(storage.load_timeblocks() + [{"id": "q", "date": "2026-10-13", "start": "09:30", "end": "10:30", "title": "dup", "done": False}])
        assert planner.dispatch_tool("update_time_block", {"block": "q", "fields": {"done": True}}).startswith("Time block updated")

    def test_unreadable_block_needs_both_times(self, planner):
        import storage
        storage.save_timeblocks([{"id": "q", "date": "2026-10-13", "start": "x", "end": "y", "title": "broken"}])
        assert "no readable start and end" in planner.dispatch_tool("update_time_block", {"block": "q", "fields": {"start": "09:00"}})
        assert planner.dispatch_tool("update_time_block", {"block": "q", "fields": {"start": "09:00", "end": "10:00"}}).startswith("Time block updated")

    def test_delete(self, planner):
        add(planner)
        assert planner.dispatch_tool("delete_time_block", {"block": "deep"}) == "Deleted time block Deep work (2026-10-13 09:30). This can't be undone."
        assert rows() == []

    def test_ambiguous_title_needs_id_or_date(self, planner):
        add(planner, "Gym", "07:00", "08:00"); add(planner, "Gym", "07:00", "08:00", date="tomorrow")
        out = planner.dispatch_tool("delete_time_block", {"block": "gym"})
        assert "matches 2 blocks" in out and "2026-10-13 07:00 Gym" in out and len(rows()) == 2
        assert planner.dispatch_tool("delete_time_block", {"block": "gym", "date": "tomorrow"}).startswith("Deleted")
        assert [r["date"] for r in rows()] == ["2026-10-13"]

    def test_unknown_and_blank_refs(self, planner):
        assert "no time block matches 'zzz'" in planner.dispatch_tool("delete_time_block", {"block": "zzz"})
        assert "say which block" in planner.dispatch_tool("delete_time_block", {"block": ""})

    def test_finish_and_complete_task(self, planner):
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        add(planner, "Report time", "13:00", "14:00", task="report")
        out = planner.dispatch_tool("finish_time_block", {"block": "report time", "complete_task": True})
        assert out.startswith("Done: 13:00-14:00 Report time") and "Completed the linked task: Write the report" in out
        import storage
        assert storage.load_tasks()[0]["done"] is True
        assert planner.dispatch_tool("finish_time_block", {"block": "report time"}).startswith("Already done: ")

    def test_finish_without_completing_task(self, planner):
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        add(planner, "Report time", "13:00", "14:00", task="report")
        planner.dispatch_tool("finish_time_block", {"block": "report time"})
        import storage
        assert storage.load_tasks()[0]["done"] is False

    def test_finish_with_deleted_task(self, planner):
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        add(planner, "Report time", "13:00", "14:00", task="report")
        planner.dispatch_tool("delete_task", {"task": "report"})
        assert "The linked task no longer exists." in planner.dispatch_tool("finish_time_block", {"block": "report time", "complete_task": True})

    def test_finish_flag_must_be_boolean(self, planner):
        add(planner)
        assert "complete_task must be true or false" in planner.dispatch_tool("finish_time_block", {"block": "deep", "complete_task": "yes"})
        assert rows()[0]["done"] is False


class TestFreeTime:
    def test_slots_one_per_gap(self, planner):
        planner.set_now(datetime(2026, 10, 13, 6, 0))
        add(planner, "a", "09:00", "10:00")
        out = planner.dispatch_tool("find_free_time", {"duration_minutes": 60})
        assert out == ("2 free slots:\n- 2026-10-13 07:00-08:00 (the gap lasts until 09:00)\n"
                       "- 2026-10-13 10:00-11:00 (the gap lasts until 22:00)")

    def test_today_starts_at_the_current_time_rounded_up(self, planner):
        planner.set_now(datetime(2026, 10, 13, 9, 3))
        out = planner.dispatch_tool("find_free_time", {"duration_minutes": 30})
        assert "2026-10-13 09:05-09:35" in out

    def test_gap_must_fit(self, planner):
        planner.set_now(datetime(2026, 10, 13, 6, 0))
        add(planner, "a", "07:00", "09:00"); add(planner, "b", "09:30", "22:00")
        assert planner.dispatch_tool("find_free_time", {"duration_minutes": 45}) == "No free slot of that length in the search window."
        assert "09:00-09:30" in planner.dispatch_tool("find_free_time", {"duration_minutes": 30})

    def test_several_days_capped_at_five(self, planner):
        planner.set_now(datetime(2026, 10, 13, 6, 0))
        out = planner.dispatch_tool("find_free_time", {"duration_minutes": 60, "days": 14})
        assert out.startswith("5 free slots:") and out.count("\n- ") == 5
        assert "2026-10-17" in out

    def test_window_arguments(self, planner):
        planner.set_now(datetime(2026, 10, 13, 6, 0))
        out = planner.dispatch_tool("find_free_time", {"duration_minutes": 60, "earliest": "13:00", "latest": "15:00", "date": "tomorrow"})
        assert out == "1 free slot:\n- 2026-10-14 13:00-14:00 (the gap lasts until 15:00)"
        assert "shorter than the time you asked for" in planner.dispatch_tool("find_free_time", {"duration_minutes": 120, "earliest": "13:00", "latest": "14:00"})

    @pytest.mark.parametrize("args", [{}, {"duration_minutes": 0}, {"duration_minutes": "x"}, {"duration_minutes": 60, "days": 0},
                                      {"duration_minutes": 60, "days": 15}, {"duration_minutes": 60, "earliest": "late"}])
    def test_bad_arguments(self, planner, args):
        assert planner.dispatch_tool("find_free_time", args).startswith("Cannot search for free time: ")


class TestScheduleTask:
    def test_first_free_slot(self, planner):
        planner.set_now(datetime(2026, 10, 13, 6, 0))
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        add(planner, "a", "07:00", "09:00")
        out = planner.dispatch_tool("schedule_task", {"task": "report", "duration_minutes": 45})
        assert out.startswith("Scheduled on 2026-10-13: 09:00-09:45 Write the report [task] (45min), linked to a task")

    def test_moves_to_a_later_day_when_today_is_full(self, planner):
        planner.set_now(datetime(2026, 10, 13, 6, 0))
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        add(planner, "all day", "07:00", "22:00")
        assert "Scheduled on 2026-10-14: 07:00-08:00" in planner.dispatch_tool("schedule_task", {"task": "report"})

    def test_given_day_only(self, planner):
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        add(planner, "all day", "07:00", "22:00", date="friday")
        out = planner.dispatch_tool("schedule_task", {"task": "report", "date": "friday"})
        assert out.startswith("Task not scheduled: no free slot of 1h on 2026-10-16.")
        assert rows()[0]["title"] == "all day" and len(rows()) == 1

    def test_unknown_task(self, planner):
        assert planner.dispatch_tool("schedule_task", {"task": "nope"}).startswith("Task not scheduled: no open task matches")

    def test_custom_category(self, planner):
        planner.dispatch_tool("add_task", {"text": "Write the report"})
        planner.dispatch_tool("schedule_task", {"task": "report", "category": "work"})
        assert rows()[0]["category"] == "work"


class TestAllocation:
    def test_per_category(self, planner):
        add(planner, "a", "09:00", "11:00", category="work")
        add(planner, "b", "12:00", "13:00", category="work")
        add(planner, "c", "17:00", "18:00", category="health")
        planner.dispatch_tool("finish_time_block", {"block": "a"})
        add(planner, "old", "09:00", "10:00", category="work", date="2026-10-12")
        add(planner, "future", "09:00", "10:00", category="work", date="2026-10-14")
        add(planner, "ancient", "09:00", "10:00", category="work", date="2026-09-01")
        out = planner.dispatch_tool("get_time_allocation", {"days": 2}).split("\n")
        assert out[0] == "Time blocks, 2026-10-12 to 2026-10-13: 4 blocks, 5h planned, 2h done (40%)."
        assert out[1] == "- work: 4h planned (80% of the time), 2h done (50%), 3 block(s)"
        assert out[2] == "- health: 1h planned (20% of the time), 0min done (0%), 1 block(s)"

    def test_empty_and_bad(self, planner):
        assert planner.dispatch_tool("get_time_allocation", {}) == "No time blocks in the last 7 day(s)."
        assert planner.dispatch_tool("get_time_allocation", {"days": 0}).startswith("Cannot show the time allocation: ")
        assert planner.dispatch_tool("get_time_allocation", {"days": 91}).startswith("Cannot show the time allocation: ")


class TestNudgeAndAgenda:
    def test_nudge_window(self, planner):
        import timeblocks
        add(planner, "Standup", "09:10", "09:30")
        assert timeblocks.nudges() == ["Standup starts in 10 min (09:10)."]
        planner.set_now(datetime(2026, 10, 13, 8, 50))
        assert timeblocks.nudges() == []         # 20 minutes away
        planner.set_now(datetime(2026, 10, 13, 9, 10))
        assert timeblocks.nudges() == []         # already started
        planner.set_now(datetime(2026, 10, 13, 8, 55))
        assert timeblocks.nudges() == ["Standup starts in 15 min (09:10)."]

    def test_done_block_is_not_nudged(self, planner):
        import timeblocks
        add(planner, "Standup", "09:10", "09:30")
        planner.dispatch_tool("finish_time_block", {"block": "standup"})
        assert timeblocks.nudges() == []

    def test_agenda_section(self, planner):
        add(planner, "b", "13:00", "14:00"); add(planner, "a", "09:00", "10:00"); add(planner, "c", "15:00", "16:00")
        planner.dispatch_tool("finish_time_block", {"block": "c"})
        add(planner, "tomorrow", "09:00", "10:00", date="tomorrow")
        out = planner.dispatch_tool("get_today_agenda", {})
        assert "Time blocks:\n  09:00-10:00 a\n  13:00-14:00 b" in out and "tomorrow" not in out.split("Time blocks:")[1]
