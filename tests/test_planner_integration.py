"""Planner integration: proactive nudges, doctor planner check, clock helpers, batching."""

from __future__ import annotations

from datetime import date, datetime

import pytest


class TestClockHelpers:
    @pytest.mark.parametrize("text,expected", [("2026-10-13", date(2026, 10, 13)), ("2026-1-5", date(2026, 1, 5)),
                                               (" 2026-02-28 ", date(2026, 2, 28))])
    def test_parse_day(self, planner, text, expected):
        import clock
        assert clock.parse_day(text) == expected

    @pytest.mark.parametrize("bad", ["", "soon", "2026-02-30", "13-01", None, 5, "2026/01/01"])
    def test_parse_day_rejects(self, planner, bad):
        import clock
        with pytest.raises(ValueError):
            clock.parse_day(bad)

    @pytest.mark.parametrize("start,months,expected", [
        (date(2026, 1, 31), 1, date(2026, 2, 28)), (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 12, 15), 1, date(2027, 1, 15)), (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2026, 3, 31), -1, date(2026, 2, 28)), (date(2026, 1, 15), 12, date(2027, 1, 15)),
        (date(2026, 1, 15), 0, date(2026, 1, 15)), (date(2026, 1, 15), -13, date(2024, 12, 15)),
        (date(2026, 10, 31), 2, date(2026, 12, 31)), (date(2026, 8, 31), 4, date(2026, 12, 31))])
    def test_add_months(self, planner, start, months, expected):
        import clock
        assert clock.add_months(start, months) == expected


