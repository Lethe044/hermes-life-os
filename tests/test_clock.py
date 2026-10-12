"""Tests for demo/clock.py - the single source of "what day is it for the user"."""

from __future__ import annotations

import sys
from datetime import datetime, date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

import clock  # noqa: E402 - needs the demo/ path set up above


def freeze(monkeypatch, *args):
    """Pin the wall clock to a local datetime(*args)."""
    when = datetime(*args)
    monkeypatch.setattr(clock, "now", lambda: when)
    return when


class TestNow:
    def test_returns_naive_local_datetime(self):
        n = clock.now()
        assert isinstance(n, datetime)
        assert n.tzinfo is None

    def test_tracks_the_system_clock(self):
        assert abs((datetime.now() - clock.now()).total_seconds()) < 5


class TestDayStartHour:
    @pytest.mark.parametrize("raw,expected", [
        (None, 0), ("", 0), ("   ", 0), ("0", 0), ("4", 4), (" 6 ", 6), ("12", 12),
        ("13", 0), ("-1", 0), ("99", 0), ("abc", 0), ("4.5", 0), ("04", 4),
    ])
    def test_parsing(self, monkeypatch, raw, expected):
        if raw is None:
            monkeypatch.delenv(clock.DAY_START_ENV, raising=False)
        else:
            monkeypatch.setenv(clock.DAY_START_ENV, raw)
        assert clock.day_start_hour() == expected

    @pytest.mark.parametrize("raw", [None, "", "0", "4", "12", " 7 "])
    def test_no_problem_for_unset_or_valid(self, monkeypatch, raw):
        if raw is None:
            monkeypatch.delenv(clock.DAY_START_ENV, raising=False)
        else:
            monkeypatch.setenv(clock.DAY_START_ENV, raw)
        assert clock.day_start_problem() is None

    @pytest.mark.parametrize("raw", ["abc", "4.5", "13", "-1", "99"])
    def test_problem_described_for_invalid(self, monkeypatch, raw):
        monkeypatch.setenv(clock.DAY_START_ENV, raw)
        msg = clock.day_start_problem()
        assert msg and clock.DAY_START_ENV in msg and "ignored" in msg

    def test_invalid_value_never_shifts_the_day(self, monkeypatch):
        freeze(monkeypatch, 2026, 11, 1, 1, 30)
        monkeypatch.setenv(clock.DAY_START_ENV, "banana")
        assert clock.today_str() == "2026-11-01"


class TestDerivedDates:
    def test_just_after_midnight(self, monkeypatch):
        freeze(monkeypatch, 2026, 11, 1, 0, 30)
        assert clock.today_str() == "2026-11-01"
        assert clock.today() == date(2026, 11, 1)
        assert clock.month_str() == "2026-11"
        assert clock.days_ago_str(0) == "2026-11-01"
        assert clock.days_ago_str(1) == "2026-10-31"
        assert clock.days_ago_str(30) == "2026-10-02"

    def test_late_evening(self, monkeypatch):
        freeze(monkeypatch, 2026, 10, 31, 23, 59)
        assert clock.today_str() == "2026-10-31"
        assert clock.month_str() == "2026-10"

    def test_ignores_the_real_utc_date(self, monkeypatch):
        """Whatever the machine's real clock says, everything derives from now()."""
        freeze(monkeypatch, 1999, 12, 31, 23, 0)
        assert clock.today_str() == "1999-12-31"
        assert clock.month_str() == "1999-12"

    def test_leap_day_arithmetic(self, monkeypatch):
        freeze(monkeypatch, 2028, 3, 1, 0, 10)
        assert clock.days_ago_str(1) == "2028-02-29"
        assert clock.days_ago_str(2) == "2028-02-28"

    def test_year_boundary(self, monkeypatch):
        freeze(monkeypatch, 2027, 1, 1, 0, 5)
        assert clock.days_ago_str(1) == "2026-12-31"
        assert clock.days_ago_str(400) == "2025-11-27"

    def test_effective_now_is_now_by_default(self, monkeypatch):
        when = freeze(monkeypatch, 2026, 5, 5, 5, 5)
        assert clock.effective_now() == when


class TestDayStartShift:
    def test_before_the_boundary_counts_as_yesterday(self, monkeypatch):
        monkeypatch.setenv(clock.DAY_START_ENV, "4")
        freeze(monkeypatch, 2026, 11, 1, 3, 59)
        assert clock.today_str() == "2026-10-31"
        assert clock.month_str() == "2026-10"
        assert clock.days_ago_str(1) == "2026-10-30"

    def test_exactly_at_the_boundary_is_the_new_day(self, monkeypatch):
        monkeypatch.setenv(clock.DAY_START_ENV, "4")
        freeze(monkeypatch, 2026, 11, 1, 4, 0)
        assert clock.today_str() == "2026-11-01"
        assert clock.month_str() == "2026-11"

    def test_new_year_night(self, monkeypatch):
        monkeypatch.setenv(clock.DAY_START_ENV, "4")
        freeze(monkeypatch, 2027, 1, 1, 1, 0)
        assert clock.today_str() == "2026-12-31"
        assert clock.month_str() == "2026-12"

    def test_afternoon_unaffected(self, monkeypatch):
        monkeypatch.setenv(clock.DAY_START_ENV, "6")
        freeze(monkeypatch, 2026, 11, 1, 15, 0)
        assert clock.today_str() == "2026-11-01"

    def test_maximum_shift(self, monkeypatch):
        monkeypatch.setenv(clock.DAY_START_ENV, "12")
        freeze(monkeypatch, 2026, 11, 1, 11, 59)
        assert clock.today_str() == "2026-10-31"
        freeze(monkeypatch, 2026, 11, 1, 12, 0)
        assert clock.today_str() == "2026-11-01"


class TestHermeticDefault:
    def test_conftest_clears_a_developers_own_setting(self):
        import os
        assert clock.DAY_START_ENV not in os.environ
