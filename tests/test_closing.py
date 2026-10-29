"""The closing summary of a day or a week."""

from __future__ import annotations

from datetime import datetime

import pytest


def closing(p, **kw):
    return p.dispatch_tool("get_closing_summary", kw)


class TestDay:
    def test_nothing_at_all(self, planner):
        assert closing(planner) == ("Closing summary for Tuesday 2026-10-13\n"
                                    "Nothing recorded for today and nothing coming up tomorrow.")

    def test_full_day(self, planner):
        d = planner.dispatch_tool
        planner.set_now(datetime(2026, 10, 13, 21, 0))
        d("add_task", {"text": "Pay rent"}); d("complete_task", {"task": "rent"})
        d("add_task", {"text": "Call bank", "due": "today"}); d("add_task", {"text": "Old one", "due": "2026-10-01"})
        d("add_task", {"text": "File taxes", "due": "tomorrow"})
        d("add_time_block", {"title": "Deep work", "start": "09:00", "end": "10:00"}); d("finish_time_block", {"block": "deep"})
        d("add_time_block", {"title": "Gym", "start": "18:00", "end": "19:00"})
        d("add_time_block", {"title": "Planning", "start": "08:30", "end": "09:00", "date": "tomorrow"})
        d("log_meal", {"meal_time": "lunch", "food": "soup", "calories": 300}); d("log_hydration", {"glasses": 2})
        d("log_expense", {"amount": 25, "category": "food"}); d("log_income", {"amount": 100, "source": "gig"})
        d("add_recipe", {"name": "Omelette", "ingredients": ["2 eggs"]}); d("plan_meal", {"slot": "breakfast", "recipe": "omelette", "date": "tomorrow"})
        import storage
        storage.save_habits([{"name": "read", "streak": 4, "last_done": "2026-10-13"}, {"name": "walk", "streak": 6, "last_done": "2026-10-12"}])
        out = closing(planner).split("\n")
        assert out == [
            "Closing summary for Tuesday 2026-10-13",
            "Done today (1 task(s), 1 block(s), 1 habit(s)):",
            "  task: Pay rent", "  time block: Deep work", "  habit: read",
            "Logged today:", "  expenses 1, hydration 1, income 1, meals 1", "  spent 25, earned 100, net 75",
            "Still open:", "  1 overdue task(s)", "  due today, not done: Call bank", "  unfinished block: 18:00-19:00 Gym",
            "  habit streak at risk: walk (6 days)",
            "Tomorrow:", "  task: File taxes", "  1 time block(s), first 08:30 Planning", "  meal breakfast: Omelette"]

    def test_tomorrow_items(self, planner):
        d = planner.dispatch_tool
        d("add_countdown", {"name": "Exam", "date": "2026-10-14"}); d("add_countdown", {"name": "Later", "date": "2026-10-20"})
        d("add_trip", {"name": "Rome", "start": "2026-10-14", "end": "2026-10-16"})
        d("add_subscription", {"name": "Netflix", "amount": 10, "cycle": "monthly", "next_date": "2026-10-14"})
        d("add_person", {"name": "Ana", "birthday": "10-14"})
        import storage
        storage.save_reminders([{"id": "r", "text": "dentist", "time": "09:00", "date": "2026-10-14", "enabled": True},
                                {"id": "s", "text": "today only", "time": "09:00", "date": "2026-10-13", "enabled": True}])
        out = closing(planner)
        tomorrow = out.split("Tomorrow:\n")[1].split("\n")
        assert tomorrow == ["  reminder 09:00: dentist", "  renewal: Netflix", "  birthday: Ana", "  Exam: tomorrow (Wed 2026-10-14)",
                            "  trip starts: Rome"]

    def test_long_sections_are_cut(self, planner):
        for i in range(8):
            planner.dispatch_tool("add_task", {"text": f"task {i}", "due": "tomorrow"})
        out = closing(planner)
        assert out.count("  task: task") == 5 and "  ... and 3 more" in out

    def test_a_broken_store_only_loses_its_section(self, planner):
        import storage
        planner.dispatch_tool("add_task", {"text": "File taxes", "due": "tomorrow"})
        planner.dispatch_tool("add_time_block", {"title": "Deep work", "start": "09:00", "end": "10:00"})
        storage.save_timeblocks("garbage"); storage.save_habits({"x": 1})
        out = closing(planner)
        assert "task: File taxes" in out and "Deep work" not in out

    def test_night_owl_day(self, planner, monkeypatch):
        monkeypatch.setenv("LIFE_OS_DAY_START_HOUR", "4")
        planner.set_now(datetime(2026, 10, 14, 1, 30))       # still "Tuesday" for this user
        assert closing(planner).startswith("Closing summary for Tuesday 2026-10-13")