class TestNudges:
    def test_nothing(self, planner):
        import nudges
        assert nudges._planner_nudges() == []

    def test_each_source(self, planner):
        import nudges
        planner.dispatch_tool("add_task", {"text": "old", "due": "2026-10-01"})
        assert any("old" in n for n in nudges._planner_nudges())

    def test_renewal(self, planner):
        import nudges
        planner.dispatch_tool("add_subscription", {"name": "Netflix", "amount": 15, "next_date": "2026-10-14"})
        assert any("Netflix" in n for n in nudges._planner_nudges())

    def test_birthday(self, planner):
        import nudges
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        assert any("Ayse" in n for n in nudges._planner_nudges())

    def test_capped(self, planner):
        import nudges
        planner.dispatch_tool("add_task", {"text": "old", "due": "2026-10-01"})
        planner.dispatch_tool("add_subscription", {"name": "Netflix", "amount": 15, "next_date": "2026-10-14"})
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        assert len(nudges._planner_nudges()) == nudges.MAX_PLANNER_NUDGES == 2

    def test_a_failing_source_does_not_block_the_others(self, planner, monkeypatch):
        import nudges, tasks
        planner.dispatch_tool("add_person", {"name": "Ayse", "birthday": "10-14"})
        monkeypatch.setattr(tasks, "overdue_nudge", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert any("Ayse" in n for n in nudges._planner_nudges())

    def test_all_failing(self, planner, monkeypatch):
        import nudges, tasks, subscriptions, people
        for mod, fn in ((tasks, "overdue_nudge"), (subscriptions, "renewal_nudge"), (people, "nudges")):
            monkeypatch.setattr(mod, fn, lambda *a, **k: 1 / 0)
        assert nudges._planner_nudges() == []

    def test_generate_nudges_includes_them(self, planner):
        import nudges
        planner.dispatch_tool("add_task", {"text": "old", "due": "2026-10-01"})
        assert any("old" in n for n in nudges.generate_nudges())


class TestDoctorPlanner:
    def check(self, planner):
        import doctor
        return doctor.check_planner_data()

    def test_clean(self, planner):
        planner.dispatch_tool("add_task", {"text": "x", "due": "today"})
        planner.dispatch_tool("add_person", {"name": "A", "birthday": "10-14"})
        planner.dispatch_tool("log_body_metric", {"metric": "weight", "value": 80})
        planner.dispatch_tool("add_subscription", {"name": "N", "amount": 5, "next_date": "2026-11-01"})
        f = self.check(planner)
        assert [x["level"] for x in f] == ["ok"]

    def test_empty_is_ok(self, planner):
        assert [x["level"] for x in self.check(planner)] == ["ok"]

    def _levels_for(self, planner, store, rows, area):
        import storage
        storage.save_store(store, rows)
        return [x for x in self.check(planner) if x["area"] == area and x["level"] == "warn"]

    def test_task_with_bad_due(self, planner):
        w = self._levels_for(planner, "tasks", [{"id": "a", "text": "t", "due": "banana", "done": False}], "tasks")
        assert len(w) == 1 and "1 open task" in w[0]["message"]

    def test_done_task_with_bad_due_is_ignored(self, planner):
        assert not self._levels_for(planner, "tasks", [{"id": "a", "text": "t", "due": "banana", "done": True}], "tasks")

    def test_subscription_problems(self, planner):
        rows = [{"id": "a", "name": "x", "next_date": "bad", "cycle": "monthly", "amount": 5, "active": True},
                {"id": "b", "name": "y", "next_date": "2026-11-01", "cycle": "daily", "amount": 5},
                {"id": "c", "name": "z", "next_date": "2026-11-01", "cycle": "monthly", "amount": 0},
                {"id": "d", "name": "off", "next_date": "bad", "cycle": "monthly", "amount": 5, "active": False}]
        w = self._levels_for(planner, "subscriptions", rows, "subscriptions")
        assert len(w) == 1 and w[0]["message"].startswith("3 active")

    @pytest.mark.parametrize("bday,count", [("13-45", 1), ("10-14", 0), ("1990-10-14", 0), ("1990-13-01", 1), ("02-29", 0)])
    def test_birthdays(self, planner, bday, count):
        w = self._levels_for(planner, "people", [{"id": "a", "name": "A", "birthday": bday}], "people")
        assert len(w) == count

    def test_body_rows(self, planner):
        rows = [{"id": "a", "date": "2026-10-01", "metric": "weight", "value": 80, "unit": "kg"},
                {"id": "b", "date": "2026-10-01", "metric": "mystery", "value": 80},
                {"id": "c", "date": "2026-10-01", "metric": "weight", "value": "x"},
                {"id": "d", "date": "nope", "metric": "weight", "value": 80},
                {"type": "goal", "metric": "weight", "target": 70}]
        w = self._levels_for(planner, "body", rows, "body")
        assert len(w) == 1 and w[0]["message"].startswith("3 body")

    def test_duplicate_ids(self, planner):
        w = self._levels_for(planner, "tasks", [{"id": "a", "text": "1"}, {"id": "a", "text": "2"}], "tasks")
        assert len(w) == 1 and "shared" in w[0]["message"]

    def test_read_only(self, planner):
        import storage
        storage.save_store("tasks", [{"text": "no id", "due": "2026-10-13"}])
        self.check(planner)
        assert "id" not in storage.load_store("tasks")[0]

    def test_malformed_stores_do_not_crash(self, planner):
        import storage
        for name in ("tasks", "subscriptions", "people", "body"):
            storage.save_store(name, {"not": "a list"})
        assert [x["level"] for x in self.check(planner)] == ["ok"]
        for name in ("tasks", "subscriptions", "people", "body"):
            storage.save_store(name, ["junk", None, 5])
        assert [x["level"] for x in self.check(planner)] == ["ok"]

    def test_run_checks_includes_it(self, planner):
        import doctor, storage
        storage.save_store("tasks", [{"id": "a", "text": "t", "due": "banana"}])
        assert any(f["area"] == "tasks" and f["level"] == "warn" for f in doctor.run_checks())


class TestBatching:
    def test_log_many_body_metrics(self, planner):
        out = planner.dispatch_tool("log_many", {"entries": [
            {"tool": "log_body_metric", "args": {"metric": "weight", "value": 80, "date": "2026-10-10"}},
            {"tool": "log_body_metric", "args": {"metric": "resting_hr", "value": 60}}]})
        import storage
        rows = storage.load_store("body")
        assert len(rows) == 2 and {r["date"] for r in rows} == {"2026-10-10", "2026-10-13"}, out

    def test_backdated_journal_entry(self, planner):
        planner.dispatch_tool("log_body_metric", {"metric": "weight", "value": 79, "date": "2026-10-09"})
        import storage
        assert any("79" in str(m) for m in storage.get_all_memory())

    def test_unsupported_planner_tool_in_log_many_is_refused(self, planner):
        out = planner.dispatch_tool("log_many", {"entries": [{"tool": "add_task", "args": {"text": "x"}}]})
        import storage
        assert storage.load_store("tasks") == [], out


class TestBackupRoundTrip:
    @pytest.mark.parametrize("store", ["tasks", "subscriptions", "people", "body"])
    def test_store_registered(self, planner, store):
        import storage
        assert store in storage.DATA_STORES
