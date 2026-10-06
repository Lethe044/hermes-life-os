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
