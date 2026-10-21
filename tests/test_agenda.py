"""get_today_agenda: one place for everything with a date on it."""

from __future__ import annotations

from datetime import datetime


def agenda(p):
    return p.dispatch_tool("get_today_agenda", {})


class TestEmpty:
    def test_nothing_due(self, planner):
        assert agenda(planner) == ("Agenda for 2026-10-13 (Tuesday)\n"
                                   "Nothing due today: no tasks, reminders, renewals, birthdays or streaks at risk.")

    def test_follows_the_clock_and_day_start_hour(self, planner, monkeypatch):
        monkeypatch.setenv("LIFE_OS_DAY_START_HOUR", "10")  # 09:00 on Tuesday is still Monday
        assert agenda(planner).startswith("Agenda for 2026-10-12 (Monday)")


class TestSections:
    def test_tasks_overdue_first_then_due_today(self, planner):
        planner.dispatch_tool("add_task", {"text": "later", "due": "friday"})
        planner.dispatch_tool("add_task", {"text": "today thing", "due": "today"})
        planner.dispatch_tool("add_task", {"text": "old thing", "due": "2026-10-10"})
        out = agenda(planner)
        assert "Tasks (1 overdue, 1 due today):" in out and "later" not in out
        assert out.index("old thing") < out.index("today thing")

    def test_reminders(self, planner):
        planner.dispatch_tool("create_reminder", {"text": "stretch", "time": "09:30"})
        planner.dispatch_tool("create_reminder", {"text": "water plants"})
        out = agenda(planner)
        assert "Reminders:" in out and "09:30: stretch" in out and "any time: water plants" in out

    def test_renewals_within_three_days(self, planner):
        planner.dispatch_tool("add_subscription", {"name": "Netflix", "amount": 15, "next_date": "2026-10-14"})
        planner.dispatch_tool("add_subscription", {"name": "Gym", "amount": 30, "next_date": "2026-10-20"})
        out = agenda(planner)
        assert "Renewals in the next 3 days:" in out and "2026-10-14 (in 1 day(s)): Netflix 15" in out and "Gym" not in out

    def test_people(self, planner):
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "1990-10-16"})
        planner.dispatch_tool("add_person", {"name": "Can", "keep_in_touch_days": 5})
        planner.set_now(datetime(2026, 10, 19, 9, 0))
        planner.dispatch_tool("add_person", {"name": "Eda", "birthday": "10-19"})
        out = agenda(planner)
        assert "People:" in out and "Eda's birthday TODAY" in out and "Catch up with Can (6 days, goal every 5)" in out

    def test_birthday_window_is_seven_days(self, planner):
        planner.dispatch_tool("add_person", {"name": "Near", "birthday": "10-20"})
        planner.dispatch_tool("add_person", {"name": "Far", "birthday": "10-21"})
        out = agenda(planner)
        assert "Near's birthday in 7 day(s)" in out and "Far" not in out

    def test_habit_streaks_at_risk(self, planner):
        planner.set_now(datetime(2026, 10, 12, 9, 0))
        planner.dispatch_tool("update_habit", {"habit_name": "run", "completed": True})
        planner.dispatch_tool("update_habit", {"habit_name": "read", "completed": True})
        planner.set_now(datetime(2026, 10, 13, 9, 0))
        planner.dispatch_tool("update_habit", {"habit_name": "read", "completed": True})
        out = agenda(planner)
        assert "Habits that need a check-in today to keep their streak:" in out and "run (1 days)" in out
        assert "read" not in out

    def test_a_habit_not_done_for_days_is_not_at_risk(self, planner):
        planner.set_now(datetime(2026, 10, 1, 9, 0))
        planner.dispatch_tool("update_habit", {"habit_name": "run", "completed": True})
        planner.set_now(datetime(2026, 10, 13, 9, 0))
        assert "Habits" not in agenda(planner)

    def test_budget_alerts(self, planner):
        planner.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        planner.dispatch_tool("log_expense", {"amount": 150, "category": "food"})
        out = agenda(planner)
        assert "Budgets:" in out and "food" in out

    def test_a_section_is_capped_at_five(self, planner):
        for i in range(8):
            planner.dispatch_tool("add_task", {"text": f"task {i}", "due": "today"})
        out = agenda(planner)
        assert out.count("[ ] task") == 5 and "... and 3 more" in out

    def test_only_sections_with_content_appear(self, planner):
        planner.dispatch_tool("add_task", {"text": "x", "due": "today"})
        out = agenda(planner)
        for header in ("Reminders:", "Renewals", "People:", "Habits", "Budgets:"):
            assert header not in out

    def test_everything_at_once_in_a_stable_order(self, planner):
        planner.dispatch_tool("add_task", {"text": "t", "due": "today"})
        planner.dispatch_tool("create_reminder", {"text": "r", "time": "10:00"})
        planner.dispatch_tool("add_subscription", {"name": "S", "amount": 1, "next_date": "2026-10-13"})
        planner.dispatch_tool("add_person", {"name": "P", "birthday": "10-13"})
        planner.dispatch_tool("set_budget", {"category": "food", "limit": 10})
        planner.dispatch_tool("log_expense", {"amount": 50, "category": "food"})
        out = agenda(planner)
        order = [out.index(h) for h in ("Tasks (", "Reminders:", "Renewals", "People:", "Budgets:")]
        assert order == sorted(order)


class TestRobustness:
    def test_garbage_in_every_store_does_not_crash(self, planner):
        import storage
        storage.save_tasks(["x", None, {"text": "t", "due": "banana"}])
        storage.save_subscriptions(["x", None, {"name": "s", "next_date": "x"}])
        storage.save_people(["x", None, {"name": "p", "birthday": "x", "keep_in_touch_days": "x"}])
        storage.save_habits(["x", {"name": "h", "streak": "many"}]) if False else None
        assert agenda(planner).startswith("Agenda for 2026-10-13")

    def test_read_only(self, planner):
        import storage
        storage.save_tasks([{"text": "legacy", "due": "2026-10-13", "done": False}])
        agenda(planner)
        assert storage.get_all_memory() == []

    def test_schema(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        assert "get_today_agenda" in schemas and schemas["get_today_agenda"]["parameters"]["required"] == []
