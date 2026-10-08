"""Tests for demo/reminders.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def reminders(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "reminders"):
        if mod in sys.modules:
            del sys.modules[mod]
    import reminders as r
    importlib.reload(r)
    import storage
    storage.set_active_profile(None)
    return r


class TestCreateReminder:
    def test_create_reminder_basic(self, reminders):
        entry = reminders.create_reminder("stretch")
        assert entry["text"] == "stretch"
        assert entry["time"] is None
        assert entry["days"] == []
        assert "id" in entry
        assert "created" in entry

    def test_create_reminder_with_time_and_days(self, reminders):
        entry = reminders.create_reminder("stretch", "09:00", ["mon", "wed", "fri"])
        assert entry["time"] == "09:00"
        assert entry["days"] == ["mon", "wed", "fri"]

    def test_create_reminder_normalizes_day_case(self, reminders):
        entry = reminders.create_reminder("call mom", days=["Sun"])
        assert entry["days"] == ["sun"]

    def test_create_reminder_drops_invalid_days(self, reminders):
        entry = reminders.create_reminder("call mom", days=["sun", "notaday"])
        assert entry["days"] == ["sun"]

    def test_create_reminder_unique_ids(self, reminders):
        e1 = reminders.create_reminder("one")
        e2 = reminders.create_reminder("two")
        assert e1["id"] != e2["id"]

    def test_create_reminder_persists(self, reminders):
        reminders.create_reminder("stretch")
        from storage import load_reminders
        assert len(load_reminders()) == 1


class TestListReminders:
    def test_list_empty(self, reminders):
        assert reminders.list_reminders() == []

    def test_list_returns_created_order(self, reminders):
        reminders.create_reminder("first")
        reminders.create_reminder("second")
        result = reminders.list_reminders()
        assert [r["text"] for r in result] == ["first", "second"]


class TestDeleteReminder:
    def test_delete_existing(self, reminders):
        entry = reminders.create_reminder("stretch")
        assert reminders.delete_reminder(entry["id"]) is True
        assert reminders.list_reminders() == []

    def test_delete_nonexistent(self, reminders):
        assert reminders.delete_reminder("doesnotexist") is False

    def test_delete_only_removes_matching_id(self, reminders):
        e1 = reminders.create_reminder("one")
        reminders.create_reminder("two")
        reminders.delete_reminder(e1["id"])
        remaining = reminders.list_reminders()
        assert len(remaining) == 1
        assert remaining[0]["text"] == "two"


class TestFormatReminderList:
    def test_format_empty(self, reminders):
        assert reminders.format_reminder_list([]) == "No reminders set yet."

    def test_format_with_time_and_days(self, reminders):
        entry = reminders.create_reminder("stretch", "09:00", ["mon"])
        formatted = reminders.format_reminder_list([entry])
        assert "stretch" in formatted
        assert "09:00" in formatted
        assert "mon" in formatted

    def test_format_defaults_to_every_day_when_no_time_or_days(self, reminders):
        entry = reminders.create_reminder("stretch")
        formatted = reminders.format_reminder_list([entry])
        assert "every day" in formatted

    def test_format_includes_id(self, reminders):
        entry = reminders.create_reminder("stretch")
        formatted = reminders.format_reminder_list([entry])
        assert entry["id"] in formatted


def _at(y, m, d, hh, mm):
    from datetime import datetime
    return datetime(y, m, d, hh, mm)


# 2026-10-05 is a Monday
MON = (2026, 10, 5)
TUE = (2026, 10, 6)


class TestNormalizeTime:
    @pytest.mark.parametrize("raw,expected", [
        ("09:00", "09:00"), ("9:00", "09:00"), ("17:30", "17:30"), ("00:00", "00:00"),
        ("23:59", "23:59"), ("9am", "09:00"), ("9 AM", "09:00"), ("9:30pm", "21:30"),
        ("12am", "00:00"), ("12pm", "12:00"), ("12:15am", "00:15"), ("1pm", "13:00"),
        ("  7:05 ", "07:05"),
    ])
    def test_valid(self, reminders, raw, expected):
        assert reminders.normalize_time(raw) == expected

    @pytest.mark.parametrize("raw", [
        None, "", "   ", "9", "noon", "25:00", "24:00", "9:60", "13pm", "0am", "abc",
        "9:5", "9:00:00",
    ])
    def test_invalid(self, reminders, raw):
        assert reminders.normalize_time(raw) is None


class TestCreateReminderNormalization:
    def test_time_is_normalized(self, reminders):
        assert reminders.create_reminder("x", "9am")["time"] == "09:00"

    def test_unparseable_time_stored_as_given(self, reminders):
        assert reminders.create_reminder("x", "after lunch")["time"] == "after lunch"

    def test_blank_time_becomes_none(self, reminders):
        assert reminders.create_reminder("x", "   ")["time"] is None

    def test_duplicate_days_collapsed(self, reminders):
        assert reminders.create_reminder("x", days=["Mon", "monday", "tue"])["days"] == ["mon", "tue"]


class TestUpdateReminder:
    def test_update_text_only(self, reminders):
        e = reminders.create_reminder("old", "09:00", ["mon"])
        u = reminders.update_reminder(e["id"], text="  new  ")
        assert u["text"] == "new"
        assert u["time"] == "09:00"
        assert u["days"] == ["mon"]

    def test_update_time_normalizes(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        assert reminders.update_reminder(e["id"], time_str="6:30pm")["time"] == "18:30"

    def test_empty_time_clears(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        assert reminders.update_reminder(e["id"], time_str="")["time"] is None

    def test_update_days_and_empty_days_means_every_day(self, reminders):
        e = reminders.create_reminder("x", days=["mon"])
        assert reminders.update_reminder(e["id"], days=["Fri", "bogus"])["days"] == ["fri"]
        assert reminders.update_reminder(e["id"], days=[])["days"] == []

    def test_update_persists(self, reminders):
        e = reminders.create_reminder("x")
        reminders.update_reminder(e["id"], text="y")
        assert reminders.list_reminders()[0]["text"] == "y"

    def test_update_unknown_id_returns_none(self, reminders):
        assert reminders.update_reminder("nope", text="y") is None

    def test_blank_text_raises_and_changes_nothing(self, reminders):
        e = reminders.create_reminder("keep")
        with pytest.raises(ValueError):
            reminders.update_reminder(e["id"], text="   ")
        assert reminders.list_reminders()[0]["text"] == "keep"

    def test_update_only_touches_matching_reminder(self, reminders):
        a = reminders.create_reminder("a")
        reminders.create_reminder("b")
        reminders.update_reminder(a["id"], text="a2")
        assert [r["text"] for r in reminders.list_reminders()] == ["a2", "b"]


class TestPauseResume:
    def test_pause_sets_disabled(self, reminders):
        e = reminders.create_reminder("x")
        assert reminders.set_reminder_enabled(e["id"], False)["enabled"] is False
        assert reminders.is_enabled(reminders.list_reminders()[0]) is False

    def test_resume_removes_flag(self, reminders):
        e = reminders.create_reminder("x")
        reminders.set_reminder_enabled(e["id"], False)
        r = reminders.set_reminder_enabled(e["id"], True)
        assert "enabled" not in r
        assert reminders.is_enabled(r) is True

    def test_unknown_id_returns_none(self, reminders):
        assert reminders.set_reminder_enabled("nope", False) is None
        assert reminders.set_reminder_enabled("nope", True) is None

    def test_legacy_entry_without_flag_is_enabled(self, reminders):
        assert reminders.is_enabled({"id": "a", "text": "x"}) is True

    def test_paused_marked_in_list_format(self, reminders):
        e = reminders.create_reminder("x")
        reminders.set_reminder_enabled(e["id"], False)
        assert "[paused]" in reminders.format_reminder_list(reminders.list_reminders())

    def test_active_not_marked_paused(self, reminders):
        reminders.create_reminder("x")
        assert "[paused]" not in reminders.format_reminder_list(reminders.list_reminders())


class TestGetTodaysReminders:
    def test_empty(self, reminders):
        assert reminders.get_todays_reminders(_at(*MON, 9, 0)) == []

    def test_filters_by_weekday(self, reminders):
        reminders.create_reminder("monday only", "09:00", ["mon"])
        reminders.create_reminder("tuesday only", "09:00", ["tue"])
        reminders.create_reminder("daily", "10:00")
        texts = [r["text"] for r in reminders.get_todays_reminders(_at(*MON, 8, 0))]
        assert texts == ["monday only", "daily"]

    def test_sorted_by_time_with_untimed_last(self, reminders):
        reminders.create_reminder("note")
        reminders.create_reminder("evening", "18:00")
        reminders.create_reminder("morning", "7am")
        reminders.create_reminder("weird", "after lunch")
        texts = [r["text"] for r in reminders.get_todays_reminders(_at(*MON, 8, 0))]
        assert texts[:2] == ["morning", "evening"]
        assert set(texts[2:]) == {"note", "weird"}

    def test_paused_excluded(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.set_reminder_enabled(e["id"], False)
        assert reminders.get_todays_reminders(_at(*MON, 8, 0)) == []

    def test_format_empty(self, reminders):
        assert reminders.format_todays_reminders([]) == "No reminders for today."

    def test_format_lists_time_and_any_time(self, reminders):
        reminders.create_reminder("stretch", "9am")
        reminders.create_reminder("call mom")
        out = reminders.format_todays_reminders(reminders.get_todays_reminders(_at(*MON, 8, 0)))
        assert "- 09:00: stretch" in out
        assert "- any time: call mom" in out


class TestDueReminders:
    def test_due_at_exact_minute(self, reminders):
        reminders.create_reminder("stretch", "09:00")
        assert [r["text"] for r in reminders.due_reminders(_at(*MON, 9, 0))] == ["stretch"]

    def test_not_due_before(self, reminders):
        reminders.create_reminder("stretch", "09:00")
        assert reminders.due_reminders(_at(*MON, 8, 59)) == []

    def test_grace_window(self, reminders):
        reminders.create_reminder("stretch", "09:00")
        assert len(reminders.due_reminders(_at(*MON, 9, 2))) == 1
        assert reminders.due_reminders(_at(*MON, 9, 3)) == []

    def test_custom_grace(self, reminders):
        reminders.create_reminder("stretch", "09:00")
        assert reminders.due_reminders(_at(*MON, 9, 5), grace_minutes=5)
        assert not reminders.due_reminders(_at(*MON, 9, 5), grace_minutes=0)

    def test_does_not_wrap_past_midnight(self, reminders):
        reminders.create_reminder("late", "23:59")
        assert reminders.due_reminders(_at(*TUE, 0, 1)) == []

    def test_day_restriction(self, reminders):
        reminders.create_reminder("monday", "09:00", ["mon"])
        assert len(reminders.due_reminders(_at(*MON, 9, 0))) == 1
        assert reminders.due_reminders(_at(*TUE, 9, 0)) == []

    def test_paused_never_due(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.set_reminder_enabled(e["id"], False)
        assert reminders.due_reminders(_at(*MON, 9, 0)) == []

    def test_untimed_and_unparseable_never_due(self, reminders):
        reminders.create_reminder("untimed")
        reminders.create_reminder("odd", "after lunch")
        for hh in range(24):
            assert reminders.due_reminders(_at(*MON, hh, 0)) == []

    def test_am_pm_time_is_due(self, reminders):
        reminders.create_reminder("evening", "6pm")
        assert len(reminders.due_reminders(_at(*MON, 18, 0))) == 1

    def test_multiple_due_same_minute(self, reminders):
        reminders.create_reminder("a", "09:00")
        reminders.create_reminder("b", "09:00")
        assert len(reminders.due_reminders(_at(*MON, 9, 0))) == 2


class TestSchedulerSource:
    def test_empty_when_nothing_due(self, reminders):
        assert reminders.scheduler_source(_at(*MON, 9, 0)) == []

    def test_returns_key_title_message(self, reminders):
        e = reminders.create_reminder("stretch", "09:00")
        items = reminders.scheduler_source(_at(*MON, 9, 0))
        assert items == [(f"reminder:{e['id']}@09:00", "Hermes Life OS - Reminder", "stretch")]

    def test_key_changes_when_time_edited(self, reminders):
        e = reminders.create_reminder("stretch", "09:00")
        k1 = reminders.scheduler_source(_at(*MON, 9, 0))[0][0]
        reminders.update_reminder(e["id"], time_str="09:30")
        k2 = reminders.scheduler_source(_at(*MON, 9, 30))[0][0]
        assert k1 != k2


class TestSchedulerIntegration:
    """End to end: reminders.scheduler_source plugged into run_scheduler."""

    def test_reminder_delivered_once_per_day(self, reminders):
        from scheduler import run_scheduler
        reminders.create_reminder("stretch", "09:00")
        notified = []
        clock_times = iter([_at(*MON, 9, 0), _at(*MON, 9, 1), _at(*MON, 9, 2)])
        run_scheduler(
            schedule=[], runner=None,
            notifier=lambda t, m: notified.append((t, m)),
            max_iterations=3, clock=lambda: next(clock_times), sleeper=lambda s: None,
            dynamic_source=reminders.scheduler_source,
        )
        assert notified == [("Hermes Life OS - Reminder", "stretch")]

    def test_delivered_again_next_day(self, reminders):
        from scheduler import run_scheduler
        reminders.create_reminder("stretch", "09:00")
        notified = []
        clock_times = iter([_at(*MON, 9, 0), _at(*TUE, 9, 0)])
        run_scheduler(
            schedule=[], notifier=lambda t, m: notified.append(m),
            max_iterations=2, clock=lambda: next(clock_times), sleeper=lambda s: None,
            dynamic_source=reminders.scheduler_source,
        )
        assert notified == ["stretch", "stretch"]


# ---------------------------------------------------------------------------
# v1.38.0: dated one-offs, remind_me_in, snooze, clearing past reminders
# ---------------------------------------------------------------------------

def _id(entry):
    return entry["id"]


class TestNormalizeDate:
    @pytest.mark.parametrize("raw,expected", [
        ("2026-11-02", "2026-11-02"), (" 2026-11-02 ", "2026-11-02"),
        ("2026-1-5", "2026-01-05"), ("2028-02-29", "2028-02-29"),
    ])
    def test_valid(self, reminders, raw, expected):
        assert reminders.normalize_date(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_blank_means_no_date(self, reminders, raw):
        assert reminders.normalize_date(raw) is None

    @pytest.mark.parametrize("raw", [
        "2026-13-01", "2026-02-30", "2027-02-29", "11/02/2026", "tomorrow", "2026-11", "20261102", "2026-11-02T09:00",
    ])
    def test_invalid_raises(self, reminders, raw):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            reminders.normalize_date(raw)


class TestDatedReminders:
    def test_create_dated(self, reminders):
        e = reminders.create_reminder("renew passport", "9am", date="2026-11-02")
        assert e["date"] == "2026-11-02"
        assert e["time"] == "09:00"

    def test_date_overrides_days(self, reminders):
        e = reminders.create_reminder("x", "09:00", ["mon", "tue"], date="2026-11-02")
        assert e["days"] == []

    def test_no_date_key_when_not_dated(self, reminders):
        assert "date" not in reminders.create_reminder("x", "09:00")

    def test_invalid_date_raises_and_saves_nothing(self, reminders):
        with pytest.raises(ValueError):
            reminders.create_reminder("x", "09:00", date="2026-02-30")
        assert reminders.list_reminders() == []

    def test_blank_date_is_ignored(self, reminders):
        assert "date" not in reminders.create_reminder("x", "09:00", date="  ")

    def test_due_only_on_its_date(self, reminders):
        reminders.create_reminder("passport", "09:00", date="2026-10-05")
        assert len(reminders.due_reminders(_at(*MON, 9, 0))) == 1
        assert reminders.due_reminders(_at(*TUE, 9, 0)) == []
        assert reminders.due_reminders(_at(2026, 10, 4, 9, 0)) == []
        assert reminders.due_reminders(_at(2026, 11, 2, 9, 0)) == []

    def test_dated_without_time_never_fires_but_is_listed_that_day(self, reminders):
        reminders.create_reminder("birthday", date="2026-10-05")
        assert reminders.due_reminders(_at(*MON, 9, 0)) == []
        assert [r["text"] for r in reminders.get_todays_reminders(_at(*MON, 8, 0))] == ["birthday"]
        assert reminders.get_todays_reminders(_at(*TUE, 8, 0)) == []

    def test_todays_list_mixes_dated_and_recurring(self, reminders):
        reminders.create_reminder("daily", "10:00")
        reminders.create_reminder("one-off", "09:00", date="2026-10-05")
        reminders.create_reminder("other day", "09:30", date="2026-10-06")
        texts = [r["text"] for r in reminders.get_todays_reminders(_at(*MON, 8, 0))]
        assert texts == ["one-off", "daily"]

    def test_paused_dated_reminder_does_not_fire(self, reminders):
        e = reminders.create_reminder("x", "09:00", date="2026-10-05")
        reminders.set_reminder_enabled(_id(e), False)
        assert reminders.due_reminders(_at(*MON, 9, 0)) == []

    def test_key_includes_the_date(self, reminders):
        e = reminders.create_reminder("x", "09:00", date="2026-10-05")
        key = reminders.scheduler_source(_at(*MON, 9, 0))[0][0]
        assert key == f"reminder:{e['id']}@2026-10-05T09:00"


class TestUpdateReminderDate:
    def test_set_date_clears_days(self, reminders):
        e = reminders.create_reminder("x", "09:00", ["mon"])
        u = reminders.update_reminder(_id(e), date="2026-11-02")
        assert u["date"] == "2026-11-02" and u["days"] == []

    def test_empty_date_makes_it_recurring_again(self, reminders):
        e = reminders.create_reminder("x", "09:00", date="2026-11-02")
        u = reminders.update_reminder(_id(e), date="")
        assert "date" not in u

    def test_non_empty_days_make_a_one_off_recurring(self, reminders):
        e = reminders.create_reminder("x", "09:00", date="2026-11-02")
        u = reminders.update_reminder(_id(e), days=["fri"])
        assert "date" not in u and u["days"] == ["fri"]

    def test_empty_days_keeps_the_date(self, reminders):
        e = reminders.create_reminder("x", "09:00", date="2026-11-02")
        u = reminders.update_reminder(_id(e), days=[])
        assert u["date"] == "2026-11-02"

    def test_date_wins_over_days_in_the_same_call(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        u = reminders.update_reminder(_id(e), days=["mon"], date="2026-11-02")
        assert u["date"] == "2026-11-02" and u["days"] == []

    def test_invalid_date_changes_nothing_even_with_other_fields(self, reminders):
        e = reminders.create_reminder("keep", "09:00")
        with pytest.raises(ValueError):
            reminders.update_reminder(_id(e), text="changed", date="nope")
        assert reminders.list_reminders()[0]["text"] == "keep"

    def test_untouched_date_stays(self, reminders):
        e = reminders.create_reminder("x", "09:00", date="2026-11-02")
        assert reminders.update_reminder(_id(e), text="y")["date"] == "2026-11-02"


class TestRemindMeIn:
    def test_basic(self, reminders):
        e = reminders.remind_me_in("check the oven", 20, now=_at(*MON, 10, 0))
        assert (e["date"], e["time"], e["text"]) == ("2026-10-05", "10:20", "check the oven")

    def test_rounds_up_to_the_next_minute(self, reminders):
        from datetime import datetime
        e = reminders.remind_me_in("x", 1, now=datetime(2026, 10, 5, 10, 0, 30))
        assert e["time"] == "10:02"

    def test_exact_minute_not_rounded(self, reminders):
        assert reminders.remind_me_in("x", 5, now=_at(*MON, 10, 0))["time"] == "10:05"

    def test_crosses_midnight(self, reminders):
        e = reminders.remind_me_in("x", 30, now=_at(*MON, 23, 50))
        assert (e["date"], e["time"]) == ("2026-10-06", "00:20")

    def test_maximum_is_24_hours(self, reminders):
        e = reminders.remind_me_in("x", 1440, now=_at(*MON, 10, 0))
        assert (e["date"], e["time"]) == ("2026-10-06", "10:00")

    @pytest.mark.parametrize("bad", [0, -5, 1441, "abc", None, ""])
    def test_invalid_minutes(self, reminders, bad):
        with pytest.raises(ValueError):
            reminders.remind_me_in("x", bad, now=_at(*MON, 10, 0))
        assert reminders.list_reminders() == []

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank_text(self, reminders, bad):
        with pytest.raises(ValueError, match="what to be reminded"):
            reminders.remind_me_in(bad, 5)

    def test_numeric_string_minutes_accepted(self, reminders):
        assert reminders.remind_me_in("x", "15", now=_at(*MON, 10, 0))["time"] == "10:15"

    def test_text_is_trimmed(self, reminders):
        assert reminders.remind_me_in("  call  ", 5, now=_at(*MON, 10, 0))["text"] == "call"

    def test_fires_at_the_target_minute_only(self, reminders):
        reminders.remind_me_in("oven", 20, now=_at(*MON, 10, 0))
        assert reminders.due_reminders(_at(*MON, 10, 19)) == []
        assert len(reminders.due_reminders(_at(*MON, 10, 20))) == 1
        assert len(reminders.due_reminders(_at(*MON, 10, 22))) == 1
        assert reminders.due_reminders(_at(*MON, 10, 23)) == []

    def test_fires_after_midnight_on_the_new_date(self, reminders):
        reminders.remind_me_in("late", 30, now=_at(*MON, 23, 50))
        assert reminders.due_reminders(_at(*MON, 23, 59)) == []
        assert len(reminders.due_reminders(_at(*TUE, 0, 20))) == 1


class TestSnooze:
    def test_sets_snoozed_until(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        u = reminders.snooze_reminder(_id(e), 10, now=_at(*MON, 9, 0))
        assert u["snoozed_until"] == "2026-10-05T09:10"

    def test_default_is_ten_minutes(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        assert reminders.snooze_reminder(_id(e), now=_at(*MON, 9, 0))["snoozed_until"] == "2026-10-05T09:10"

    def test_rounds_up_to_the_next_minute(self, reminders):
        from datetime import datetime
        e = reminders.create_reminder("x", "09:00")
        u = reminders.snooze_reminder(_id(e), 5, now=datetime(2026, 10, 5, 9, 0, 20))
        assert u["snoozed_until"] == "2026-10-05T09:06"

    def test_persists(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.snooze_reminder(_id(e), 10, now=_at(*MON, 9, 0))
        assert reminders.list_reminders()[0]["snoozed_until"] == "2026-10-05T09:10"

    def test_unknown_id(self, reminders):
        assert reminders.snooze_reminder("nope", 10) is None

    @pytest.mark.parametrize("bad", [0, -1, 1441, "abc"])
    def test_invalid_minutes(self, reminders, bad):
        e = reminders.create_reminder("x", "09:00")
        with pytest.raises(ValueError):
            reminders.snooze_reminder(_id(e), bad)
        assert "snoozed_until" not in reminders.list_reminders()[0]

    def test_snoozed_reminder_fires_at_snooze_time(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.snooze_reminder(_id(e), 10, now=_at(*MON, 9, 0))
        assert reminders.due_reminders(_at(*MON, 9, 9)) == []
        assert len(reminders.due_reminders(_at(*MON, 9, 10))) == 1
        assert len(reminders.due_reminders(_at(*MON, 9, 12))) == 1
        assert reminders.due_reminders(_at(*MON, 9, 13)) == []

    def test_normal_time_is_suppressed_while_snoozed(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.snooze_reminder(_id(e), 5, now=_at(*MON, 8, 59))  # until 09:04
        assert reminders.due_reminders(_at(*MON, 9, 0)) == []
        assert reminders.due_reminders(_at(*MON, 9, 1)) == []
        assert len(reminders.due_reminders(_at(*MON, 9, 4))) == 1

    def test_untimed_reminder_can_be_snoozed_into_firing(self, reminders):
        e = reminders.create_reminder("note")
        reminders.snooze_reminder(_id(e), 30, now=_at(*MON, 9, 0))
        assert len(reminders.due_reminders(_at(*MON, 9, 30))) == 1

    def test_snooze_works_across_midnight(self, reminders):
        e = reminders.create_reminder("x", "23:50")
        reminders.snooze_reminder(_id(e), 30, now=_at(*MON, 23, 50))  # until 00:20 tomorrow
        assert len(reminders.due_reminders(_at(*TUE, 0, 20))) == 1

    def test_paused_snoozed_reminder_never_fires(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.snooze_reminder(_id(e), 10, now=_at(*MON, 9, 0))
        reminders.set_reminder_enabled(_id(e), False)
        assert reminders.due_reminders(_at(*MON, 9, 10)) == []

    def test_expired_snooze_does_not_block_the_next_days_normal_time(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.snooze_reminder(_id(e), 10, now=_at(*MON, 9, 0))
        assert len(reminders.due_reminders(_at(*TUE, 9, 0))) == 1

    def test_malformed_snoozed_until_is_ignored(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        stored = reminders.list_reminders()
        stored[0]["snoozed_until"] = "garbage"
        reminders.save_reminders(stored)
        assert len(reminders.due_reminders(_at(*MON, 9, 0))) == 1

    def test_scheduler_key_differs_for_snoozed_delivery(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        normal_key = reminders.scheduler_source(_at(*MON, 9, 0))[0][0]
        reminders.snooze_reminder(_id(e), 10, now=_at(*MON, 9, 1))  # until 09:11
        snooze_key = reminders.scheduler_source(_at(*MON, 9, 11))[0][0]
        assert normal_key == f"reminder:{e['id']}@09:00"
        assert snooze_key == f"reminder:{e['id']}@snooze:2026-10-05T09:11"

    def test_snoozed_reminder_is_delivered_twice_in_one_day_through_the_scheduler(self, reminders):
        from scheduler import run_scheduler
        e = reminders.create_reminder("stretch", "09:00")
        times = [_at(*MON, 9, 0), _at(*MON, 9, 1), _at(*MON, 9, 11)]
        index = {"i": 0}

        def clock():
            now = times[index["i"]]
            if index["i"] == 1:  # the user snoozes right after the first delivery
                reminders.snooze_reminder(e["id"], 10, now=now)
            index["i"] += 1
            return now

        notified = []
        run_scheduler(schedule=[], notifier=lambda t, m: notified.append(m),
                      max_iterations=3, clock=clock, sleeper=lambda s: None,
                      dynamic_source=reminders.scheduler_source)
        assert notified == ["stretch", "stretch"]

    def test_dated_reminder_delivered_once_through_the_scheduler(self, reminders):
        from scheduler import run_scheduler
        reminders.create_reminder("passport", "09:00", date="2026-10-05")
        notified = []
        times = iter([_at(*MON, 9, 0), _at(*MON, 9, 1), _at(*TUE, 9, 0)])
        run_scheduler(schedule=[], notifier=lambda t, m: notified.append(m),
                      max_iterations=3, clock=lambda: next(times), sleeper=lambda s: None,
                      dynamic_source=reminders.scheduler_source)
        assert notified == ["passport"]


class TestClearPastReminders:
    def test_removes_only_past_one_offs(self, reminders):
        reminders.create_reminder("past", "09:00", date="2026-10-04")
        reminders.create_reminder("today", "09:00", date="2026-10-05")
        reminders.create_reminder("future", "09:00", date="2026-10-06")
        reminders.create_reminder("recurring", "09:00")
        removed = reminders.clear_past_reminders(now=_at(*MON, 12, 0))
        assert removed == 1
        assert [r["text"] for r in reminders.list_reminders()] == ["today", "future", "recurring"]

    def test_nothing_to_clear(self, reminders):
        reminders.create_reminder("recurring", "09:00")
        assert reminders.clear_past_reminders(now=_at(*MON, 12, 0)) == 0
        assert len(reminders.list_reminders()) == 1

    def test_empty_store(self, reminders):
        assert reminders.clear_past_reminders() == 0

    def test_removes_paused_past_one_offs_too(self, reminders):
        e = reminders.create_reminder("past", date="2026-01-01")
        reminders.set_reminder_enabled(_id(e), False)
        assert reminders.clear_past_reminders(now=_at(*MON, 12, 0)) == 1

    def test_removes_several(self, reminders):
        for d in ("2026-01-01", "2026-02-01", "2026-03-01"):
            reminders.create_reminder("x", date=d)
        assert reminders.clear_past_reminders(now=_at(*MON, 12, 0)) == 3
        assert reminders.list_reminders() == []


class TestFormattingV138:
    def test_list_shows_date_and_time_instead_of_days(self, reminders):
        e = reminders.create_reminder("passport", "09:00", date="2026-11-02")
        out = reminders.format_reminder_list([e], now=_at(*MON, 8, 0))
        assert "(2026-11-02, 09:00)" in out
        assert "[past]" not in out

    def test_list_marks_past_one_offs(self, reminders):
        e = reminders.create_reminder("old", "09:00", date="2026-10-01")
        assert "[past]" in reminders.format_reminder_list([e], now=_at(*MON, 8, 0))

    def test_one_off_dated_today_is_not_past(self, reminders):
        e = reminders.create_reminder("today", "09:00", date="2026-10-05")
        assert "[past]" not in reminders.format_reminder_list([e], now=_at(*MON, 23, 0))

    def test_list_marks_active_snooze(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        e = reminders.snooze_reminder(_id(e), 30, now=_at(*MON, 9, 0))
        out = reminders.format_reminder_list([e], now=_at(*MON, 9, 5))
        assert "[snoozed until 2026-10-05 09:30]" in out

    def test_list_does_not_mark_expired_snooze(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        e = reminders.snooze_reminder(_id(e), 10, now=_at(*MON, 9, 0))
        assert "snoozed" not in reminders.format_reminder_list([e], now=_at(*MON, 10, 0))

    def test_paused_and_snoozed_both_shown(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.snooze_reminder(_id(e), 30, now=_at(*MON, 9, 0))
        reminders.set_reminder_enabled(_id(e), False)
        out = reminders.format_reminder_list(reminders.list_reminders(), now=_at(*MON, 9, 5))
        assert "[snoozed until" in out and "[paused]" in out

    def test_todays_list_shows_snooze(self, reminders):
        e = reminders.create_reminder("x", "09:00")
        reminders.snooze_reminder(_id(e), 30, now=_at(*MON, 9, 0))
        out = reminders.format_todays_reminders(reminders.get_todays_reminders(_at(*MON, 9, 5)), now=_at(*MON, 9, 5))
        assert "[snoozed until 09:30]" in out

    def test_recurring_label_unchanged(self, reminders):
        e = reminders.create_reminder("x", "09:00", ["mon", "wed"])
        assert "(09:00, mon/wed)" in reminders.format_reminder_list([e])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
