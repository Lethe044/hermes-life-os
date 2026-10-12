"""Regression tests: every dated tracker uses the user's LOCAL day.

Before v1.39.0 the writers stamped entries with the local date while about a
dozen readers computed "today" and "the last N days" in UTC. Whenever the
local date and the UTC date differ, a dose logged today did not count towards
today's streak and an expense logged just after midnight on the 1st landed in
the previous month's budget.

These tests pin the clock with clock.now, so they exercise the problem on any
machine in any time zone, not only on a machine that happens to be in UTC+3.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

DEMO = Path(__file__).parent.parent / "demo"
sys.path.insert(0, str(DEMO))

import clock  # noqa: E402 - needs the demo/ path set up above


def freeze(monkeypatch, *args):
    when = datetime(*args)
    monkeypatch.setattr(clock, "now", lambda: when)
    return when


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """tools.py plus a pristine copy of every demo module, with HOME in a temp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None) or ""
        if path.startswith(str(DEMO)) and name != "clock":
            del sys.modules[name]
    import tools
    importlib.reload(tools)
    import storage
    storage.set_active_profile(None)
    return tools


# 2026-11-01 00:30 local: in UTC+3 it is still Oct 31 in UTC
JUST_AFTER_MIDNIGHT = (2026, 11, 1, 0, 30)
# 2026-10-31 22:00 local: in UTC-8 it is already Nov 1 in UTC
LATE_EVENING = (2026, 10, 31, 22, 0)


