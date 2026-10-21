"""Symptoms: logging, validation, summary statistics, entry-tool integration."""

from __future__ import annotations

import pytest


def log(p, symptom="headache", severity=5, **kw):
    out = p.dispatch_tool("log_symptom", {"symptom": symptom, "severity": severity, **kw})
    assert out.startswith("Logged: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_symptoms()


def summary(p, **kw):
    return p.dispatch_tool("get_symptom_summary", kw)


class TestLog:
    def test_minimal(self, planner):
        sid = log(planner)
        assert rows() == [{"id": sid, "date": "2026-10-13", "symptom": "headache", "severity": 5,
                           "duration_minutes": None, "triggers": [], "time": None}]

    def test_full(self, planner):
        out = planner.dispatch_tool("log_symptom", {
            "symptom": "  Migraine ", "severity": 8, "duration_minutes": 120, "triggers": ["Stress", "coffee", "stress"],
            "time": "7:05", "notes": "left side", "date": "2026-10-10"})
        assert out.startswith("Logged: Migraine 8/10, 120 min (triggers: stress, coffee) on 2026-10-10 [id=")
        r = rows()[0]
        assert (r["symptom"], r["time"], r["notes"], r["triggers"]) == ("migraine", "07:05", "left side", ["stress", "coffee"])

    def test_triggers_as_a_string(self, planner):
        log(planner, triggers="stress; coffee, bad sleep")
        assert rows()[0]["triggers"] == ["stress", "coffee", "bad sleep"]

    def test_float_severity_that_is_whole(self, planner):
        log(planner, severity=6.0)
        assert rows()[0]["severity"] == 6

    def test_notes_are_capped(self, planner):
        log(planner, notes="n" * 500)
        assert len(rows()[0]["notes"]) == 300

    @pytest.mark.parametrize("sev", [0, 11, -1, 5.5, "bad", None, True, [5]])
    def test_bad_severity(self, planner, sev):
        out = planner.dispatch_tool("log_symptom", {"symptom": "x", "severity": sev})
        assert out == "Not logged: severity must be a whole number from 1 to 10." and rows() == []

    @pytest.mark.parametrize("name", ["", "  ", None, 5, "x" * 41])
    def test_bad_names(self, planner, name):
        assert planner.dispatch_tool("log_symptom", {"symptom": name, "severity": 3}).startswith("Not logged: ")
        assert rows() == []

    @pytest.mark.parametrize("dur", [0, -5, 1.5, "long", True, 10081])
    def test_bad_durations(self, planner, dur):
        assert "duration_minutes" in planner.dispatch_tool("log_symptom", {"symptom": "x", "severity": 3, "duration_minutes": dur})
        assert rows() == []

    @pytest.mark.parametrize("dur,stored", [(None, None), ("", None), ("30", 30), (45.0, 45)])
    def test_durations(self, planner, dur, stored):
        log(planner, duration_minutes=dur)
        assert rows()[0]["duration_minutes"] == stored

    @pytest.mark.parametrize("trig", [5, [1], ["x" * 31], [f"t{i}" for i in range(9)]])
    def test_bad_triggers(self, planner, trig):
        assert planner.dispatch_tool("log_symptom", {"symptom": "x", "severity": 3, "triggers": trig}).startswith("Not logged: ")
        assert rows() == []

    @pytest.mark.parametrize("t", ["25:00", "12:60", "noon", "1230", 5, "12:3x"])
    def test_bad_times(self, planner, t):
        assert "HH:MM" in planner.dispatch_tool("log_symptom", {"symptom": "x", "severity": 3, "time": t})
        assert rows() == []

    def test_blank_time_is_none(self, planner):
        log(planner, time=" ")
        assert rows()[0]["time"] is None

    def test_backdating(self, planner):
        log(planner, date="2026-10-01")
        assert rows()[0]["date"] == "2026-10-01"

    @pytest.mark.parametrize("date,msg", [("2026-10-14", "in the future"), ("soon", "not a valid date")])
    def test_bad_dates(self, planner, date, msg):
        out = planner.dispatch_tool("log_symptom", {"symptom": "x", "severity": 3, "date": date})
        assert msg in out and rows() == []

    def test_journal_entry_is_linked(self, planner):
        import storage
        sid = log(planner, "headache", 6, duration_minutes=30)
        m = storage.get_all_memory()[-1]
        assert m["type"] == "symptom" and m["log_id"] == sid and m["content"] == "Headache 6/10, 30 min"
        assert m["severity"] == 6

    def test_confirmation_mentions_the_running_count(self, planner):
        log(planner)
        assert "entries in the last 30 days" not in planner.dispatch_tool("log_symptom", {"symptom": "back pain", "severity": 2})
        out = planner.dispatch_tool("log_symptom", {"symptom": "headache", "severity": 7})
        assert "2 headache entries in the last 30 days, average severity 6/10." in out

    def test_limit(self, planner):
        import storage
        storage.save_symptoms([{"id": str(i), "date": "2026-10-01", "symptom": "x", "severity": 1} for i in range(20000)])
        assert "already holds 20000" in planner.dispatch_tool("log_symptom", {"symptom": "x", "severity": 1})


class TestSummary:
    def test_empty(self, planner):
        assert summary(planner) == "No symptoms logged in the last 30 days."
        assert summary(planner, symptom="Cough", days=7) == "No 'cough' symptoms logged in the last 7 days."

    def test_basic_statistics(self, planner):
        for day, sev in (("2026-10-02", 4), ("2026-10-08", 6), ("2026-10-13", 8)):
            log(planner, severity=sev, date=day, duration_minutes=60)
        out = summary(planner)
        assert "- Headache: 3 entries on 3 day(s), average severity 6/10 (worst 8), 0.7 per week, about 60 min each." in out
        assert "last one today (2026-10-13)" in out

    def test_per_week_uses_the_window(self, planner):
        for day in ("2026-10-07", "2026-10-10"):
            log(planner, date=day)
        assert "0.5 per week" in summary(planner, days=28) and "2 per week" in summary(planner, days=7)

    def test_one_entry_wording_and_days_since(self, planner):
        log(planner, date="2026-10-10")
        out = summary(planner)
        assert "1 entry on 1 day(s)" in out and "last one 3 day(s) ago (2026-10-10)" in out

    def test_two_entries_on_one_day(self, planner):
        log(planner)
        log(planner, severity=7)
        assert "2 entries on 1 day(s)" in summary(planner)

    def test_window_excludes_older_entries_but_days_since_does_not(self, planner):
        log(planner, date="2026-08-01")
        assert summary(planner, days=30) == "No symptoms logged in the last 30 days."
        log(planner, date="2026-10-10")
        assert "last one 3 day(s) ago" in summary(planner, days=30)

    def test_the_window_boundary_is_inclusive(self, planner):
        log(planner, date="2026-10-07")  # 6 days before today: the first day of a 7-day window
        log(planner, date="2026-10-06")
        assert "1 entry" in summary(planner, days=7)

    def test_triggers_ranked(self, planner):
        log(planner, triggers=["stress", "coffee"])
        log(planner, triggers=["stress"], date="2026-10-12")
        log(planner, triggers=["stress", "coffee", "noise", "heat"], date="2026-10-11")
        assert "Common triggers: stress (3x), coffee (2x)," in summary(planner)

    def test_no_triggers_line_without_triggers(self, planner):
        log(planner)
        assert "Common triggers" not in summary(planner)

    def test_symptoms_are_listed_most_frequent_first(self, planner):
        log(planner, "cough")
        log(planner, "headache", date="2026-10-10")
        log(planner, "headache", date="2026-10-11")
        out = summary(planner)
        assert out.index("Headache") < out.index("Cough")

    def test_one_symptom_only(self, planner):
        log(planner, "cough")
        log(planner, "headache")
        out = summary(planner, symptom="  COUGH ")
        assert "Cough" in out and "Headache" not in out

    def test_worst_weekday(self, planner):
        # 2026-10-05, 10-12 are Mondays; 10-07 Wednesday; 10-09 Friday; 10-10 Saturday
        for day in ("2026-10-05", "2026-10-12", "2026-10-07", "2026-10-09", "2026-10-10"):
            log(planner, date=day)
        assert "most often on Mondays" in summary(planner)

    def test_a_tie_for_worst_weekday_is_not_reported(self, planner):
        for day in ("2026-10-05", "2026-10-12", "2026-10-07", "2026-10-14".replace("14", "07"), "2026-10-09"):
            log(planner, date=day)
        assert "most often on" not in summary(planner)

    def test_worst_weekday_needs_five_entries(self, planner):
        for day in ("2026-10-05", "2026-10-12", "2026-10-07"):
            log(planner, date=day)
        assert "most often on" not in summary(planner)

    def test_trend_more_frequent(self, planner):
        log(planner, date="2026-09-20")
        for day in ("2026-10-05", "2026-10-08", "2026-10-11", "2026-10-13"):
            log(planner, date=day)
        assert "more frequent than in the first half" in summary(planner)

    def test_trend_less_frequent(self, planner):
        for day in ("2026-09-18", "2026-09-20", "2026-09-22", "2026-09-25"):
            log(planner, date=day)
        log(planner, date="2026-10-12")
        assert "less frequent than in the first half" in summary(planner)

    def test_trend_about_the_same(self, planner):
        for day in ("2026-09-18", "2026-09-25", "2026-10-06", "2026-10-12"):
            log(planner, date=day)
        assert "about the same than in the first half" in summary(planner)

    def test_no_trend_without_a_baseline(self, planner):
        for day in ("2026-10-05", "2026-10-08", "2026-10-11", "2026-10-13"):
            log(planner, date=day)
        assert "first half" not in summary(planner)

    def test_no_trend_in_a_short_window_or_with_few_entries(self, planner):
        for day in ("2026-10-06", "2026-10-08", "2026-10-11", "2026-10-13"):
            log(planner, date=day)
        assert "first half" not in summary(planner, days=7)
        planner.dispatch_tool("delete_log", {"tracker": "symptoms", "log_id": rows()[0]["id"]})
        planner.dispatch_tool("delete_log", {"tracker": "symptoms", "log_id": rows()[0]["id"]})
        assert "first half" not in summary(planner)

    def test_severe_entries_add_a_pointer_to_a_doctor(self, planner):
        log(planner, severity=9)
        assert "worth mentioning to a doctor" in summary(planner)
        assert "worth mentioning to a doctor" in summary(planner, symptom="headache")

    def test_mild_entries_do_not(self, planner):
        log(planner, severity=8)
        assert "doctor" not in summary(planner)

    def test_it_says_it_is_not_medical_advice(self, planner):
        log(planner)
        assert "not medical advice" in summary(planner)

    @pytest.mark.parametrize("days", ["many", 0, 366, -1, None])
    def test_bad_days(self, planner, days):
        assert summary(planner, days=days).startswith("Cannot summarize symptoms: ")


class TestSleepLink:
    def sleep(self, planner, day, hours):
        planner.dispatch_tool("log_sleep", {"hours": hours, "quality": 5, "date": day})

    def test_comparison_when_there_is_enough_data(self, planner):
        for day in ("2026-10-02", "2026-10-04", "2026-10-06"):
            self.sleep(planner, day, 5)
            log(planner, date=day)
        for day in ("2026-10-03", "2026-10-05", "2026-10-07"):
            self.sleep(planner, day, 8)
        assert "Average logged sleep: 5h on symptom days vs 8h on other days" in summary(planner)

    def test_not_shown_with_too_little_data(self, planner):
        for day in ("2026-10-02", "2026-10-04"):
            self.sleep(planner, day, 5)
            log(planner, date=day)
        for day in ("2026-10-03", "2026-10-05", "2026-10-07"):
            self.sleep(planner, day, 8)
        assert "Average logged sleep" not in summary(planner)

    def test_not_shown_without_sleep_data(self, planner):
        for day in ("2026-10-02", "2026-10-04", "2026-10-06"):
            log(planner, date=day)
        assert "Average logged sleep" not in summary(planner)

    def test_garbage_sleep_rows_are_ignored(self, planner):
        import storage
        storage.save_sleep(["x", None, {"date": 5, "hours": 1}, {"date": "2026-10-01", "hours": "lots"}])
        log(planner)
        assert "Average logged sleep" not in summary(planner)


class TestEntryTools:
    def test_list_logs(self, planner):
        log(planner, "headache", 6, duration_minutes=30)
        out = planner.dispatch_tool("list_logs", {"tracker": "symptoms"})
        assert "Headache 6/10, 30 min" in out

    def test_edit_log(self, planner):
        sid = log(planner, "headache", 6)
        out = planner.dispatch_tool("edit_log", {"tracker": "symptoms", "log_id": sid, "fields": {
            "severity": 3, "duration_minutes": 20, "triggers": "noise, heat", "notes": "better", "symptom": "Migraine"}})
        r = rows()[0]
        assert (r["severity"], r["duration_minutes"], r["triggers"], r["notes"], r["symptom"]) == (
            3, 20, ["noise", "heat"], "better", "migraine"), out

    def test_edit_keeps_the_journal_in_sync(self, planner):
        import storage
        sid = log(planner, "headache", 6)
        planner.dispatch_tool("edit_log", {"tracker": "symptoms", "log_id": sid, "fields": {"severity": 2}})
        assert storage.get_all_memory()[-1]["content"] == "Headache 2/10"

    @pytest.mark.parametrize("fields", [{"severity": 11}, {"severity": 0}, {"duration_minutes": 0}, {"bogus": 1}])
    def test_invalid_edits_change_nothing(self, planner, fields):
        sid = log(planner, "headache", 6)
        before = rows()
        planner.dispatch_tool("edit_log", {"tracker": "symptoms", "log_id": sid, "fields": fields})
        assert rows() == before

    def test_delete_log_removes_the_journal_entry_too(self, planner):
        import storage
        sid = log(planner)
        planner.dispatch_tool("delete_log", {"tracker": "symptoms", "log_id": sid})
        assert rows() == [] and storage.get_all_memory() == []

    def test_undo_last_log(self, planner):
        log(planner)
        out = planner.dispatch_tool("undo_last_log", {"tracker": "symptoms"})
        assert rows() == [] and "Headache" in out

    def test_get_day_log_and_search(self, planner):
        log(planner, "back pain", 4, date="2026-10-12")
        assert "Back pain 4/10" in planner.dispatch_tool("get_day_log", {"date": "2026-10-12"})
        assert "Back pain" in planner.dispatch_tool("search_logs", {"query": "back pain"})

    def test_logging_gaps_knows_the_tracker(self, planner):
        log(planner, date="2026-10-12")
        out = planner.dispatch_tool("get_logging_gaps", {"tracker": "symptoms", "days": 3})
        assert out == ("symptoms: nothing logged on 2 of the last 3 complete days: 2026-10-10, 2026-10-11. "
                       "Add them with the log tool's date argument.")

    def test_log_many(self, planner):
        out = planner.dispatch_tool("log_many", {"entries": [
            {"tool": "log_symptom", "args": {"symptom": "headache", "severity": 4, "date": "2026-10-10"}},
            {"tool": "log_symptom", "args": {"symptom": "cough", "severity": 2}}]})
        assert len(rows()) == 2 and {r["date"] for r in rows()} == {"2026-10-10", "2026-10-13"}, out

    def test_log_many_reports_the_bad_entry_and_keeps_the_good_one(self, planner):
        out = planner.dispatch_tool("log_many", {"entries": [
            {"tool": "log_symptom", "args": {"symptom": "headache", "severity": 4}},
            {"tool": "log_symptom", "args": {"symptom": "cough", "severity": 99}}]})
        assert out.startswith("Logged 1 of 2 entries.") and "2. log_symptom: Not logged: severity" in out
        assert [r["symptom"] for r in rows()] == ["headache"]

    def test_log_many_rejects_a_bad_date_for_the_whole_batch(self, planner):
        out = planner.dispatch_tool("log_many", {"entries": [
            {"tool": "log_symptom", "args": {"symptom": "headache", "severity": 4}},
            {"tool": "log_symptom", "args": {"symptom": "cough", "severity": 2, "date": "2099-01-01"}}]})
        assert out.startswith("Nothing logged: entry 2") and rows() == []

    def test_tracker_names_are_consistent(self, planner):
        import entries
        assert "symptoms" in entries.tracker_names() and "symptoms" in planner._TRACKER_NAMES
        assert planner._TRACKER_NAMES == entries.tracker_names()


class TestRobustness:
    def test_handwritten_rows(self, planner):
        import storage
        storage.save_symptoms([{"symptom": "legacy", "severity": 3, "date": "2026-10-12"}, "junk", None,
                               {"id": "k", "symptom": "k", "severity": "bad", "date": "2026-10-12"},
                               {"id": "j", "symptom": "j", "severity": 4, "date": "garbage"}])
        out = summary(planner)
        assert "Legacy" in out and "Journal" not in out
        assert "K:" not in out and "J:" not in out
        assert all(r["id"] for r in storage.load_symptoms() if isinstance(r, dict))

    def test_not_a_list_store(self, planner):
        import storage
        storage.save_symptoms({"x": 1})
        assert summary(planner) == "No symptoms logged in the last 30 days."

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        log(planner)
        path = backup.run_backup()
        storage.save_symptoms([])
        restore.restore_backup(path, only="symptoms", safety_backup=False)
        assert rows()[0]["symptom"] == "headache"

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        assert schemas["log_symptom"]["parameters"]["required"] == ["symptom", "severity"]
        assert schemas["log_symptom"]["parameters"]["properties"]["date"] == planner._ENTRY_DATE_PROP
        assert schemas["get_symptom_summary"]["parameters"]["required"] == []
