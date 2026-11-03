"""ICS calendar export."""

from __future__ import annotations

import calendar_export as cx


def read(path):
    return open(path, "rb").read().decode("utf-8")


def seed(d):
    d("add_task", {"text": "Pay rent, now; ASAP", "due": "tomorrow", "priority": "high"})
    d("add_time_block", {"title": "Deep work", "start": "10:00", "end": "11:30"})
    d("add_person", {"name": "Ayse", "birthday": "1990-10-20"})
    d("add_countdown", {"name": "Launch", "date": "2026-12-01"})
    d("add_trip", {"name": "Rome", "start": "2026-11-05", "end": "2026-11-09", "destination": "Italy"})
    d("add_expiry", {"name": "Milk", "date": "2026-10-16"})


def test_escape_and_fold():
    assert cx.escape("a,b;c\\d\ne") == r"a\,b\;c\\d\ne"
    long = "SUMMARY:" + "é" * 100
    folded = cx.fold(long)
    for line in folded.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    assert folded.replace("\r\n ", "") == long
    assert cx.fold("short") == "short"


def test_export_file_content(planner):
    d = planner.dispatch_tool
    seed(d)
    out = d("export_calendar", {})
    assert out.startswith("Exported ") and ".ics" in out
    import storage
    files = list((storage.HERMES_DIR / "exports").glob("calendar-*.ics"))
    assert len(files) == 1
    text = read(files[0])
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert text.count("BEGIN:VEVENT") == text.count("END:VEVENT") == 6
    assert "DTSTART:20261013T100000" in text and "DTEND:20261013T113000" in text
    assert r"SUMMARY:! Task: Pay rent\, now\; ASAP" in text and "DTSTART;VALUE=DATE:20261014" in text
    assert "RRULE:FREQ=YEARLY" in text and "DTSTART;VALUE=DATE:20261020" in text
    assert "DTSTART;VALUE=DATE:20261105" in text and "DTEND;VALUE=DATE:20261110" in text
    assert "DTSTAMP:20261013T090000" in text and "SUMMARY:Expires: Milk" in text and "SUMMARY:Launch" in text


def test_uids_are_stable_between_exports(planner):
    d = planner.dispatch_tool
    seed(d)
    a = cx.build()["text"]
    b = cx.build()["text"]
    assert a == b
    uids = [l for l in a.split("\r\n") if l.startswith("UID:")]
    assert len(uids) == len(set(uids)) and all(u.endswith("@hermes-life-os") for u in uids)


def test_sections_and_days(planner):
    d = planner.dispatch_tool
    seed(d)
    r = cx.build(sections=["tasks"])
    assert r["counts"] == {"tasks": 1} and r["total"] == 1
    assert cx.build(days=3, sections=["trips", "countdowns"])["total"] == 0
    assert "tasks: 1" in d("export_calendar", {"sections": ["tasks"]})


def test_empty_and_validation(planner):
    d = planner.dispatch_tool
    assert d("export_calendar", {}).startswith("The calendar file is empty")
    assert "unknown section" in d("export_calendar", {"sections": ["bogus"]})
    assert "days must be" in d("export_calendar", {"days": 0})
    assert d("export_calendar", {"sections": "tasks"}).startswith("Calendar not exported:")


def test_unreadable_rows_do_not_break_the_export(planner):
    import storage
    storage.save_timeblocks([{"id": "x", "date": "garbage", "start": "10:00", "end": "11:00"}, "junk",
                             {"id": "y", "date": "2026-10-13", "start": "11:00", "end": "10:00"}])
    storage.save_tasks([{"id": "t", "text": "x", "due": "nope"}, 7])
    assert cx.build()["total"] == 0


def test_done_tasks_and_blocks_marked(planner):
    d = planner.dispatch_tool
    d("add_task", {"text": "Finished", "due": "tomorrow"})
    d("complete_task", {"task": "Finished"})
    assert cx.build(sections=["tasks"])["total"] == 0
