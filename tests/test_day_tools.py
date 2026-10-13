"""get_day_log, search_logs, find_duplicate_logs and log_many."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

DEMO = Path(__file__).parent.parent / "demo"
sys.path.insert(0, str(DEMO))

import clock  # noqa: E402 - needs the demo/ path set up above


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


def meal(app, food="soup", **extra):
    return app.dispatch_tool("log_meal", {"meal_time": "lunch", "food": food, "calories": 300, **extra})


class TestDayLog:
    def test_empty_day(self, app):
        assert app.dispatch_tool("get_day_log", {}) == "Nothing logged on 2026-10-12."

    def test_groups_by_tracker_with_ids(self, app):
        meal(app)
        meal(app, "pasta")
        app.dispatch_tool("log_sleep", {"hours": 7, "quality": 6})
        app.dispatch_tool("log_expense", {"amount": 4, "category": "coffee"})
        app.dispatch_tool("log_hydration", {"glasses": 2})
        app.dispatch_tool("log_medication", {"name": "vit d"})
        out = app.dispatch_tool("get_day_log", {})
        assert out.startswith("Everything logged on 2026-10-12:")
        for header in ("meals (2)", "sleep (1)", "expenses (1)", "hydration (1)", "medication (1)"):
            assert header in out
        assert out.count("[id=") == 6 and "soup (300 cal)" in out and "4.00 coffee" in out

    def test_other_days_are_excluded(self, app):
        meal(app, "old", date="2026-10-09")
        meal(app, "new")
        out = app.dispatch_tool("get_day_log", {"date": "2026-10-09"})
        assert "old" in out and "new" not in out

    def test_mental_store_entries_are_split_by_tracker(self, app):
        app.dispatch_tool("log_stress", {"score": 4, "trigger": "x"})
        app.dispatch_tool("log_meditation", {"duration_min": 5})
        out = app.dispatch_tool("get_day_log", {})
        assert "stress (1)" in out and "meditation (1)" in out

    @pytest.mark.parametrize("bad", ["yesterday", "2026-13-01", "10/12/2026", 5])
    def test_bad_dates(self, app, bad):
        assert "YYYY-MM-DD" in app.dispatch_tool("get_day_log", {"date": bad})

    def test_future_and_old_dates_are_viewable(self, app):
        assert app.dispatch_tool("get_day_log", {"date": "2031-01-01"}) == "Nothing logged on 2031-01-01."
        assert app.dispatch_tool("get_day_log", {"date": "2001-01-01"}) == "Nothing logged on 2001-01-01."

    def test_ids_match_the_edit_tools(self, app):
        meal(app)
        rid = app.dispatch_tool("get_day_log", {}).split("[id=")[1].split("]")[0]
        assert app.dispatch_tool("edit_log", {"tracker": "meals", "log_id": rid,
                                              "fields": {"calories": 1}}).startswith("Updated")

    def test_blank_date_means_today(self, app):
        meal(app)
        assert "meals (1)" in app.dispatch_tool("get_day_log", {"date": "  "})

    def test_viewing_is_read_only(self, app):
        import storage
        storage.save_sleep([{"date": "2026-10-12", "hours": 7}])  # legacy row without id
        app.dispatch_tool("get_day_log", {})
        assert "id" in storage.load_sleep()[0]  # ids are handed out once, nothing else changes
        assert storage.load_sleep()[0]["hours"] == 7


class TestSearch:
    def test_finds_by_food_notes_and_names(self, app):
        meal(app, "pepperoni pizza", date="2026-10-10")
        app.dispatch_tool("log_social_interaction", {"with_who": "Sam", "quality": 8, "notes": "pizza night"})
        app.dispatch_tool("log_expense", {"amount": 9, "category": "food", "notes": "Pizza delivery"})
        out = app.dispatch_tool("search_logs", {"query": "PIZZA"})
        assert out.startswith("3 of 3 entries mention 'PIZZA', newest first:")
        assert out.count("[") == 3 and "[meals id=" in out and "[social id=" in out and "[expenses id=" in out

    def test_newest_first(self, app):
        meal(app, "a pizza", date="2026-10-01")
        meal(app, "b pizza", date="2026-10-11")
        out = app.dispatch_tool("search_logs", {"query": "pizza"})
        assert out.index("2026-10-11") < out.index("2026-10-01")

    def test_no_match(self, app):
        meal(app)
        assert app.dispatch_tool("search_logs", {"query": "zzz"}) == "No entries mention 'zzz' in the last 30 days."

    def test_days_window(self, app):
        meal(app, "pizza", date="2026-09-01")
        assert "No entries mention" in app.dispatch_tool("search_logs", {"query": "pizza", "days": 7})

    def test_limit_and_count(self, app):
        for _ in range(5):
            meal(app, "pizza")
        out = app.dispatch_tool("search_logs", {"query": "pizza", "limit": 2})
        assert out.startswith("2 of 5 entries") and out.count("[meals") == 2

    def test_blank_query(self, app):
        for q in ("", "  ", None, 5):
            assert app.dispatch_tool("search_logs", {"query": q}) == "Give some text to search for."

    def test_bad_numbers(self, app):
        assert "whole numbers" in app.dispatch_tool("search_logs", {"query": "x", "days": "soon"})

    def test_matches_list_fields_like_gratitude_items(self, app):
        app.dispatch_tool("log_gratitude", {"items": ["sunshine", "tea"]})
        assert "gratitude" in app.dispatch_tool("search_logs", {"query": "sunshine"})

    def test_ids_are_not_searched(self, app):
        meal(app)
        rid = app.dispatch_tool("get_day_log", {}).split("[id=")[1].split("]")[0]
        assert "No entries mention" in app.dispatch_tool("search_logs", {"query": rid})

    def test_singular_wording(self, app):
        meal(app, "pizza")
        assert app.dispatch_tool("search_logs", {"query": "pizza"}).startswith("1 of 1 entry mention")


class TestDuplicates:
    def test_none(self, app):
        meal(app)
        assert app.dispatch_tool("find_duplicate_logs", {}) == "No duplicate entries found in the last 30 days."

    def test_double_logged_meal(self, app):
        meal(app)
        meal(app)
        out = app.dispatch_tool("find_duplicate_logs", {})
        assert out.startswith("1 possible duplicate group(s)") and "meals 2026-10-12: soup (300 cal) x2" in out
        ids = out.split("(ids: ")[1].split(")")[0].split(", ")
        assert len(set(ids)) == 2 and out.rstrip().endswith("delete_expense for expenses).")

    def test_different_calories_are_not_duplicates(self, app):
        meal(app)
        app.dispatch_tool("log_meal", {"meal_time": "lunch", "food": "soup", "calories": 310})
        assert "No duplicate" in app.dispatch_tool("find_duplicate_logs", {})

    def test_same_entry_on_different_days_is_fine(self, app):
        meal(app)
        meal(app, date="2026-10-11")
        assert "No duplicate" in app.dispatch_tool("find_duplicate_logs", {})

    def test_hydration_is_ignored(self, app):
        app.dispatch_tool("log_hydration", {"glasses": 1})
        app.dispatch_tool("log_hydration", {"glasses": 1})
        assert "No duplicate" in app.dispatch_tool("find_duplicate_logs", {})

    def test_expenses_and_triplicates(self, app):
        for _ in range(3):
            app.dispatch_tool("log_expense", {"amount": 5, "category": "coffee"})
        out = app.dispatch_tool("find_duplicate_logs", {})
        assert "expenses 2026-10-12: 5.00 coffee x3" in out

    def test_window(self, app):
        meal(app, date="2026-08-01")
        meal(app, date="2026-08-01")
        assert "No duplicate" in app.dispatch_tool("find_duplicate_logs", {"days": 30})
        assert "1 possible duplicate" in app.dispatch_tool("find_duplicate_logs", {"days": 90})

    def test_report_only(self, app):
        import storage
        meal(app)
        meal(app)
        app.dispatch_tool("find_duplicate_logs", {})
        assert len(storage.load_nutrition()) == 2

    def test_bad_days(self, app):
        assert "whole number" in app.dispatch_tool("find_duplicate_logs", {"days": "x"})

    def test_deleting_the_extra_clears_the_report(self, app):
        meal(app)
        meal(app)
        out = app.dispatch_tool("find_duplicate_logs", {})
        rid = out.split("(ids: ")[1].split(")")[0].split(", ")[1]
        app.dispatch_tool("delete_log", {"tracker": "meals", "log_id": rid})
        assert "No duplicate" in app.dispatch_tool("find_duplicate_logs", {})


class TestLogMany:
    def test_logs_a_whole_day(self, app):
        import storage
        out = app.dispatch_tool("log_many", {"entries": [
            {"tool": "log_meal", "args": {"meal_time": "breakfast", "food": "eggs", "calories": 200, "date": "2026-10-10"}},
            {"tool": "log_sleep", "args": {"hours": 7, "date": "2026-10-10"}},
            {"tool": "log_hydration", "args": {"glasses": 3, "date": "2026-10-10"}},
            {"tool": "log_expense", "args": {"amount": 4, "category": "coffee", "date": "2026-10-10"}},
        ]})
        assert out.startswith("Logged 4 of 4 entries.")
        assert [l.split(":")[0] for l in out.splitlines()[1:]] == ["1. log_meal", "2. log_sleep", "3. log_hydration", "4. log_expense"]
        assert storage.load_nutrition()[0]["date"] == "2026-10-10"
        assert storage.load_spending()[0]["date"] == "2026-10-10"
        assert storage.load_hydration()["log"][0]["date"] == "2026-10-10"

    def test_one_bad_date_logs_nothing(self, app):
        import storage
        out = app.dispatch_tool("log_many", {"entries": [
            {"tool": "log_meal", "args": {"meal_time": "lunch", "food": "x", "calories": 1}},
            {"tool": "log_sleep", "args": {"hours": 7, "date": "2099-01-01"}},
        ]})
        assert out.startswith("Nothing logged: entry 2 (log_sleep): ") and "in the future" in out
        assert storage.load_nutrition() == [] and storage.load_sleep() == []

    @pytest.mark.parametrize("entries,fragment", [
        ([], "non-empty list"), (None, "non-empty list"), ("meal", "non-empty list"),
        ([{"tool": "delete_log", "args": {}}], "entry 1 must be"),
        ([{"tool": "log_meal", "args": "soup"}], "entry 1 must be"),
        (["log_meal"], "entry 1 must be"), ([{"args": {}}], "entry 1 must be"),
        ([{"tool": "remember", "args": {"type": "x"}}], "entry 1 must be"),
    ])
    def test_bad_shapes_log_nothing(self, app, entries, fragment):
        import storage
        out = app.dispatch_tool("log_many", {"entries": entries})
        assert out.startswith("Nothing logged: ") and fragment in out
        assert storage.get_all_memory() == []

    def test_too_many(self, app):
        entries = [{"tool": "log_medication", "args": {"name": "x"}}] * 51
        assert "at most 50" in app.dispatch_tool("log_many", {"entries": entries})
        assert app.dispatch_tool("log_many", {"entries": entries[:50]}).startswith("Logged 50 of 50")

    def test_missing_args_defaults(self, app):
        assert app.dispatch_tool("log_many", {"entries": [{"tool": "log_medication"}]}).startswith("Logged 1 of 1")

    def test_a_crash_in_one_entry_does_not_stop_the_rest(self, app):
        import storage
        out = app.dispatch_tool("log_many", {"entries": [
            {"tool": "log_expense", "args": {"amount": "lots", "category": "x"}},
            {"tool": "log_medication", "args": {"name": "vit d"}},
        ]})
        assert out.startswith("Logged 1 of 2 entries.") and "Not logged: ValueError" in out
        assert len(storage.load_medication()) == 1

    def test_entries_get_ids_and_journal_links(self, app):
        import storage
        app.dispatch_tool("log_many", {"entries": [{"tool": "log_meal", "args": {"meal_time": "lunch", "food": "x", "calories": 1}}]})
        assert storage.get_all_memory()[-1]["log_id"] == storage.load_nutrition()[0]["id"]

    def test_args_are_not_mutated(self, app):
        args = {"meal_time": "lunch", "food": "x", "calories": 1}
        batch = {"entries": [{"tool": "log_meal", "args": args}]}
        app.dispatch_tool("log_many", batch)
        assert args == {"meal_time": "lunch", "food": "x", "calories": 1}

    def test_dreams_and_habit_free(self, app):
        assert app.dispatch_tool("log_many", {"entries": [{"tool": "log_dream", "args": {"content": "flying"}}]}) \
            .startswith("Logged 1 of 1")
        assert "Nothing logged" in app.dispatch_tool("log_many", {"entries": [
            {"tool": "update_habit", "args": {"habit_name": "x", "completed": True}}]})

    def test_schema(self, app):
        schemas = {t["function"]["name"]: t["function"] for t in app.TOOLS}
        for n in ("get_day_log", "search_logs", "find_duplicate_logs", "log_many"):
            assert n in schemas
        enum = schemas["log_many"]["parameters"]["properties"]["entries"]["items"]["properties"]["tool"]["enum"]
        assert set(enum) == set(app._BATCHABLE) and set(enum) <= set(app._BACKDATABLE)
