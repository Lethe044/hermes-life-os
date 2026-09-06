"""Tests for demo/moon.py. All computation is local (no network) - the
tests include real known-full-moon dates to sanity-check the formula
against actual astronomical data, not just internal consistency."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def moon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "moon"):
        if mod in sys.modules:
            del sys.modules[mod]
    import moon as m
    importlib.reload(m)
    import storage
    storage.set_active_profile(None)
    return m


class TestMoonPhaseFraction:
    @pytest.mark.parametrize("date_str", ["2024-01-25", "2024-08-19", "2026-01-03"])
    def test_known_full_moons_land_near_half(self, moon, date_str):
        # Real published full-moon dates - fraction should land close
        # to 0.5 (full moon), well within the formula's ~1-day accuracy.
        d = datetime.strptime(date_str, "%Y-%m-%d")
        fraction = moon.moon_phase_fraction(d)
        assert 0.4 < fraction < 0.6

    def test_fraction_always_in_valid_range(self, moon):
        for year in (2020, 2023, 2026, 2030):
            d = datetime(year, 6, 15)
            fraction = moon.moon_phase_fraction(d)
            assert 0.0 <= fraction < 1.0

    def test_reference_new_moon_is_near_zero(self, moon):
        # The reference date itself should read as (close to) new moon.
        fraction = moon.moon_phase_fraction(moon._REFERENCE_NEW_MOON)
        assert fraction < 0.02 or fraction > 0.98


class TestMoonPhaseName:
    def test_zero_is_new_moon(self, moon):
        assert moon.moon_phase_name(0.0) == "New Moon"

    def test_half_is_full_moon(self, moon):
        assert moon.moon_phase_name(0.5) == "Full Moon"

    def test_all_thresholds_return_a_valid_name(self, moon):
        valid_names = {name for _t, name in moon._PHASE_NAMES}
        for i in range(20):
            fraction = i / 20
            assert moon.moon_phase_name(fraction) in valid_names


class TestMoonIllumination:
    def test_new_moon_is_dark(self, moon):
        assert moon.moon_illumination(0.0) < 0.05

    def test_full_moon_is_bright(self, moon):
        assert moon.moon_illumination(0.5) > 0.95

    def test_quarter_moon_is_roughly_half_lit(self, moon):
        assert 0.4 < moon.moon_illumination(0.25) < 0.6

    def test_illumination_always_in_valid_range(self, moon):
        for i in range(20):
            fraction = i / 20
            illum = moon.moon_illumination(fraction)
            assert 0.0 <= illum <= 1.0


class TestComputeMoonCorrelation:
    def test_no_data_returns_empty_correlations(self, moon):
        result = moon.compute_moon_correlation(90)
        assert result["correlations"] == []
        assert "today_phase" in result
        assert 0 <= result["today_illumination_pct"] <= 100

    def test_includes_days_param(self, moon):
        result = moon.compute_moon_correlation(45)
        assert result["days"] == 45

    def test_with_data_does_not_crash(self, moon):
        import storage
        for i in range(10):
            storage.write_memory({"type": "mood", "content": "day", "score": 5 + (i % 3)})
        result = moon.compute_moon_correlation(90)
        assert isinstance(result["correlations"], list)


class TestFormatMoonInsights:
    def test_empty_correlations_returns_empty_list(self, moon):
        result = {"correlations": []}
        assert moon.format_moon_insights(result) == []

    def test_formats_positive_correlation(self, moon):
        result = {"correlations": [{
            "metric": "mood", "r": 0.55, "n_days": 12, "direction": "positive",
        }]}
        insights = moon.format_moon_insights(result)
        assert len(insights) == 1
        assert "mood" in insights[0]
        assert "rise together" in insights[0]

    def test_formats_negative_correlation(self, moon):
        result = {"correlations": [{
            "metric": "stress", "r": -0.4, "n_days": 8, "direction": "negative",
        }]}
        insights = moon.format_moon_insights(result)
        assert "opposite directions" in insights[0]

    def test_respects_limit(self, moon):
        correlations = [
            {"metric": f"m{i}", "r": 0.5, "n_days": 5, "direction": "positive"}
            for i in range(5)
        ]
        assert len(moon.format_moon_insights({"correlations": correlations}, limit=2)) == 2
