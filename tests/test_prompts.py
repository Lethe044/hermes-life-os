"""Tests for demo/prompts.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

import prompts


class TestGetDailyPrompt:
    def test_returns_a_string_from_the_list(self):
        result = prompts.get_daily_prompt("2026-01-01")
        assert result in prompts.DAILY_PROMPTS

    def test_same_date_always_returns_same_prompt(self):
        first = prompts.get_daily_prompt("2026-03-15")
        second = prompts.get_daily_prompt("2026-03-15")
        assert first == second

    def test_different_dates_can_return_different_prompts(self):
        # Not a strict guarantee for every pair, but across many dates
        # we should see more than one distinct prompt - otherwise the
        # hashing isn't actually varying anything.
        seen = {prompts.get_daily_prompt(f"2026-01-{d:02d}") for d in range(1, 29)}
        assert len(seen) > 1

    def test_defaults_to_today_when_no_date_given(self):
        # Doesn't raise, and returns a valid prompt.
        result = prompts.get_daily_prompt()
        assert result in prompts.DAILY_PROMPTS

    def test_prompt_list_has_no_duplicates(self):
        assert len(prompts.DAILY_PROMPTS) == len(set(prompts.DAILY_PROMPTS))

    def test_prompt_list_is_reasonably_sized(self):
        # Enough variety that it doesn't feel like the same handful of
        # questions on repeat within a month.
        assert len(prompts.DAILY_PROMPTS) >= 20
