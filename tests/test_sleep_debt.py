"""Tests for demo/sleep_debt.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def sleep_debt(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "sleep_debt"):
        if mod in sys.modules:
            del sys.modules[mod]
    import sleep_debt as sd
    importlib.reload(sd)
    import storage
    storage.set_active_profile(None)
    return sd


class TestComputeSleepDebt:
    def test_no_data_returns_zero_logged_days(self, sleep_debt):
        result = sleep_debt.compute_sleep_debt(14)
        assert result["logged_days"] == 0
        assert result["total_debt_hours"] == 0.0

    def test_sleeping_under_target_creates_debt(self, sleep_debt):
        import storage
        storage.write_memory({"type": "sleep", "content": "slept", "hours": 6.0})
        result = sleep_debt.compute_sleep_debt(14, target_hours=8.0)
        assert result["logged_days"] == 1
        assert result["total_debt_hours"] == 2.0

    def test_sleeping_over_target_creates_negative_debt(self, sleep_debt):
        import storage
        storage.write_memory({"type": "sleep", "content": "slept", "hours": 9.0})
        result = sleep_debt.compute_sleep_debt(14, target_hours=8.0)
        assert result["total_debt_hours"] == -1.0

    def test_debt_accumulates_across_days(self, sleep_debt):
        import storage
        storage.write_memory({"type": "sleep", "content": "day1", "hours": 6.0})
        result = sleep_debt.compute_sleep_debt(14, target_hours=8.0)
        # Only one day logged in this test (write_memory always stamps
        # "now"), but confirms the per-entry arithmetic is right.
        assert result["avg_debt_per_day"] == 2.0

    def test_custom_target_hours_respected(self, sleep_debt):
        import storage
        storage.write_memory({"type": "sleep", "content": "slept", "hours": 6.0})
        result = sleep_debt.compute_sleep_debt(14, target_hours=6.0)
        assert result["total_debt_hours"] == 0.0

    def test_days_and_target_hours_passed_through(self, sleep_debt):
        result = sleep_debt.compute_sleep_debt(days=21, target_hours=7.5)
        assert result["days"] == 21
        assert result["target_hours"] == 7.5


class TestSuggestedBedtime:
    def test_no_debt_uses_target_hours_exactly(self, sleep_debt):
        bedtime = sleep_debt.suggested_bedtime("07:00", target_hours=8.0, debt_hours=0.0)
        assert bedtime == "23:00"

    def test_some_debt_nudges_earlier(self, sleep_debt):
        no_debt = sleep_debt.suggested_bedtime("07:00", target_hours=8.0, debt_hours=0.0)
        with_debt = sleep_debt.suggested_bedtime("07:00", target_hours=8.0, debt_hours=4.0)
        # with_debt should be an earlier clock time than no_debt
        assert with_debt != no_debt

    def test_debt_capped_at_max_extra(self, sleep_debt):
        # A huge debt shouldn't push the suggestion more than max_extra_hours early.
        result = sleep_debt.suggested_bedtime("07:00", target_hours=8.0, debt_hours=1000, max_extra_hours=1.0)
        # 8h target + at most 1h extra = 9h before 07:00 = 22:00
        assert result == "22:00"

    def test_handles_wrap_past_midnight(self, sleep_debt):
        # Waking at 06:00 with an 8h target means bedtime is the
        # evening before - just confirms no crash/garbage output.
        result = sleep_debt.suggested_bedtime("06:00", target_hours=8.0)
        assert len(result) == 5 and ":" in result

    def test_negative_debt_treated_as_zero(self, sleep_debt):
        # A sleep surplus shouldn't push bedtime *later* than the plain target.
        result = sleep_debt.suggested_bedtime("07:00", target_hours=8.0, debt_hours=-5.0)
        assert result == "23:00"


class TestFormatSleepDebtSummary:
    def test_no_data_message(self, sleep_debt):
        result = sleep_debt.compute_sleep_debt(14)
        summary = sleep_debt.format_sleep_debt_summary(result)
        assert "No sleep logged" in summary

    def test_debt_message_mentions_hours_short(self, sleep_debt):
        result = {"days": 14, "target_hours": 8.0, "logged_days": 5,
                  "total_debt_hours": 10.0, "avg_debt_per_day": 2.0}
        summary = sleep_debt.format_sleep_debt_summary(result)
        assert "10.0h total" in summary
        assert "short of your 8.0h target" in summary

    def test_surplus_message_mentions_above_target(self, sleep_debt):
        result = {"days": 14, "target_hours": 8.0, "logged_days": 5,
                  "total_debt_hours": -3.0, "avg_debt_per_day": -0.6}
        summary = sleep_debt.format_sleep_debt_summary(result)
        assert "No sleep debt" in summary
        assert "above your 8.0h target" in summary
