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
