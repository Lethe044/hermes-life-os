"""Entry management: list / edit / delete / undo for the trackers, gap finder, journal links."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

DEMO = Path(__file__).parent.parent / "demo"
sys.path.insert(0, str(DEMO))

import clock  # noqa: E402 - needs the demo/ path set up above

CASES = {
    "meals": ("log_meal", {"meal_time": "lunch", "food": "soup", "calories": 300}, "load_nutrition"),
    "sleep": ("log_sleep", {"hours": 7, "quality": 6}, "load_sleep"),
    "workouts": ("log_workout", {"workout_type": "run", "duration_min": 30}, "load_fitness"),
    "stress": ("log_stress", {"score": 4, "trigger": "deadline"}, "load_mental"),
    "meditation": ("log_meditation", {"duration_min": 10}, "load_mental"),
    "gratitude": ("log_gratitude", {"items": ["sun", "tea"]}, "load_mental"),
    "focus": ("log_focus_session", {"duration_min": 25, "task": "write"}, "load_focus"),
    "social": ("log_social_interaction", {"with_who": "Sam", "quality": 8}, "load_social"),
    "substances": ("log_substance", {"substance": "coffee", "amount": 2, "unit": "cups"}, "load_substance"),
    "reading": ("log_reading", {"title": "Dune", "minutes": 20, "pages": 10}, "load_reading"),
    "medication": ("log_medication", {"name": "vitamin d"}, "load_medication"),
}
# one valid edit per tracker: (fields, expected row key, expected value)
EDITS = {
    "meals": ({"calories": 450}, "calories", 450),
    "sleep": ({"hours": 8.5}, "hours", 8.5),
    "workouts": ({"duration_min": 45}, "duration", 45),
    "stress": ({"score": 9}, "score", 9),
    "meditation": ({"duration_min": 20}, "duration", 20),
    "gratitude": ({"items": "a, b"}, "items", ["a", "b"]),
    "focus": ({"distractions": 3}, "distractions", 3),
    "social": ({"quality": 3}, "quality", 3),
    "substances": ({"substance": " Tea "}, "substance", "tea"),
    "reading": ({"pages": 33}, "pages", 33),
    "medication": ({"taken": "no"}, "taken", False),
}


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None) or ""
        if path.startswith(str(DEMO)) and name != "clock":
            del sys.modules[name]
    when = datetime(2026, 10, 12, 9, 0)
    monkeypatch.setattr(clock, "now", lambda: when)
    import tools
    importlib.reload(tools)
    import storage
    storage.set_active_profile(None)
    return tools


def rows(tracker):
    import entries
    return entries.list_logs(tracker, days=400, limit=200)


def log(app, tracker, **extra):
    tool, args, _ = CASES[tracker]
    app.dispatch_tool(tool, {**args, **extra})
    return rows(tracker)[0] if not extra.get("date") else next(r for r in rows(tracker) if r["date"] == extra["date"])


@pytest.mark.parametrize("tracker", sorted(CASES))
class TestEveryTracker:
    def test_new_log_carries_an_id_and_the_journal_is_linked(self, app, tracker):
        import storage
        tool, args, loader = CASES[tracker]
        app.dispatch_tool(tool, dict(args))
        row = getattr(storage, loader)()[-1]
        assert len(row["id"]) == 8
        if tracker != "medication":
            assert storage.get_all_memory()[-1]["log_id"] == row["id"]

    def test_list(self, app, tracker):
        row = log(app, tracker)
        out = app.dispatch_tool("list_logs", {"tracker": tracker})
        assert f"[id={row['id']}] 2026-10-12" in out
        assert out.startswith("1 ")

    def test_edit_changes_the_row(self, app, tracker):
        row = log(app, tracker)
        fields, key, expected = EDITS[tracker]
        out = app.dispatch_tool("edit_log", {"tracker": tracker, "log_id": row["id"], "fields": fields})
        assert out.startswith(f"Updated [id={row['id']}]")
        assert rows(tracker)[0][key] == expected

    def test_edit_syncs_the_journal(self, app, tracker):
        import storage
        row = log(app, tracker)
        import entries
        if tracker == "medication":
            # medication has no journal entry: editing must not create one
            fields, _, _ = EDITS[tracker]
            app.dispatch_tool("edit_log", {"tracker": tracker, "log_id": row["id"], "fields": fields})
            assert storage.get_all_memory() == []
            return
        fields, _, _ = EDITS[tracker]
        app.dispatch_tool("edit_log", {"tracker": tracker, "log_id": row["id"], "fields": fields})
        after = storage.get_all_memory()[-1]
        assert after["log_id"] == row["id"]
        edited = rows(tracker)[0]
        for key, value in entries.TRACKERS[tracker]["journal"](edited).items():
            assert after[key] == value, (tracker, key)

    def test_edit_date_moves_journal_stamp(self, app, tracker):
        import storage
        row = log(app, tracker)
        app.dispatch_tool("edit_log", {"tracker": tracker, "log_id": row["id"], "fields": {"date": "2026-10-01"}})
        assert rows(tracker)[0]["date"] == "2026-10-01"
        if tracker != "medication":
            assert storage.get_all_memory()[-1]["timestamp"] == "2026-10-01T12:00:00Z"

    def test_delete_removes_only_that_row_and_its_journal(self, app, tracker):
        import storage
        keep = log(app, tracker, date="2026-10-10")
        gone = log(app, tracker)
        out = app.dispatch_tool("delete_log", {"tracker": tracker, "log_id": gone["id"]})
        assert out.startswith(f"Deleted [id={gone['id']}]")
        assert [r["id"] for r in rows(tracker)] == [keep["id"]]
        assert gone["id"] not in {m.get("log_id") for m in storage.get_all_memory()}

    def test_undo_with_tracker(self, app, tracker):
        keep = log(app, tracker, date="2026-10-10")
        log(app, tracker)
        out = app.dispatch_tool("undo_last_log", {"tracker": tracker})
        assert out.startswith(f"Undid the last {tracker} entry")
        assert [r["id"] for r in rows(tracker)] == [keep["id"]]

    def test_wrong_id_and_empty_fields(self, app, tracker):
        row = log(app, tracker)
        assert "No %s entry found" % tracker in app.dispatch_tool(
            "edit_log", {"tracker": tracker, "log_id": "nope", "fields": {"date": "2026-10-01"}})
        assert "No %s entry found" % tracker in app.dispatch_tool("delete_log", {"tracker": tracker, "log_id": "nope"})
        assert app.dispatch_tool("edit_log", {"tracker": tracker, "log_id": row["id"], "fields": {}}) \
            .startswith("Not changed: Nothing to change")

    def test_unknown_field_changes_nothing(self, app, tracker):
        import storage
        row = log(app, tracker)
        before = rows(tracker)
        out = app.dispatch_tool("edit_log", {"tracker": tracker, "log_id": row["id"],
                                             "fields": {"bogus": 1, "date": "2026-10-01"}})
        assert "'bogus' cannot be edited" in out
        assert rows(tracker) == before

    def test_gap_finder(self, app, tracker):
        log(app, tracker, date="2026-10-10")
        out = app.dispatch_tool("get_logging_gaps", {"tracker": tracker, "days": 3})
        assert "2026-10-09, 2026-10-11" in out and "2026-10-10" not in out.split(":", 1)[1].split(".")[0]


class TestMentalStoreSeparation:
    def test_trackers_sharing_the_mental_store_do_not_see_each_other(self, app):
        s = log(app, "stress")
        m = log(app, "meditation")
        g = log(app, "gratitude")
        assert [r["id"] for r in rows("stress")] == [s["id"]]
        assert [r["id"] for r in rows("meditation")] == [m["id"]]
        assert [r["id"] for r in rows("gratitude")] == [g["id"]]
        assert "No stress entry found" in app.dispatch_tool("delete_log", {"tracker": "stress", "log_id": m["id"]})
        assert "No meditation entry found" in app.dispatch_tool(
            "edit_log", {"tracker": "meditation", "log_id": s["id"], "fields": {"notes": "x"}})

    def test_undo_stress_leaves_meditation(self, app):
        log(app, "meditation")
        log(app, "stress")
        app.dispatch_tool("undo_last_log", {"tracker": "stress"})
        assert len(rows("meditation")) == 1 and rows("stress") == []


class TestValidation:
    @pytest.mark.parametrize("tracker,fields,msg", [
        ("meals", {"calories": -5}, "0 or more"), ("meals", {"calories": "lots"}, "must be a number"),
        ("meals", {"calories": float("nan")}, "0 or more"), ("meals", {"calories": True}, "must be a number"),
        ("meals", {"food": 5}, "must be text"), ("sleep", {"quality": 11}, "1 to 10"),
        ("sleep", {"quality": 2.5}, "1 to 10"), ("sleep", {"quality": True}, "1 to 10"),
        ("sleep", {"hours": float("inf")}, "0 or more"), ("stress", {"score": 0}, "1 to 10"),
        ("focus", {"completed": "maybe"}, "true or false"), ("focus", {"distractions": -1}, "0 to 1000"),
        ("gratitude", {"items": []}, "at least one"), ("gratitude", {"items": [1]}, "list of text"),
        ("gratitude", {"items": " , "}, "at least one"), ("meals", {"date": "2026-10-13"}, "in the future"),
        ("meals", {"date": "soon"}, "YYYY-MM-DD"), ("meals", {"date": ""}, "date cannot be empty"),
        ("meals", {"date": None}, "date cannot be empty"),
    ])
    def test_invalid_edit_changes_nothing(self, app, tracker, fields, msg):
        import storage
        row = log(app, tracker)
        before = (rows(tracker), storage.get_all_memory())
        out = app.dispatch_tool("edit_log", {"tracker": tracker, "log_id": row["id"], "fields": fields})
        assert out.startswith("Not changed: ") and msg in out
        assert (rows(tracker), storage.get_all_memory()) == before

    def test_partly_invalid_edit_applies_nothing(self, app):
        row = log(app, "meals")
        app.dispatch_tool("edit_log", {"tracker": "meals", "log_id": row["id"],
                                       "fields": {"calories": 999, "date": "garbage"}})
        assert rows("meals")[0]["calories"] == 300

    def test_integral_floats_become_ints(self, app):
        row = log(app, "meals")
        app.dispatch_tool("edit_log", {"tracker": "meals", "log_id": row["id"], "fields": {"calories": 450.0}})
        assert rows("meals")[0]["calories"] == 450 and isinstance(rows("meals")[0]["calories"], int)

    def test_unknown_tracker(self, app):
        for tool in ("list_logs", "delete_log", "edit_log"):
            out = app.dispatch_tool(tool, {"tracker": "nope", "log_id": "x", "fields": {"a": 1}})
            assert "Unknown tracker 'nope'" in out
        assert "Unknown tracker" in app.dispatch_tool("undo_last_log", {"tracker": "nope"})
        assert "Unknown tracker" in app.dispatch_tool("get_logging_gaps", {"tracker": "nope"})

    def test_tracker_name_is_case_insensitive(self, app):
        log(app, "meals")
        assert app.dispatch_tool("list_logs", {"tracker": " MEALS "}).startswith("1 ")

    def test_journal_content_follows_edits(self, app):
        import storage
        row = log(app, "workouts")
        app.dispatch_tool("edit_log", {"tracker": "workouts", "log_id": row["id"],
                                       "fields": {"workout_type": "swim", "duration_min": 50}})
        m = storage.get_all_memory()[-1]
        assert m["content"] == "swim 50min" and m["workout_type"] == "swim" and m["duration"] == 50

    def test_sleep_edit_updates_hours_quality_in_journal(self, app):
        import storage
        row = log(app, "sleep")
        app.dispatch_tool("edit_log", {"tracker": "sleep", "log_id": row["id"], "fields": {"hours": 5, "quality": 2}})
        m = storage.get_all_memory()[-1]
        assert (m["content"], m["hours"], m["quality"]) == ("5h sleep", 5, 2)

    def test_readers_see_the_correction(self, app):
        row = log(app, "meals")
        app.dispatch_tool("edit_log", {"tracker": "meals", "log_id": row["id"], "fields": {"calories": 1000}})
        assert "1000" in app.dispatch_tool("get_meal_summary", {"days": 7})


class TestListing:
    def test_empty(self, app):
        assert app.dispatch_tool("list_logs", {"tracker": "sleep"}) == "No sleep entries found in the last 7 days."

    def test_window_and_limit_and_order(self, app):
        a = log(app, "meals", date="2026-10-01")
        b = log(app, "meals", date="2026-10-11")
        c = log(app, "meals", date="2026-10-12")
        out = app.dispatch_tool("list_logs", {"tracker": "meals", "days": 3})
        assert a["id"] not in out and out.index(c["id"]) < out.index(b["id"])
        assert app.dispatch_tool("list_logs", {"tracker": "meals", "days": 30, "limit": 1}).startswith("1 meals entry")

    def test_bad_numbers(self, app):
        assert "whole numbers" in app.dispatch_tool("list_logs", {"tracker": "meals", "days": "soon"})

    def test_legacy_rows_get_ids_once_and_keep_existing_ones(self, app):
        import storage
        storage.save_sleep([{"date": "2026-10-10", "hours": 7}, {"date": "2026-10-11", "hours": 6, "id": "keepme01"}])
        app.dispatch_tool("list_logs", {"tracker": "sleep"})
        first = storage.load_sleep()
        assert first[1]["id"] == "keepme01" and first[0]["id"] and first[0]["id"] != "keepme01"
        app.dispatch_tool("list_logs", {"tracker": "sleep"})
        assert storage.load_sleep() == first

    def test_legacy_row_without_a_journal_twin_can_be_edited_and_deleted(self, app):
        import storage
        storage.save_sleep([{"date": "2026-10-10", "hours": 7, "quality": 5}])
        rid = rows("sleep")[0]["id"]
        assert app.dispatch_tool("edit_log", {"tracker": "sleep", "log_id": rid, "fields": {"hours": 6}}).startswith("Updated")
        assert storage.load_sleep()[0]["hours"] == 6
        assert app.dispatch_tool("delete_log", {"tracker": "sleep", "log_id": rid}).startswith("Deleted")
        assert storage.load_sleep() == []

    def test_malformed_rows_are_tolerated(self, app):
        import storage
        storage.save_sleep([{"date": "2026-10-10", "hours": 7}, "junk", {"hours": 3}, None])
        assert len(rows("sleep")) == 1

    def test_missing_fields_do_not_crash_labels(self, app):
        import storage
        storage.save_sleep([{"date": "2026-10-10"}])
        storage.save_nutrition([{"date": "2026-10-10"}])
        assert "[id=" in app.dispatch_tool("list_logs", {"tracker": "sleep"})
        assert "[id=" in app.dispatch_tool("list_logs", {"tracker": "meals"})


class TestUndoWithoutTracker:
    def test_undoes_whatever_was_logged_last(self, app):
        log(app, "meals")
        log(app, "sleep")
        out = app.dispatch_tool("undo_last_log", {})
        assert out.startswith("Undid the last sleep entry")
        assert len(rows("meals")) == 1 and rows("sleep") == []

    def test_works_across_trackers_repeatedly(self, app):
        import storage
        log(app, "meals")
        app.dispatch_tool("log_expense", {"amount": 5, "category": "food"})
        log(app, "workouts")
        names = [app.dispatch_tool("undo_last_log", {}).split()[3] for _ in range(3)]
        assert names == ["workouts", "expenses", "meals"]
        assert storage.load_spending() == [] and storage.get_all_memory() == []

    def test_nothing_to_undo(self, app):
        assert app.dispatch_tool("undo_last_log", {}) == "Nothing to undo - no entries found."
        assert app.dispatch_tool("undo_last_log", {"tracker": "sleep"}) == "Nothing to undo - no sleep entries found."

    def test_expenses_by_name(self, app):
        import storage
        app.dispatch_tool("log_expense", {"amount": 5, "category": "a"})
        app.dispatch_tool("log_expense", {"amount": 7, "category": "b"})
        out = app.dispatch_tool("undo_last_log", {"tracker": "expenses"})
        assert "7.00 b" in out and [e["category"] for e in storage.load_spending()] == ["a"]

    def test_expenses_by_name_when_empty(self, app):
        assert "Nothing to undo" in app.dispatch_tool("undo_last_log", {"tracker": "expenses"})

    def test_skips_journal_entries_whose_row_is_gone(self, app):
        import storage
        log(app, "meals")
        row = log(app, "sleep")
        storage.save_sleep([])  # sleep row vanished (e.g. partial restore), its journal entry stays
        out = app.dispatch_tool("undo_last_log", {})
        assert out.startswith("Undid the last meals entry")

    def test_does_not_touch_unlinked_journal_entries(self, app):
        import storage
        app.dispatch_tool("remember", {"type": "note", "content": "hello"})
        assert app.dispatch_tool("undo_last_log", {}).startswith("Nothing to undo")
        assert len(storage.get_all_memory()) == 1

    def test_blank_tracker_means_none(self, app):
        log(app, "meals")
        assert app.dispatch_tool("undo_last_log", {"tracker": "  "}).startswith("Undid the last meals")


class TestDeleteEntryCascade:
    def test_deleting_a_journal_entry_removes_the_linked_row(self, app):
        import storage
        log(app, "meals")
        mem = storage.get_all_memory()[-1]
        out = app.dispatch_tool("delete_entry", {"entry_id": mem["id"]})
        assert "linked meals entry was removed too" in out
        assert storage.load_nutrition() == []

    def test_linked_expense(self, app):
        import storage
        app.dispatch_tool("log_expense", {"amount": 5, "category": "a"})
        mem = storage.get_all_memory()[-1]
        out = app.dispatch_tool("delete_entry", {"entry_id": mem["id"]})
        assert "linked expenses entry was removed too" in out and storage.load_spending() == []

    def test_unlinked_entry_message_unchanged(self, app):
        import storage
        app.dispatch_tool("remember", {"type": "note", "content": "x"})
        mem = storage.get_all_memory()[-1]
        out = app.dispatch_tool("delete_entry", {"entry_id": mem["id"]})
        assert out == f"Deleted entry [id={mem['id']}]. This can't be undone."

    def test_row_already_gone_is_fine(self, app):
        import storage
        log(app, "meals")
        mem = storage.get_all_memory()[-1]
        storage.save_nutrition([])
        assert app.dispatch_tool("delete_entry", {"entry_id": mem["id"]}) == \
            f"Deleted entry [id={mem['id']}]. This can't be undone."

    def test_unknown_id_message_unchanged(self, app):
        assert "No entry found with id 'zz'" in app.dispatch_tool("delete_entry", {"entry_id": "zz"})

    def test_other_rows_untouched(self, app):
        import storage
        log(app, "meals", date="2026-10-10")
        log(app, "meals")
        app.dispatch_tool("delete_entry", {"entry_id": storage.get_all_memory()[-1]["id"]})
        assert [r["date"] for r in storage.load_nutrition()] == ["2026-10-10"]


class TestGaps:
    def test_none_missing(self, app):
        for d in ("2026-10-09", "2026-10-10", "2026-10-11"):
            log(app, "sleep", date=d)
        out = app.dispatch_tool("get_logging_gaps", {"tracker": "sleep", "days": 3})
        assert out == "sleep: logged on every one of the last 3 complete days. Nothing to fill in."

    def test_today_is_not_counted(self, app):
        out = app.dispatch_tool("get_logging_gaps", {"tracker": "sleep", "days": 1})
        assert "2026-10-11" in out and "2026-10-12" not in out

    def test_all_missing_message(self, app):
        out = app.dispatch_tool("get_logging_gaps", {"tracker": "sleep", "days": 3})
        assert "nothing logged on any of the last 3 complete days (2026-10-09 to 2026-10-11)" in out

    def test_hydration_and_expenses(self, app):
        app.dispatch_tool("log_hydration", {"glasses": 2, "date": "2026-10-11"})
        app.dispatch_tool("log_expense", {"amount": 3, "category": "x", "date": "2026-10-10"})
        assert "2026-10-09, 2026-10-10" in app.dispatch_tool("get_logging_gaps", {"tracker": "hydration", "days": 3})
        assert "2026-10-09, 2026-10-11" in app.dispatch_tool("get_logging_gaps", {"tracker": "expenses", "days": 3})

    def test_stress_ignores_other_mental_entries(self, app):
        log(app, "meditation", date="2026-10-11")
        out = app.dispatch_tool("get_logging_gaps", {"tracker": "stress", "days": 1})
        assert "2026-10-11" in out

    def test_bad_days(self, app):
        assert "whole number" in app.dispatch_tool("get_logging_gaps", {"tracker": "sleep", "days": "x"})

    def test_days_are_clamped(self, app):
        import entries
        assert len(entries.missing_days("sleep", 10_000)) == 366
        assert len(entries.missing_days("sleep", 0)) == 1

    def test_respects_the_day_start_hour(self, app, monkeypatch):
        monkeypatch.setenv("LIFE_OS_DAY_START_HOUR", "10")  # 09:00 on the 12th is still the 11th
        out = app.dispatch_tool("get_logging_gaps", {"tracker": "sleep", "days": 1})
        assert "2026-10-10" in out and "2026-10-11" not in out

    def test_backfilling_closes_the_gap(self, app):
        app.dispatch_tool("log_sleep", {"hours": 7, "date": "2026-10-10"})
        out = app.dispatch_tool("get_logging_gaps", {"tracker": "sleep", "days": 2})
        assert "2026-10-11" in out and "2026-10-10" not in out.split(":", 1)[1].split(".")[0]


class TestDreamBackdating:
    def test_dream_date_and_stamp(self, app):
        import storage
        out = app.dispatch_tool("log_dream", {"content": "flying", "date": "2026-10-09"})
        assert out.startswith("Dream logged")
        m = storage.get_all_memory()[-1]
        assert m["date"] == "2026-10-09" and m["timestamp"] == "2026-10-09T12:00:00Z"

    def test_dream_today_and_bad_date(self, app):
        import storage
        app.dispatch_tool("log_dream", {"content": "x"})
        assert storage.get_all_memory()[-1]["date"] == "2026-10-12"
        out = app.dispatch_tool("log_dream", {"content": "y", "date": "2099-01-01"})
        assert out.startswith("Not logged: ") and len(storage.get_all_memory()) == 1


class TestSchemas:
    def test_new_tools_registered(self, app):
        schemas = {t["function"]["name"]: t["function"] for t in app.TOOLS}
        for n in ("list_logs", "edit_log", "delete_log", "undo_last_log", "get_logging_gaps"):
            assert n in schemas
        assert schemas["edit_log"]["parameters"]["required"] == ["tracker", "log_id", "fields"]
        assert schemas["undo_last_log"]["parameters"]["required"] == []

    def test_enum_matches_registry(self, app):
        import entries
        assert app._TRACKER_NAMES == entries.tracker_names()
        schemas = {t["function"]["name"]: t["function"] for t in app.TOOLS}
        assert schemas["list_logs"]["parameters"]["properties"]["tracker"]["enum"] == entries.tracker_names()

    def test_every_tracker_maps_to_a_real_log_tool(self, app):
        import entries
        schemas = {t["function"]["name"]: t["function"] for t in app.TOOLS}
        for tracker, (tool, _, _) in CASES.items():
            props = schemas[tool]["parameters"]["properties"]
            for arg in entries.TRACKERS[tracker]["fields"]:
                assert arg in props or arg in ("fields",), (tracker, arg)

    def test_undo_without_args_never_raises(self, app):
        assert isinstance(app.dispatch_tool("undo_last_log", {}), str)


class TestExportsStillWork:
    def test_csv_export_copes_with_ids(self, app, tmp_path):
        import data_export
        log(app, "meals")
        app.dispatch_tool("log_expense", {"amount": 5, "category": "a"})
        out = tmp_path / "out.csv"
        assert data_export.export_csv(str(out)) >= 1
        assert out.read_text(encoding="utf-8").strip()

    def test_backup_payload_has_the_ids(self, app):
        import data_export
        log(app, "meals")
        assert data_export.build_backup_payload()["nutrition"][0]["id"]


class TestGapsOverview:
    def test_only_used_trackers_listed(self, app):
        log(app, "sleep", date="2026-10-10")
        log(app, "meals", date="2026-10-11")
        out = app.dispatch_tool("get_logging_gaps", {"days": 3})
        assert "- sleep: 2 of 3 days empty: 2026-10-09, 2026-10-11" in out
        assert "- meals: 2 of 3 days empty: 2026-10-09, 2026-10-10" in out
        assert "workouts" not in out and out.rstrip().endswith("date argument.")

    def test_all_keyword_and_blank_are_the_same(self, app):
        log(app, "sleep", date="2026-10-10")
        a = app.dispatch_tool("get_logging_gaps", {"tracker": "all", "days": 3})
        assert a == app.dispatch_tool("get_logging_gaps", {"tracker": " ", "days": 3})

    def test_no_data_at_all(self, app):
        assert app.dispatch_tool("get_logging_gaps", {}).startswith("No gaps: every tracker you use")

    def test_complete_trackers_are_not_listed(self, app):
        for d in ("2026-10-09", "2026-10-10", "2026-10-11"):
            log(app, "sleep", date=d)
        assert app.dispatch_tool("get_logging_gaps", {"days": 3}).startswith("No gaps")

    def test_long_gap_list_is_truncated_to_the_latest_five(self, app):
        log(app, "sleep", date="2026-09-01")
        out = app.dispatch_tool("get_logging_gaps", {"days": 30})
        assert "(latest 5 shown)" in out and "2026-10-11" in out and "2026-09-20" not in out

    def test_includes_hydration_and_expenses(self, app):
        app.dispatch_tool("log_hydration", {"glasses": 1, "date": "2026-10-10"})
        app.dispatch_tool("log_expense", {"amount": 1, "category": "x", "date": "2026-10-10"})
        out = app.dispatch_tool("get_logging_gaps", {"days": 2})
        assert "- hydration:" in out and "- expenses:" in out

    def test_bad_days(self, app):
        log(app, "sleep")
        assert "whole number" in app.dispatch_tool("get_logging_gaps", {"days": "x"})
