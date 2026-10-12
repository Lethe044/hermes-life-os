"""Backdating: the 13 log tools accept an optional `date` (YYYY-MM-DD)."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

DEMO = Path(__file__).parent.parent / "demo"
sys.path.insert(0, str(DEMO))

import clock  # noqa: E402 - needs the demo/ path set up above

NOW = (2026, 10, 12, 9, 0)

# tool -> (arguments, storage loader name, expected store key for the date)
CASES = {
    "log_meal": ({"meal_time": "lunch", "food": "soup", "calories": 300}, "load_nutrition"),
    "log_sleep": ({"hours": 7, "quality": 6}, "load_sleep"),
    "log_workout": ({"workout_type": "run", "duration_min": 30}, "load_fitness"),
    "log_stress": ({"score": 4, "trigger": "deadline"}, "load_mental"),
    "log_meditation": ({"duration_min": 10}, "load_mental"),
    "log_gratitude": ({"items": ["sun"]}, "load_mental"),
    "log_focus_session": ({"duration_min": 25, "task": "write"}, "load_focus"),
    "log_expense": ({"amount": 12.5, "category": "food"}, "load_spending"),
    "log_social_interaction": ({"with_who": "Sam", "quality": 8}, "load_social"),
    "log_substance": ({"substance": "coffee", "amount": 2, "unit": "cups"}, "load_substance"),
    "log_reading": ({"title": "Dune", "minutes": 20, "pages": 10}, "load_reading"),
    "log_medication": ({"name": "vitamin d"}, "load_medication"),
}


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None) or ""
        if path.startswith(str(DEMO)) and name != "clock":
            del sys.modules[name]
    when = datetime(*NOW)
    monkeypatch.setattr(clock, "now", lambda: when)
    import tools
    importlib.reload(tools)
    import storage
    storage.set_active_profile(None)
    return tools


def stored(loader):
    import storage
    return getattr(storage, loader)()


class TestResolveEntryDate:
    @pytest.fixture(autouse=True)
    def _freeze(self, monkeypatch):
        when = datetime(*NOW)
        monkeypatch.setattr(clock, "now", lambda: when)

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_missing_means_today(self, value):
        assert clock.resolve_entry_date(value) == "2026-10-12"

    def test_valid_past_date(self):
        assert clock.resolve_entry_date("2026-10-11") == "2026-10-11"

    def test_today_is_allowed(self):
        assert clock.resolve_entry_date("2026-10-12") == "2026-10-12"

    def test_normalizes_unpadded_dates(self):
        assert clock.resolve_entry_date(" 2026-9-5 ") == "2026-09-05"

    def test_future_rejected(self):
        with pytest.raises(ValueError, match="in the future"):
            clock.resolve_entry_date("2026-10-13")

    def test_oldest_allowed_and_one_too_old(self):
        assert clock.resolve_entry_date("2025-10-12") == "2025-10-12"
        with pytest.raises(ValueError, match="more than 365 days"):
            clock.resolve_entry_date("2025-10-11")

    @pytest.mark.parametrize("value", ["yesterday", "2026-13-01", "2026-02-30", "10/11/2026", "20261011"])
    def test_garbage_rejected(self, value):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            clock.resolve_entry_date(value)

    @pytest.mark.parametrize("value", [20261011, 1.5, True, ["2026-10-11"], {"a": 1}])
    def test_non_strings_rejected(self, value):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            clock.resolve_entry_date(value)

    def test_respects_the_day_start_hour(self, monkeypatch):
        monkeypatch.setenv("LIFE_OS_DAY_START_HOUR", "10")
        # 09:00 on the 12th is still the 11th for this user, so the 12th is "future"
        with pytest.raises(ValueError, match="in the future"):
            clock.resolve_entry_date("2026-10-12")
        assert clock.resolve_entry_date(None) == "2026-10-11"


@pytest.mark.parametrize("tool", sorted(CASES))
class TestEveryLogTool:
    def test_default_is_today(self, app, tool):
        args, loader = CASES[tool]
        app.dispatch_tool(tool, dict(args))
        assert stored(loader)[-1]["date"] == "2026-10-12"

    def test_backdated(self, app, tool):
        args, loader = CASES[tool]
        out = app.dispatch_tool(tool, {**args, "date": "2026-10-09"})
        assert not out.startswith("Not logged")
        assert stored(loader)[-1]["date"] == "2026-10-09"

    @pytest.mark.parametrize("bad", ["2026-10-13", "nonsense", "2020-01-01"])
    def test_bad_date_writes_nothing(self, app, tool, bad):
        import storage
        args, loader = CASES[tool]
        out = app.dispatch_tool(tool, {**args, "date": bad})
        assert out.startswith("Not logged: ")
        assert stored(loader) == []
        assert storage.get_all_memory() == []

    def test_schema_documents_date(self, app, tool):
        schemas = {t["function"]["name"]: t["function"] for t in app.TOOLS}
        prop = schemas[tool]["parameters"]["properties"]["date"]
        assert prop["type"] == "string"
        assert "YYYY-MM-DD" in prop["description"]
        assert "date" not in schemas[tool]["parameters"].get("required", [])


class TestMemoryJournalStamp:
    @pytest.mark.parametrize("tool", [t for t in sorted(CASES) if t != "log_medication"])
    def test_backdated_entry_is_stamped_on_its_day(self, app, tool):
        import storage
        args, _ = CASES[tool]
        app.dispatch_tool(tool, {**args, "date": "2026-10-09"})
        assert storage.get_all_memory()[-1]["timestamp"] == "2026-10-09T12:00:00Z"

    def test_entry_for_today_keeps_the_real_timestamp(self, app):
        import storage
        app.dispatch_tool("log_meal", {**CASES["log_meal"][0], "date": "2026-10-12"})
        assert storage.get_all_memory()[-1]["timestamp"] != "2026-10-12T12:00:00Z"

    def test_memory_entry_has_no_date_field_leak(self, app):
        import storage
        app.dispatch_tool("log_meal", {**CASES["log_meal"][0], "date": "2026-10-09"})
        assert "date" not in storage.get_all_memory()[-1]


class TestLabels:
    def test_meal_total_is_for_the_logged_day(self, app):
        app.dispatch_tool("log_meal", {**CASES["log_meal"][0], "date": "2026-10-09"})
        out = app.dispatch_tool("log_meal", {"meal_time": "dinner", "food": "pasta", "calories": 500,
                                              "date": "2026-10-09"})
        assert "Total for 2026-10-09: 800 calories across 2 meals." in out
        assert "Today" not in out

    def test_meal_total_today(self, app):
        out = app.dispatch_tool("log_meal", dict(CASES["log_meal"][0]))
        assert "Today's total: 300 calories across 1 meals." in out

    def test_focus_labels(self, app):
        past = app.dispatch_tool("log_focus_session", {**CASES["log_focus_session"][0], "date": "2026-10-09"})
        now = app.dispatch_tool("log_focus_session", dict(CASES["log_focus_session"][0]))
        assert "Deep work on 2026-10-09: 25 minutes across 1 sessions" in past
        assert "Today's deep work: 25 minutes across 1 sessions" in now

    def test_expense_labels(self, app):
        app.dispatch_tool("log_expense", {"amount": 10, "category": "food"})
        past = app.dispatch_tool("log_expense", {"amount": 5, "category": "food", "date": "2026-10-09"})
        assert "Total for 2026-10-09: 5.0" in past
        now = app.dispatch_tool("log_expense", {"amount": 1, "category": "food"})
        assert "Today's total: 11.0" in now


class TestHydration:
    def test_backdated_does_not_touch_the_todays_counter(self, app):
        import storage
        app.dispatch_tool("log_hydration", {"glasses": 3})
        out = app.dispatch_tool("log_hydration", {"glasses": 2, "date": "2026-10-09"})
        h = storage.load_hydration()
        assert h["today"] == 3 and h["last_date"] == "2026-10-12"
        assert [e["date"] for e in h["log"]] == ["2026-10-12", "2026-10-09"]
        assert "2026-10-09: 2/8 glasses" in out

    def test_backdated_total_adds_up_per_day(self, app):
        app.dispatch_tool("log_hydration", {"glasses": 2, "date": "2026-10-09"})
        out = app.dispatch_tool("log_hydration", {"glasses": 3, "date": "2026-10-09"})
        assert "2026-10-09: 5/8 glasses" in out

    def test_backdated_memory_entry_records_that_days_total(self, app):
        import storage
        app.dispatch_tool("log_hydration", {"glasses": 2, "date": "2026-10-09"})
        app.dispatch_tool("log_hydration", {"glasses": 3, "date": "2026-10-09"})
        assert storage.get_all_memory()[-1]["glasses"] == 5

    def test_backdated_first_log_does_not_reset_or_set_today(self, app):
        import storage
        app.dispatch_tool("log_hydration", {"glasses": 2, "date": "2026-10-09"})
        h = storage.load_hydration()
        assert h.get("today", 0) == 0
        assert h.get("last_date") != "2026-10-09"

    def test_today_still_works(self, app):
        out = app.dispatch_tool("log_hydration", {"glasses": 2})
        assert "Today: 2/8 glasses" in out

    def test_hydration_summary_sees_backdated_glasses(self, app):
        app.dispatch_tool("log_hydration", {"glasses": 4, "date": "2026-10-10"})
        out = app.dispatch_tool("get_hydration_summary", {"days": 7})
        assert "4" in out


class TestReadersSeeBackdatedEntries:
    def test_medication_streak_bridges_a_forgotten_day(self, app):
        app.dispatch_tool("log_medication", {"name": "vitamin d", "date": "2026-10-11"})
        app.dispatch_tool("log_medication", {"name": "vitamin d"})
        out = app.dispatch_tool("get_medication_streak", {"med_name": "vitamin d"})
        assert "current streak 2 day(s)" in out

    def test_expense_lands_in_its_own_month(self, app):
        app.dispatch_tool("log_expense", {"amount": 40, "category": "food", "date": "2026-09-30"})
        s = stored("load_spending")
        assert s[-1]["date"] == "2026-09-30"
        import budgets
        assert budgets._current_month_spent_by_category().get("food", 0) == 0

    def test_non_backdatable_tools_ignore_a_date_argument(self, app):
        # remember is free-form memory, not a dated tracker: `date` is just data
        import storage
        app.dispatch_tool("remember", {"type": "note", "content": "x", "date": "garbage"})
        assert storage.get_all_memory()[-1]["date"] == "garbage"


class TestSchemaConsistency:
    def test_exactly_the_backdatable_tools_have_a_date_property(self, app):
        with_date = {t["function"]["name"] for t in app.TOOLS
                     if "date" in t["function"]["parameters"].get("properties", {})
                     and t["function"]["parameters"]["properties"]["date"] == app._ENTRY_DATE_PROP}
        assert with_date == set(app._BACKDATABLE)

    def test_schemas_do_not_share_one_dict(self, app):
        props = [t["function"]["parameters"]["properties"]["date"] for t in app.TOOLS
                 if t["function"]["name"] in app._BACKDATABLE]
        assert len({id(p) for p in props}) == len(props)

    def test_schemas_are_json_serializable(self, app):
        json.dumps(app.TOOLS)