class TestWeek:
    def test_empty(self, planner):
        assert closing(planner, period="week") == ("Closing summary for the week 2026-10-07 to 2026-10-13\n"
                                                   "Nothing recorded this week and nothing coming up.")

    def test_full_week(self, planner):
        d = planner.dispatch_tool
        for text in ("a", "b"):
            d("add_task", {"text": text}); d("complete_task", {"task": text})
        d("add_time_block", {"title": "Deep work", "start": "09:00", "end": "11:00", "date": "2026-10-09"})
        d("finish_time_block", {"block": "deep", "date": "2026-10-09"})
        d("log_meal", {"meal_time": "lunch", "food": "soup", "calories": 300, "date": "2026-10-10"})
        d("log_meal", {"meal_time": "dinner", "food": "pasta", "calories": 600, "date": "2026-10-11"})
        d("log_sleep", {"hours": 7, "date": "2026-10-11"})
        d("log_expense", {"amount": 40, "date": "2026-10-08"}); d("log_expense", {"amount": 10, "date": "2026-10-01"})
        d("log_income", {"amount": 1000, "date": "2026-10-12"})
        d("log_symptom", {"symptom": "headache", "severity": 3, "date": "2026-10-10"}); d("log_symptom", {"symptom": "headache", "severity": 5, "date": "2026-10-12"})
        d("add_objective", {"name": "Ship", "period": "week", "key_results": [{"name": "t", "target": 10}]})
        d("add_task", {"text": "Late", "due": "2026-10-01"}); d("add_task", {"text": "Next week", "due": "2026-10-15"})
        d("add_time_block", {"title": "Plan", "start": "09:00", "end": "10:30", "date": "2026-10-14"})
        d("add_trip", {"name": "Rome", "start": "2026-10-16"})
        d("add_countdown", {"name": "Exam", "date": "2026-10-18"})
        out = closing(planner, period="week")
        assert out.split("\n") == [
            "Closing summary for the week 2026-10-07 to 2026-10-13",
            "Done:", "  2 task(s) finished", "  1 time block(s) done, 2.0 h",
            "Logged:", "  entries on 4 of 7 days: meals 2, symptoms 2, sleep 1, income 1, expenses 1",
            "Money:", "  spent 40, earned 1,000, net 960",
            "Symptoms (a personal log, not medical advice):", "  headache 2x",
            "Objectives:", "  Ship: 0% done, behind",
            "Still open:", "  1 overdue task(s)",
            "Next 7 days:", "  1 task(s) due", "  1 time block(s), 1.5 h planned", "  trip: Rome starts 2026-10-16", "  countdowns: Exam"]

    def test_bad_period(self, planner):
        assert closing(planner, period="month") == "Cannot summarize: period must be day or week."
        assert closing(planner, period=5) == "Cannot summarize: period must be day or week."

    def test_default_and_case(self, planner):
        assert closing(planner, period=None).startswith("Closing summary for Tuesday")
        assert closing(planner, period=" WEEK ").startswith("Closing summary for the week")

    def test_it_is_read_only(self, planner):
        import storage
        planner.dispatch_tool("add_task", {"text": "x", "due": "tomorrow"})
        before = {n: storage.load_store(n) for n in storage.data_store_names()}
        closing(planner); closing(planner, period="week")
        assert {n: storage.load_store(n) for n in storage.data_store_names()} == before
