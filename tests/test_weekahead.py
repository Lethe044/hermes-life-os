"""Week ahead: one calendar over everything with a date."""

from __future__ import annotations

import pytest


def d(p, _tool, **a):
    return p.dispatch_tool(_tool, a)


class TestBuild:
    def test_empty(self, planner):
        assert d(planner, "get_week_ahead") == "Week ahead: Tue 2026-10-13 to Mon 2026-10-19\nNothing planned for the next 7 days."

    def test_everything_in_date_order(self, planner):
        d(planner, "add_task", text="Pay rent", due="2026-10-14")
        d(planner, "add_task", text="Late one", due="2026-10-10")
        d(planner, "add_time_block", title="Deep work", start="09:00", end="10:00", date="2026-10-14")
        d(planner, "add_person", name="Ayse", birthday="1990-10-18")
        d(planner, "add_chore", name="Water plants", every="weekly", start="2026-10-15")
        d(planner, "add_expiry", name="Passport", date="2026-10-16")
        d(planner, "add_countdown", name="Exam", date="2026-10-17")
        d(planner, "add_trip", name="Rome", start="2026-10-17", end="2026-10-19")
        d(planner, "add_decision", title="Desk", review="2026-10-15")
        d(planner, "add_subscription", name="Netflix", amount=15, next_date="2026-10-16")
        d(planner, "add_debt", who="Ali", amount=50, direction="owe", due="2026-10-14")
        out = d(planner, "get_week_ahead")
        assert out.splitlines() == [
            "Week ahead: Tue 2026-10-13 to Mon 2026-10-19",
            "Overdue:", "  - Task: Late one (was due 2026-10-10)",
            "Wed 14 Oct:", "  - Task: Pay rent", "  - 09:00-10:00 Deep work", "  - Debt due: you owe Ali 50",
            "Thu 15 Oct:", "  - Chore: Water plants", "  - Review decision: Desk",
            "Fri 16 Oct:", "  - Renews: Netflix (15 monthly)", "  - Expires: Passport",
            "Sat 17 Oct:", "  - Countdown: Exam", "  - Trip starts: Rome",
            "Sun 18 Oct:", "  - Birthday: Ayse (turning 36)",
            "Mon 19 Oct:", "  - Trip ends: Rome",
            "Nothing planned: Tue 13"]

    def test_meals_and_done_blocks(self, planner):
        d(planner, "add_recipe", name="Soup", ingredients=["2 carrots"], servings=2)
        d(planner, "plan_meal", recipe="soup", slot="dinner", date="2026-10-15")
        d(planner, "add_time_block", title="Gym", start="07:00", end="08:00", date="2026-10-15")
        d(planner, "finish_time_block", block="gym")
        out = d(planner, "get_week_ahead")
        assert "Thu 15 Oct:\n  - Dinner: Soup" in out and "Gym" not in out

    def test_today_is_marked(self, planner):
        d(planner, "add_task", text="Now", due="today")
        assert "Tue 13 Oct (today):\n  - Task: Now" in d(planner, "get_week_ahead")

    def test_window_length(self, planner):
        d(planner, "add_task", text="Far", due="2026-10-25")
        assert "Far" not in d(planner, "get_week_ahead")
        out = d(planner, "get_week_ahead", days=14)
        assert out.startswith("14 days ahead: Tue 2026-10-13 to Mon 2026-10-26") and "Sun 25 Oct:\n  - Task: Far" in out
        assert d(planner, "get_week_ahead", days=1).splitlines()[0] == "Day ahead: Tue 2026-10-13 to Tue 2026-10-13"

    @pytest.mark.parametrize("days", [0, 15, -1, 2.5, True, "x"])
    def test_bad_days(self, planner, days):
        assert d(planner, "get_week_ahead", days=days) == "Cannot show the week ahead: days must be a whole number from 1 to 14."

    def test_long_days_are_cut(self, planner):
        for n in range(10):
            d(planner, "add_task", text=f"T{n}", due="2026-10-14")
        out = d(planner, "get_week_ahead")
        assert "  ... and 2 more" in out and out.count("Task: T") == 8

    def test_overdue_is_cut(self, planner):
        for n in range(10):
            d(planner, "add_task", text=f"L{n}", due="2026-10-01")
        out = d(planner, "get_week_ahead")
        assert "  ... and 2 more" in out and out.count("(was due 2026-10-01)") == 8

    def test_expired_documents_are_overdue(self, planner):
        d(planner, "add_expiry", name="Ins", date="2026-10-05")
        assert "Overdue:\n  - Expires: Ins (was due 2026-10-05)" in d(planner, "get_week_ahead")

    @pytest.mark.parametrize("module,attr", [("tasks", "list_tasks"), ("timeblocks", "day_plan"), ("people", "upcoming_birthdays"),
                                             ("chores", "listing"), ("expiries", "listing"), ("trips", "listing"),
                                             ("decisions", "due_for_review"), ("subscriptions", "upcoming"), ("debts", "due_soon"),
                                             ("countdowns", "within")])
    def test_a_failing_source_is_left_out(self, planner, monkeypatch, module, attr):
        mod = __import__(module)
        d(planner, "add_task", text="Keep me", due="2026-10-14")
        monkeypatch.setattr(mod, attr, lambda *a, **k: 1 / 0)
        out = d(planner, "get_week_ahead")
        assert out.startswith("Week ahead:") and (module == "tasks" or "Keep me" in out)

    def test_broken_stores_do_not_raise(self, planner):
        import storage
        storage.save_mealplan([{"date": 5, "name": "x"}, "junk"])
        storage.save_trips([{"id": "a", "start": "x", "end": "y"}, 7])
        storage.save_chores(["junk"])
        storage.save_expiries([{"date": None}])
        assert d(planner, "get_week_ahead").startswith("Week ahead:")
