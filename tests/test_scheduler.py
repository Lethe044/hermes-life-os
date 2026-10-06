"""Tests for the pure cron-style scheduling logic (demo/scheduler.py)."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

from scheduler import ScheduleEntry, due_entries, default_schedule, run_scheduler


class TestScheduleEntry:
    def test_id_daily(self):
        e = ScheduleEntry("07:00", "morning")
        assert e.id == "morning@07:00[daily]"

    def test_id_with_days(self):
        e = ScheduleEntry("08:00", "weekly", ["Monday"])
        assert e.id == "weekly@08:00[Monday]"


class TestDefaultSchedule:
    def test_has_six_entries(self):
        sched = default_schedule()
        assert len(sched) == 6

    def test_modes_match_daily_rhythm(self):
        sched = default_schedule()
        modes = {e.mode for e in sched}
        assert modes == {"morning", "checkin", "evening", "weekly", "nudge_check", "backup"}

    def test_backup_is_after_nudge_check(self):
        sched = default_schedule()
        backup = next(e for e in sched if e.mode == "backup")
        assert backup.time_str == "20:30"

    def test_weekly_is_monday_only(self):
        sched = default_schedule()
        weekly = next(e for e in sched if e.mode == "weekly")
        assert weekly.days == ["Monday"]


class TestDueEntries:
    def test_matches_exact_time(self):
        sched = [ScheduleEntry("07:00", "morning")]
        now = datetime(2026, 7, 17, 7, 0)
        due = due_entries(sched, now, {})
        assert len(due) == 1
        assert due[0].mode == "morning"

    def test_no_match_different_minute(self):
        sched = [ScheduleEntry("07:00", "morning")]
        now = datetime(2026, 7, 17, 7, 1)
        assert due_entries(sched, now, {}) == []

    def test_no_match_different_hour(self):
        sched = [ScheduleEntry("07:00", "morning")]
        now = datetime(2026, 7, 17, 8, 0)
        assert due_entries(sched, now, {}) == []

    def test_day_restricted_entry_fires_on_correct_day(self):
        sched = [ScheduleEntry("08:00", "weekly", ["Monday"])]
        monday = datetime(2026, 7, 20, 8, 0)
        assert monday.strftime("%A") == "Monday"
        assert len(due_entries(sched, monday, {})) == 1

    def test_day_restricted_entry_skips_wrong_day(self):
        sched = [ScheduleEntry("08:00", "weekly", ["Monday"])]
        tuesday = datetime(2026, 7, 21, 8, 0)
        assert tuesday.strftime("%A") == "Tuesday"
        assert due_entries(sched, tuesday, {}) == []

    def test_dedupes_within_same_day(self):
        sched = [ScheduleEntry("07:00", "morning")]
        now = datetime(2026, 7, 17, 7, 0)
        last_run = {sched[0].id: "2026-07-17"}
        assert due_entries(sched, now, last_run) == []

    def test_fires_again_on_new_day(self):
        sched = [ScheduleEntry("07:00", "morning")]
        now = datetime(2026, 7, 18, 7, 0)
        last_run = {sched[0].id: "2026-07-17"}
        assert len(due_entries(sched, now, last_run)) == 1

    def test_multiple_entries_same_time_both_fire(self):
        sched = [ScheduleEntry("07:00", "morning"), ScheduleEntry("07:00", "other")]
        now = datetime(2026, 7, 17, 7, 0)
        due = due_entries(sched, now, {})
        assert len(due) == 2


class TestRunScheduler:
    def test_calls_runner_and_notifier_when_due(self):
        calls = []
        notified = []
        fixed_now = datetime(2026, 7, 17, 7, 0)

        run_scheduler(
            schedule=[ScheduleEntry("07:00", "morning")],
            runner=lambda mode: calls.append(mode) or f"{mode} content",
            notifier=lambda title, content: notified.append((title, content)),
            max_iterations=1,
            clock=lambda: fixed_now,
            sleeper=lambda s: None,
        )
        assert calls == ["morning"]
        assert len(notified) == 1
        assert "morning content" in notified[0][1]

    def test_empty_runner_output_skips_notification(self):
        """Needed for nudge_check: a day with nothing notable should
        stay silent, not send an empty notification."""
        calls = []
        notified = []
        fixed_now = datetime(2026, 7, 17, 20, 0)

        run_scheduler(
            schedule=[ScheduleEntry("20:00", "nudge_check")],
            runner=lambda mode: calls.append(mode) or "",  # nothing notable
            notifier=lambda title, content: notified.append((title, content)),
            max_iterations=1,
            clock=lambda: fixed_now,
            sleeper=lambda s: None,
        )
        assert calls == ["nudge_check"]
        assert notified == []

    def test_does_not_call_when_not_due(self):
        calls = []
        fixed_now = datetime(2026, 7, 17, 9, 0)  # not 07:00

        run_scheduler(
            schedule=[ScheduleEntry("07:00", "morning")],
            runner=lambda mode: calls.append(mode) or "x",
            notifier=lambda t, c: None,
            max_iterations=1,
            clock=lambda: fixed_now,
            sleeper=lambda s: None,
        )
        assert calls == []

    def test_dedupes_across_multiple_iterations_same_minute(self):
        calls = []
        fixed_now = datetime(2026, 7, 17, 7, 0)

        run_scheduler(
            schedule=[ScheduleEntry("07:00", "morning")],
            runner=lambda mode: calls.append(mode) or "x",
            notifier=lambda t, c: None,
            max_iterations=5,
            clock=lambda: fixed_now,
            sleeper=lambda s: None,
        )
        # Same fixed "now" every iteration -> should only fire once
        assert calls == ["morning"]

    def test_runner_exception_does_not_crash_loop(self):
        notified = []
        fixed_now = datetime(2026, 7, 17, 7, 0)

        def bad_runner(mode):
            raise RuntimeError("boom")

        run_scheduler(
            schedule=[ScheduleEntry("07:00", "morning")],
            runner=bad_runner,
            notifier=lambda t, c: notified.append((t, c)),
            max_iterations=1,
            clock=lambda: fixed_now,
            sleeper=lambda s: None,
        )
        assert len(notified) == 1
        assert "runner failed" in notified[0][1]

    def test_no_runner_or_notifier_does_not_crash(self):
        fixed_now = datetime(2026, 7, 17, 7, 0)
        # Should not raise even with no callables provided
        result = run_scheduler(
            schedule=[ScheduleEntry("07:00", "morning")],
            max_iterations=1,
            clock=lambda: fixed_now,
            sleeper=lambda s: None,
        )
        assert isinstance(result, dict)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])


class TestDynamicSource:
    def _run(self, source, notifier, times, schedule=None, runner=None):
        it = iter(times)
        return run_scheduler(
            schedule=schedule if schedule is not None else [],
            runner=runner, notifier=notifier,
            max_iterations=len(times), clock=lambda: next(it), sleeper=lambda s: None,
            dynamic_source=source,
        )

    def test_items_are_delivered(self):
        notified = []
        self._run(lambda now: [("k1", "Title", "Body")],
                  lambda t, m: notified.append((t, m)), [datetime(2026, 7, 17, 9, 0)])
        assert notified == [("Title", "Body")]

    def test_deduped_per_key_per_day(self):
        notified = []
        self._run(lambda now: [("k1", "T", "B")], lambda t, m: notified.append(m),
                  [datetime(2026, 7, 17, 9, 0), datetime(2026, 7, 17, 9, 1)])
        assert notified == ["B"]

    def test_fires_again_next_day(self):
        notified = []
        self._run(lambda now: [("k1", "T", "B")], lambda t, m: notified.append(m),
                  [datetime(2026, 7, 17, 9, 0), datetime(2026, 7, 18, 9, 0)])
        assert notified == ["B", "B"]

    def test_different_keys_both_delivered(self):
        notified = []
        self._run(lambda now: [("a", "T", "one"), ("b", "T", "two")],
                  lambda t, m: notified.append(m), [datetime(2026, 7, 17, 9, 0)])
        assert notified == ["one", "two"]

    def test_empty_message_skipped(self):
        notified = []
        self._run(lambda now: [("k", "T", "")], lambda t, m: notified.append(m),
                  [datetime(2026, 7, 17, 9, 0)])
        assert notified == []

    def test_source_exception_does_not_crash_loop(self, capsys):
        calls = []

        def bad_source(now):
            calls.append(now)
            raise RuntimeError("boom")

        self._run(bad_source, lambda t, m: None,
                  [datetime(2026, 7, 17, 9, 0), datetime(2026, 7, 17, 9, 1)])
        assert len(calls) == 2
        assert "dynamic source failed" in capsys.readouterr().err

    def test_notifier_exception_does_not_crash_loop(self, capsys):
        seen = []

        def bad_notifier(t, m):
            seen.append(m)
            raise RuntimeError("down")

        self._run(lambda now: [("a", "T", "one"), ("b", "T", "two")], bad_notifier,
                  [datetime(2026, 7, 17, 9, 0)])
        assert seen == ["one", "two"]
        assert "notifier failed" in capsys.readouterr().err

    def test_no_notifier_does_not_crash(self):
        self._run(lambda now: [("a", "T", "one")], None, [datetime(2026, 7, 17, 9, 0)])

    def test_dynamic_items_not_in_last_run(self):
        result = self._run(lambda now: [("a", "T", "one")], lambda t, m: None,
                           [datetime(2026, 7, 17, 9, 0)])
        assert result == {}

    def test_works_alongside_fixed_schedule(self):
        notified = []
        self._run(lambda now: [("a", "T", "reminder")],
                  lambda t, m: notified.append(m), [datetime(2026, 7, 17, 7, 0)],
                  schedule=[ScheduleEntry("07:00", "morning")], runner=lambda mode: "briefing")
        assert notified == ["briefing", "reminder"]

    def test_omitting_source_keeps_old_behavior(self):
        notified = []
        run_scheduler(
            schedule=[ScheduleEntry("07:00", "morning")], runner=lambda m: "x",
            notifier=lambda t, c: notified.append(c), max_iterations=1,
            clock=lambda: datetime(2026, 7, 17, 7, 0), sleeper=lambda s: None,
        )
        assert notified == ["x"]
