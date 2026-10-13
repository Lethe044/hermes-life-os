"""update_habit: one check-in per day, gaps restart the streak, other dates are only recorded."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
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
    import tools
    importlib.reload(tools)
    import storage
    storage.set_active_profile(None)
    return tools


def at(monkeypatch, day, hour=9):
    when = datetime(2026, 10, 1, hour, 0) + timedelta(days=day)
    monkeypatch.setattr(clock, "now", lambda: when)


def habit(app, **extra):
    return app.dispatch_tool("update_habit", {"habit_name": "run", "completed": True, **extra})


def stored():
    import storage
    return storage.load_habits()[0]


class TestOncePerDay:
    def test_second_checkin_same_day_does_not_inflate(self, app, monkeypatch):
        at(monkeypatch, 0)
        habit(app)
        out = habit(app)
        assert "already checked in today" in out and "streak stays at 1 days" in out
        assert stored()["streak"] == 1

    def test_no_second_journal_entry(self, app, monkeypatch):
        import storage
        at(monkeypatch, 0)
        habit(app)
        habit(app)
        habit(app)
        assert len([m for m in storage.get_all_memory() if m["type"] == "habit_completion"]) == 1

    def test_next_day_counts(self, app, monkeypatch):
        at(monkeypatch, 0)
        habit(app)
        at(monkeypatch, 1)
        assert "streak 2 days" in habit(app)

    def test_late_night_checkin_with_day_start_hour_counts_for_the_previous_day(self, app, monkeypatch):
        monkeypatch.setenv("LIFE_OS_DAY_START_HOUR", "4")
        at(monkeypatch, 0, hour=22)
        habit(app)
        at(monkeypatch, 1, hour=1)  # 01:00 still belongs to day 0 for this user
        assert "already checked in today" in habit(app)
        at(monkeypatch, 1, hour=5)
        assert "streak 2 days" in habit(app)

    def test_missed_flag_after_checkin_still_resets(self, app, monkeypatch):
        at(monkeypatch, 0)
        habit(app)
        out = app.dispatch_tool("update_habit", {"habit_name": "run", "completed": False})
        assert "streak 0 days" in out


class TestGaps:
    def test_a_missed_day_restarts_the_streak(self, app, monkeypatch):
        for d in (0, 1, 2):
            at(monkeypatch, d)
            habit(app)
        at(monkeypatch, 4)  # day 3 skipped
        out = habit(app)
        assert "streak 1 days" in out and "best: 3" in out

    def test_a_gap_of_exactly_one_day_continues(self, app, monkeypatch):
        at(monkeypatch, 0)
        habit(app)
        at(monkeypatch, 1)
        assert "streak 2 days" in habit(app)

    def test_freeze_bridges_a_missed_day(self, app, monkeypatch):
        for d in range(7):
            at(monkeypatch, d)
            habit(app)
        at(monkeypatch, 7)
        out = app.dispatch_tool("update_habit", {"habit_name": "run", "completed": False, "use_freeze": True})
        assert "protected with a freeze" in out
        at(monkeypatch, 8)
        assert "streak 8 days" in habit(app)

    def test_legacy_habit_without_last_done_just_increments(self, app, monkeypatch):
        import storage
        storage.save_habits([{"name": "run", "streak": 4, "best_streak": 4, "last_done": None}])
        at(monkeypatch, 0)
        assert "streak 5 days" in habit(app)

    def test_freeze_earned_every_seven_days(self, app, monkeypatch):
        out = ""
        for d in range(7):
            at(monkeypatch, d)
            out = habit(app)
        assert "earned a streak freeze" in out and stored()["freezes_available"] == 1


class TestOtherDates:
    def test_backdated_checkin_is_recorded_but_leaves_the_streak(self, app, monkeypatch):
        import storage
        at(monkeypatch, 5)
        habit(app)
        out = habit(app, date="2026-10-03")
        assert "recorded for 2026-10-03 (done)" in out and "unchanged" in out
        h = stored()
        assert h["streak"] == 1 and h["last_done"] == "2026-10-06"
        m = [x for x in storage.get_all_memory() if x["type"] == "habit_completion"][-1]
        assert m["timestamp"] == "2026-10-03T12:00:00Z" and m["completed"] is True

    def test_backdated_miss(self, app, monkeypatch):
        at(monkeypatch, 5)
        habit(app)
        out = app.dispatch_tool("update_habit", {"habit_name": "run", "completed": False, "date": "2026-10-03"})
        assert "recorded for 2026-10-03 (missed)" in out and stored()["streak"] == 1

    def test_backdated_for_a_new_habit_creates_it_without_a_streak(self, app, monkeypatch):
        at(monkeypatch, 5)
        out = habit(app, date="2026-10-03")
        h = stored()
        assert h["streak"] == 0 and h["best_streak"] == 0 and h["last_done"] is None
        assert h["created"] == "2026-10-03" and "recorded for 2026-10-03" in out

    def test_backdated_feeds_consistency_analytics(self, app, monkeypatch):
        from habit_consistency import compute_habit_consistency
        at(monkeypatch, 5)
        habit(app)
        habit(app, date="2026-10-04")
        habit(app, date="2026-10-03")
        r = compute_habit_consistency(90)[0]
        assert r["total_checkins"] == 3 and r["completed_checkins"] == 3

    def test_today_as_explicit_date_is_a_normal_checkin(self, app, monkeypatch):
        at(monkeypatch, 0)
        assert "streak 1 days" in habit(app, date="2026-10-01")

    @pytest.mark.parametrize("bad", ["2026-10-09", "soon", "2020-01-01"])
    def test_bad_dates_write_nothing(self, app, monkeypatch, bad):
        import storage
        at(monkeypatch, 5)
        out = habit(app, date=bad)
        assert out.startswith("Not logged: ")
        assert storage.load_habits() == [] and storage.get_all_memory() == []

    def test_schema_has_date(self, app):
        schemas = {t["function"]["name"]: t["function"] for t in app.TOOLS}
        assert schemas["update_habit"]["parameters"]["properties"]["date"] == app._ENTRY_DATE_PROP
        assert "date" not in schemas["update_habit"]["parameters"]["required"]


class TestDownstream:
    def test_milestones_see_the_real_streak(self, app, monkeypatch):
        for d in range(3):
            at(monkeypatch, d)
            habit(app)
            habit(app)  # the double check-in must not count twice
        assert "3" in app.dispatch_tool("list_habits", {}).split("run")[1].split("streak")[1][:4]
