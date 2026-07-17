"""Tests for the real statistical correlation engine (demo/analytics.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

from analytics import (
    pearson_correlation,
    build_daily_series,
    daily_averages,
    compute_correlations,
    format_correlation_insights,
)


def _entry(type_, ts, **kwargs):
    e = {"type": type_, "timestamp": ts}
    e.update(kwargs)
    return e


class TestPearsonCorrelation:
    def test_perfect_positive(self):
        r = pearson_correlation([1, 2, 3, 4], [1, 2, 3, 4])
        assert abs(r - 1.0) < 1e-9

    def test_perfect_negative(self):
        r = pearson_correlation([1, 2, 3, 4], [4, 3, 2, 1])
        assert abs(r - (-1.0)) < 1e-9

    def test_no_variance_returns_none(self):
        assert pearson_correlation([1, 1, 1], [1, 2, 3]) is None

    def test_too_few_points_returns_none(self):
        assert pearson_correlation([1], [2]) is None

    def test_mismatched_lengths_returns_none(self):
        assert pearson_correlation([1, 2, 3], [1, 2]) is None

    def test_zero_correlation_ish(self):
        # Symmetric series around mean with no linear relationship
        r = pearson_correlation([1, 2, 3, 4, 5], [3, 1, 4, 1, 3])
        assert r is not None
        assert -1.0 <= r <= 1.0


class TestDailyAggregation:
    def test_build_daily_series_groups_by_date(self):
        entries = [
            _entry("mood", "2026-06-01T08:00:00Z", score=5),
            _entry("mood", "2026-06-01T20:00:00Z", score=7),
            _entry("mood", "2026-06-02T08:00:00Z", score=6),
        ]
        series = build_daily_series(entries)
        assert series["2026-06-01"]["mood"] == [5.0, 7.0]
        assert series["2026-06-02"]["mood"] == [6.0]

    def test_daily_averages_collapses_same_day(self):
        entries = [
            _entry("mood", "2026-06-01T08:00:00Z", score=4),
            _entry("mood", "2026-06-01T20:00:00Z", score=8),
        ]
        avgs = daily_averages(entries)
        assert avgs["2026-06-01"]["mood"] == 6.0

    def test_ignores_entries_without_timestamp(self):
        entries = [{"type": "mood", "score": 5}]
        assert build_daily_series(entries) == {}

    def test_ignores_unrecognized_types(self):
        entries = [_entry("win", "2026-06-01T08:00:00Z", description="shipped")]
        assert build_daily_series(entries) == {}

    def test_energy_level_mapping(self):
        entries = [
            _entry("energy", "2026-06-01T08:00:00Z", level="low"),
            _entry("energy", "2026-06-02T08:00:00Z", level="high"),
        ]
        avgs = daily_averages(entries)
        assert avgs["2026-06-01"]["energy"] == 1.0
        assert avgs["2026-06-02"]["energy"] == 3.0


class TestComputeCorrelations:
    def _sleep_mood_entries(self, sleep_vals, mood_vals, start_day=21):
        entries = []
        for i, (s, m) in enumerate(zip(sleep_vals, mood_vals)):
            date = f"2026-06-{start_day + i:02d}"
            entries.append(_entry("sleep", f"{date}T08:00:00Z", hours=s))
            entries.append(_entry("mood", f"{date}T22:00:00Z", score=m))
        return entries

    def test_detects_strong_positive_correlation(self):
        entries = self._sleep_mood_entries(
            [4.5, 5, 4, 6, 4.5, 7, 8],
            [3, 4, 3, 5, 4, 7, 8],
        )
        corrs = compute_correlations(entries)
        assert len(corrs) == 1
        assert corrs[0]["direction"] == "positive"
        assert corrs[0]["strength"] == "strong"
        assert corrs[0]["n_days"] == 7

    def test_no_data_returns_empty(self):
        assert compute_correlations([]) == []

    def test_below_min_days_excluded(self):
        # Only 2 overlapping days - below default min_days=4
        entries = self._sleep_mood_entries([4, 8], [3, 8])
        assert compute_correlations(entries) == []

    def test_weak_correlation_filtered_by_min_abs_r(self):
        # Near-random relationship should not pass the default threshold
        entries = self._sleep_mood_entries(
            [5, 5, 5, 5, 5],
            [3, 8, 3, 8, 3],
        )
        corrs = compute_correlations(entries, min_abs_r=0.99)
        assert corrs == []

    def test_results_sorted_by_strength_desc(self):
        entries = self._sleep_mood_entries(
            [4, 5, 6, 7, 8],
            [3, 4, 5, 6, 7],
        )
        # add a weaker, independent metric pair
        for i in range(5):
            date = f"2026-06-{21 + i:02d}"
            entries.append(_entry("hydration", f"{date}T09:00:00Z", glasses=(i % 3) + 1))
        corrs = compute_correlations(entries, min_abs_r=0.0)
        rs = [abs(c["r"]) for c in corrs]
        assert rs == sorted(rs, reverse=True)


class TestFormatInsights:
    def test_formats_readable_strings(self):
        corrs = [{
            "metric_a": "sleep", "metric_b": "mood", "r": 0.85,
            "n_days": 7, "strength": "strong", "direction": "positive",
            "note": "sleep and mood tend to move together",
        }]
        out = format_correlation_insights(corrs)
        assert len(out) == 1
        assert "sleep" in out[0] and "mood" in out[0]
        assert "0.85" in out[0]

    def test_respects_limit(self):
        corrs = [
            {"metric_a": "a", "metric_b": "b", "r": 0.9, "n_days": 5,
             "strength": "strong", "direction": "positive", "note": "n/a"},
            {"metric_a": "c", "metric_b": "d", "r": 0.8, "n_days": 5,
             "strength": "strong", "direction": "positive", "note": "n/a"},
            {"metric_a": "e", "metric_b": "f", "r": 0.7, "n_days": 5,
             "strength": "strong", "direction": "positive", "note": "n/a"},
        ]
        assert len(format_correlation_insights(corrs, limit=2)) == 2

    def test_empty_input(self):
        assert format_correlation_insights([]) == []


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
