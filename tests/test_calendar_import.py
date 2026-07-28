"""Tests for demo/calendar_import.py - .ics calendar import for meeting-load correlation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def calendar_import(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "calendar_import"):
        if mod in sys.modules:
            del sys.modules[mod]
    import calendar_import as ci
    importlib.reload(ci)
    return ci


ICS_CONTENT = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:1@test
DTSTART:20260110T090000Z
DTEND:20260110T100000Z
SUMMARY:Standup
END:VEVENT
BEGIN:VEVENT
UID:2@test
DTSTART:20260110T140000Z
DTEND:20260110T153000Z
SUMMARY:Planning
 with a folded continuation line
END:VEVENT
BEGIN:VEVENT
UID:3@test
DTSTART;VALUE=DATE:20260111
DTEND;VALUE=DATE:20260112
SUMMARY:All day event
END:VEVENT
BEGIN:VEVENT
UID:4@test
DTSTART:20260111T100000Z
DTEND:20260111T110000Z
SUMMARY:1-on-1
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture()
def ics_file(tmp_path):
    p = tmp_path / "calendar.ics"
    p.write_text(ICS_CONTENT, encoding="utf-8")
    return str(p)


class TestParseIcsMeetingHours:
    def test_sums_multiple_events_same_day(self, calendar_import, ics_file):
        result = calendar_import.parse_ics_meeting_hours(ics_file)
        assert result["2026-01-10"] == pytest.approx(2.5, abs=0.01)  # 1h + 1.5h

    def test_skips_all_day_events(self, calendar_import, ics_file):
        result = calendar_import.parse_ics_meeting_hours(ics_file)
        assert result["2026-01-11"] == pytest.approx(1.0, abs=0.01)  # only the timed 1-on-1

    def test_handles_folded_lines(self, calendar_import, ics_file):
        # if folding weren't handled, the Planning event's DTEND line
        # would be corrupted and this event would be dropped/miscounted
        result = calendar_import.parse_ics_meeting_hours(ics_file)
        assert result["2026-01-10"] == pytest.approx(2.5, abs=0.01)

    def test_empty_file_no_events(self, calendar_import, tmp_path):
        p = tmp_path / "empty.ics"
        p.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")
        assert calendar_import.parse_ics_meeting_hours(str(p)) == {}

    def test_malformed_event_missing_dtend_ignored(self, calendar_import, tmp_path):
        p = tmp_path / "bad.ics"
        p.write_text(
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260101T090000Z\nEND:VEVENT\nEND:VCALENDAR\n",
            encoding="utf-8",
        )
        assert calendar_import.parse_ics_meeting_hours(str(p)) == {}


class TestImportIcs:
    def test_creates_expected_entry_count(self, calendar_import, ics_file):
        count = calendar_import.import_ics(ics_file)
        assert count == 2  # 2 distinct days

    def test_entries_tagged_as_import_and_calendar_type(self, calendar_import, ics_file):
        calendar_import.import_ics(ics_file)
        entries = calendar_import.storage.get_recent_memory(days=3650)
        assert all(e["type"] == "calendar" for e in entries)
        assert all(e["source"] == "import" for e in entries)

    def test_dry_run_writes_nothing(self, calendar_import, ics_file):
        count = calendar_import.import_ics(ics_file, dry_run=True)
        assert count == 2
        assert calendar_import.storage.memory_count() == 0

    def test_meeting_hours_feed_into_correlation_metrics(self, calendar_import, ics_file):
        """meeting_hours must be picked up by analytics.py's metric
        extraction, since that's the whole point of this feature."""
        import analytics
        calendar_import.import_ics(ics_file)
        entries = calendar_import.storage.get_recent_memory(days=3650)
        daily = analytics.daily_averages(entries)
        assert daily["2026-01-10"]["meeting_hours"] == pytest.approx(2.5, abs=0.01)


class TestMainCli:
    def test_missing_file_exits_cleanly(self, calendar_import, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["calendar_import.py", "--ics", str(tmp_path / "nope.ics")]
            calendar_import.main()
        assert exc_info.value.code == 1

    def test_successful_import_via_cli(self, calendar_import, ics_file, capsys):
        sys.argv = ["calendar_import.py", "--ics", ics_file]
        calendar_import.main()
        captured = capsys.readouterr()
        assert "Imported 2 days" in captured.out

    def test_profile_flag_isolates_import(self, calendar_import, ics_file):
        sys.argv = ["calendar_import.py", "--ics", ics_file, "--profile", "alex"]
        calendar_import.main()
        assert calendar_import.storage.ACTIVE_PROFILE == "alex"
        assert calendar_import.storage.memory_count() == 2

        calendar_import.storage.set_active_profile(None)
        assert calendar_import.storage.memory_count() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