class TestMedication:
    def test_dose_logged_now_counts_for_todays_streak(self, app, monkeypatch):
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        app.dispatch_tool("log_medication", {"name": "vitamin d"})
        out = app.dispatch_tool("get_medication_streak", {"med_name": "vitamin d"})
        assert "current streak 1 day" in out

    def test_multi_day_streak_ends_on_the_local_day(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_medication([{"date": d, "name": "vitamin d", "taken": True}
                                 for d in ("2026-10-30", "2026-10-31", "2026-11-01")])
        import medication_streak
        assert medication_streak.compute_medication_streak("vitamin d")["current_streak"] == 3

    def test_evening_in_the_americas(self, app, monkeypatch):
        freeze(monkeypatch, *LATE_EVENING)
        app.dispatch_tool("log_medication", {"name": "vitamin d"})
        import medication_streak
        assert medication_streak.compute_medication_streak("vitamin d")["current_streak"] == 1

    def test_longest_streak_counts_the_local_today(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_medication([{"date": d, "name": "x", "taken": True} for d in ("2026-10-31", "2026-11-01")])
        import medication_streak
        assert medication_streak.compute_medication_streak("x")["longest_streak"] == 2


class TestWorkout:
    def test_streak_includes_a_workout_logged_now(self, app, monkeypatch):
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        app.dispatch_tool("log_workout", {"workout_type": "run", "duration_min": 30})
        out = app.dispatch_tool("get_workout_summary", {"days": 1})
        assert "Current daily workout streak: 1 day" in out

    def test_this_week_count_uses_the_local_day(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        # exactly 7 local days ago is inside the window, 8 is outside
        storage.save_fitness([{"date": "2026-10-25", "type": "run", "duration": 10},
                              {"date": "2026-10-24", "type": "run", "duration": 10}])
        out = app.dispatch_tool("log_workout", {"workout_type": "run", "duration_min": 30})
        assert "This week: 2 workout(s)" in out


class TestHydration:
    def test_goal_streak_counts_the_local_today(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_hydration({"today": 2, "goal": 2, "last_date": "2026-11-01",
                                "log": [{"date": "2026-11-01", "glasses": 2},
                                        {"date": "2026-10-31", "glasses": 2}]})
        import hydration_summary
        assert hydration_summary.compute_hydration_summary(7)["current_goal_streak"] == 2


class TestBudgets:
    def test_expense_after_midnight_on_the_1st_counts_for_the_new_month(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        app.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        storage.save_spending([{"date": "2026-10-31", "category": "food", "amount": 500}])
        app.dispatch_tool("log_expense", {"amount": 30, "category": "food"})
        out = app.dispatch_tool("get_budget_status", {})
        assert "30.0 / 100" in out
        assert "500" not in out

    def test_expense_late_on_the_last_day_stays_in_the_old_month(self, app, monkeypatch):
        freeze(monkeypatch, *LATE_EVENING)
        app.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        app.dispatch_tool("log_expense", {"amount": 40, "category": "food"})
        assert "40.0 / 100" in app.dispatch_tool("get_budget_status", {})

    def test_forecast_uses_the_local_day_of_month(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, 2026, 10, 10, 0, 30)
        app.dispatch_tool("set_budget", {"category": "food", "limit": 300})
        storage.save_spending([{"date": "2026-10-04", "category": "food", "amount": 100}])
        import budgets
        r = budgets.compute_budget_forecast()[0]
        assert r["days_left"] == 21
        assert r["projected"] == 310.0

    def test_unbudgeted_and_suggestions_use_the_local_month(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_spending([{"date": "2026-10-31", "category": "gifts", "amount": 90},
                               {"date": "2026-11-01", "category": "fun", "amount": 20}])
        import budgets
        assert [c["category"] for c in budgets.compute_unbudgeted_spending()["categories"]] == ["fun"]
        s = budgets.compute_budget_suggestions(1, 0)
        assert s["months"] == ["2026-10"]
        assert [x["category"] for x in s["suggestions"]] == ["gifts"]


class TestWindows:
    def test_spending_trends_boundary(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_spending([{"date": "2026-10-31", "category": "a", "amount": 10},
                               {"date": "2026-10-30", "category": "a", "amount": 7}])
        import spending_trends
        a = spending_trends.compute_spending_trends(1)["categories"]["a"]
        assert (a["current"], a["previous"]) == (10.0, 7.0)

    def test_stress_summary_window(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_mental([{"date": "2026-10-30", "score": 9}, {"date": "2026-10-31", "score": 3}])
        import stress_summary
        r = stress_summary.compute_stress_summary(1)
        assert r["total_entries"] == 1
        assert r["avg_score"] == 3.0

    def test_meal_social_focus_meditation_windows(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_nutrition([{"date": "2026-10-30", "food": "old", "calories": 100},
                                {"date": "2026-10-31", "food": "new", "calories": 200}])
        storage.save_focus([{"date": "2026-10-30", "duration": 10, "task": "a", "quality": 5, "completed": True},
                            {"date": "2026-10-31", "duration": 20, "task": "b", "quality": 5, "completed": True}])
        import meal_summary, focus_summary
        assert meal_summary.compute_meal_summary(1)["total_meals"] == 1
        assert focus_summary.compute_focus_summary(1)["total_sessions"] == 1

    def test_weekly_health_report_window(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_sleep([{"date": "2026-10-24", "hours": 4, "quality": 3},
                            {"date": "2026-10-25", "hours": 8, "quality": 9}])
        out = app.dispatch_tool("get_weekly_health_report", {})
        assert "8" in out

    def test_reading_pace_finish_date(self, app, monkeypatch):
        import storage
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        storage.save_reading([{"date": "2026-10-30", "title": "Dune", "pages": 50, "total_pages": 350, "minutes": 60},
                              {"date": "2026-10-31", "title": "Dune", "pages": 50, "total_pages": 350, "minutes": 60}])
        import reading_pace
        r = reading_pace.compute_reading_pace("Dune")
        assert r["estimated_finish_date"] is not None
        assert r["estimated_finish_date"] >= "2026-11-01"


class TestDailyPrompt:
    def test_default_prompt_follows_the_local_day(self, app, monkeypatch):
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        import prompts
        assert prompts.get_daily_prompt() == prompts.get_daily_prompt("2026-11-01")


class TestDayStartHour:
    def test_night_owl_entry_counts_for_the_previous_day(self, app, monkeypatch):
        import storage
        monkeypatch.setenv(clock.DAY_START_ENV, "4")
        freeze(monkeypatch, 2026, 11, 1, 1, 30)
        app.dispatch_tool("log_expense", {"amount": 25, "category": "food"})
        app.dispatch_tool("log_medication", {"name": "melatonin"})
        assert storage.load_spending()[0]["date"] == "2026-10-31"
        assert storage.load_medication()[0]["date"] == "2026-10-31"

    def test_budget_month_follows_the_shifted_day(self, app, monkeypatch):
        monkeypatch.setenv(clock.DAY_START_ENV, "4")
        freeze(monkeypatch, 2026, 11, 1, 1, 30)
        app.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        app.dispatch_tool("log_expense", {"amount": 25, "category": "food"})
        assert "25.0 / 100" in app.dispatch_tool("get_budget_status", {})

    def test_after_the_boundary_it_is_the_new_day(self, app, monkeypatch):
        import storage
        monkeypatch.setenv(clock.DAY_START_ENV, "4")
        freeze(monkeypatch, 2026, 11, 1, 4, 0)
        app.dispatch_tool("log_expense", {"amount": 25, "category": "food"})
        assert storage.load_spending()[0]["date"] == "2026-11-01"


WRITERS = [
    ("log_meal", {"meal_time": "lunch", "food": "soup"}, "nutrition"),
    ("log_sleep", {"hours": 7, "quality": 7}, "sleep"),
    ("log_workout", {"workout_type": "run", "duration_min": 20}, "fitness"),
    ("log_stress", {"score": 4}, "mental"),
    ("log_meditation", {"duration_min": 10}, "mental"),
    ("log_gratitude", {"items": ["tea"]}, "mental"),
    ("log_focus_session", {"duration_min": 25, "task": "write"}, "focus"),
    ("log_expense", {"amount": 5}, "spending"),
    ("log_social_interaction", {"with_who": "Sam", "quality": 8}, "social"),
    ("log_substance", {"substance": "coffee", "amount": 1}, "substance"),
    ("log_reading", {"title": "Dune"}, "reading"),
    ("log_medication", {"name": "vitamin d"}, "medication"),
]


class TestEveryWriterUsesTheLocalDay:
    @pytest.mark.parametrize("tool,args,store", WRITERS, ids=[w[0] for w in WRITERS])
    @pytest.mark.parametrize("when", [JUST_AFTER_MIDNIGHT, LATE_EVENING], ids=["after_midnight", "late_evening"])
    def test_entry_is_dated_with_the_local_day(self, app, monkeypatch, tool, args, store, when):
        import storage
        freeze(monkeypatch, *when)
        app.dispatch_tool(tool, args)
        expected = datetime(*when).strftime("%Y-%m-%d")
        entries = storage.load_store(store)
        assert entries and entries[-1]["date"] == expected

    @pytest.mark.parametrize("when", [JUST_AFTER_MIDNIGHT, LATE_EVENING], ids=["after_midnight", "late_evening"])
    def test_hydration_log_and_counter(self, app, monkeypatch, when):
        import storage
        freeze(monkeypatch, *when)
        app.dispatch_tool("log_hydration", {"glasses": 2})
        h = storage.load_hydration()
        expected = datetime(*when).strftime("%Y-%m-%d")
        assert h["log"][-1]["date"] == expected
        assert h["last_date"] == expected

    def test_new_reminders_are_stamped_with_the_local_day(self, app, monkeypatch):
        freeze(monkeypatch, *JUST_AFTER_MIDNIGHT)
        import reminders
        assert reminders.create_reminder("x")["created"] == "2026-11-01"


class TestSourceGuards:
    """Cheap tripwires so a future change cannot quietly reintroduce the mix-up."""

    DATED_READERS = ["budgets", "focus_summary", "gratitude_recap", "hydration_summary", "meal_summary",
                     "medication_streak", "meditation_summary", "reading_pace", "social_insights",
                     "spending_trends", "stress_summary", "workout_summary", "prompts"]

    @pytest.mark.parametrize("module", DATED_READERS)
    def test_dated_readers_never_use_utc(self, module):
        assert "utcnow" not in (DEMO / f"{module}.py").read_text(encoding="utf-8")

    def test_tools_writers_never_use_the_raw_system_date(self):
        src = (DEMO / "tools.py").read_text(encoding="utf-8")
        assert 'time.strftime("%Y-%m-%d")' not in src

    def test_tools_reads_utc_only_for_the_memory_based_on_this_day(self):
        src = (DEMO / "tools.py").read_text(encoding="utf-8")
        assert src.count("utcnow") == 1

    def test_reminders_stamp_with_the_clock(self):
        assert 'time.strftime("%Y-%m-%d")' not in (DEMO / "reminders.py").read_text(encoding="utf-8")
