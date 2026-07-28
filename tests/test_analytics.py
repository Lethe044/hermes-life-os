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
    compute_goal_progress,
    compare_periods,
    compare_before_after,
    detect_anomalies,
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


class TestComputeGoalProgress:
    def test_none_when_not_metric_linked(self):
        entries = [_entry("mood", "2026-01-01T09:00:00Z", score=8)]
        assert compute_goal_progress({"name": "x", "progress": 50}, entries) is None

    def test_none_when_no_matching_data(self):
        goal = {"metric": "sleep", "target": 7, "direction": "at_least"}
        entries = [_entry("mood", "2026-01-01T09:00:00Z", score=8)]  # no sleep entries
        assert compute_goal_progress(goal, entries) is None

    def test_at_least_full_progress_when_average_meets_target(self):
        goal = {"metric": "sleep", "target": 7, "direction": "at_least"}
        entries = [_entry("sleep", f"2026-01-0{i}T09:00:00Z", hours=8) for i in range(1, 4)]
        assert compute_goal_progress(goal, entries) == 100.0

    def test_at_least_partial_progress(self):
        goal = {"metric": "sleep", "target": 8, "direction": "at_least"}
        entries = [_entry("sleep", f"2026-01-0{i}T09:00:00Z", hours=4) for i in range(1, 4)]
        assert compute_goal_progress(goal, entries) == 50.0

    def test_at_least_clamped_to_100(self):
        goal = {"metric": "sleep", "target": 4, "direction": "at_least"}
        entries = [_entry("sleep", f"2026-01-0{i}T09:00:00Z", hours=10) for i in range(1, 4)]
        assert compute_goal_progress(goal, entries) == 100.0

    def test_at_most_full_progress_when_average_under_target(self):
        goal = {"metric": "stress", "target": 5, "direction": "at_most"}
        entries = [_entry("stress", f"2026-01-0{i}T09:00:00Z", score=3) for i in range(1, 4)]
        assert compute_goal_progress(goal, entries) == 100.0

    def test_at_most_partial_progress_when_average_over_target(self):
        goal = {"metric": "stress", "target": 4, "direction": "at_most"}
        entries = [_entry("stress", f"2026-01-0{i}T09:00:00Z", score=8) for i in range(1, 4)]
        result = compute_goal_progress(goal, entries)
        assert 0 < result < 100

    def test_unknown_metric_returns_none(self):
        goal = {"metric": "not_a_real_metric", "target": 5, "direction": "at_least"}
        entries = [_entry("mood", "2026-01-01T09:00:00Z", score=8)]
        assert compute_goal_progress(goal, entries) is None


class TestComparePeriods:
    def test_empty_when_no_overlapping_metrics(self):
        current = [_entry("mood", "2026-01-08T09:00:00Z", score=8)]
        previous = [_entry("sleep", "2026-01-01T09:00:00Z", hours=7)]  # different metric
        assert compare_periods(current, previous) == {}

    def test_computes_delta_and_pct_change(self):
        current = [_entry("mood", "2026-01-08T09:00:00Z", score=8)]
        previous = [_entry("mood", "2026-01-01T09:00:00Z", score=4)]
        result = compare_periods(current, previous)
        assert result["mood"]["current"] == 8.0
        assert result["mood"]["previous"] == 4.0
        assert result["mood"]["delta"] == 4.0
        assert result["mood"]["pct_change"] == 100.0

    def test_only_includes_metrics_present_in_both_periods(self):
        current = [
            _entry("mood", "2026-01-08T09:00:00Z", score=8),
            _entry("sleep", "2026-01-08T09:00:00Z", hours=7),
        ]
        previous = [_entry("mood", "2026-01-01T09:00:00Z", score=4)]  # no sleep here
        result = compare_periods(current, previous)
        assert "mood" in result
        assert "sleep" not in result

    def test_negative_delta_for_decline(self):
        current = [_entry("stress", "2026-01-08T09:00:00Z", score=3)]
        previous = [_entry("stress", "2026-01-01T09:00:00Z", score=8)]
        result = compare_periods(current, previous)
        assert result["stress"]["delta"] < 0


class TestCompareBeforeAfter:
    def test_splits_by_changepoint_date(self):
        entries = [
            _entry("mood", "2026-01-01T09:00:00Z", score=4),   # before
            _entry("mood", "2026-01-05T09:00:00Z", score=4),   # before
            _entry("mood", "2026-03-01T09:00:00Z", score=8),   # after (changepoint itself)
            _entry("mood", "2026-03-05T09:00:00Z", score=8),   # after
        ]
        result = compare_before_after(entries, "2026-03-01")
        assert result["mood"]["previous"] == 4.0
        assert result["mood"]["current"] == 8.0

    def test_changepoint_date_itself_counts_as_after(self):
        entries = [
            _entry("mood", "2026-02-28T09:00:00Z", score=2),
            _entry("mood", "2026-03-01T09:00:00Z", score=9),
        ]
        result = compare_before_after(entries, "2026-03-01")
        assert result["mood"]["current"] == 9.0
        assert result["mood"]["previous"] == 2.0

    def test_invalid_date_returns_empty(self):
        entries = [_entry("mood", "2026-01-01T09:00:00Z", score=4)]
        assert compare_before_after(entries, "not-a-date") == {}

    def test_empty_entries_returns_empty(self):
        assert compare_before_after([], "2026-01-01") == {}


class TestDetectAnomalies:
    def test_flags_clear_outlier(self):
        # 5 normal days around stress=3, then one wildly high day
        entries = [_entry("stress", f"2026-01-0{i}T09:00:00Z", score=3) for i in range(1, 6)]
        entries.append(_entry("stress", "2026-01-06T09:00:00Z", score=15))
        result = detect_anomalies(entries, min_history_days=5)
        assert any(a["date"] == "2026-01-06" and a["direction"] == "above" for a in result)

    def test_no_anomalies_in_flat_data(self):
        entries = [_entry("mood", f"2026-01-0{i}T09:00:00Z", score=5) for i in range(1, 8)]
        assert detect_anomalies(entries, min_history_days=5) == []

    def test_respects_min_history_days(self):
        # only 3 days of data, default min_history_days=5 -> nothing flagged
        entries = [_entry("mood", f"2026-01-0{i}T09:00:00Z", score=3 + i * 5) for i in range(1, 4)]
        assert detect_anomalies(entries, min_history_days=5) == []

    def test_empty_entries_returns_empty(self):
        assert detect_anomalies([]) == []

    def test_below_direction_detected(self):
        entries = [_entry("mood", f"2026-01-0{i}T09:00:00Z", score=8) for i in range(1, 6)]
        entries.append(_entry("mood", "2026-01-06T09:00:00Z", score=1))
        result = detect_anomalies(entries, min_history_days=5)
        assert any(a["date"] == "2026-01-06" and a["direction"] == "below" for a in result)

    def test_sorted_most_extreme_first(self):
        entries = [_entry("mood", f"2026-01-0{i}T09:00:00Z", score=5) for i in range(1, 6)]
        entries.append(_entry("mood", "2026-01-07T09:00:00Z", score=6))   # mild
        entries.append(_entry("mood", "2026-01-08T09:00:00Z", score=20))  # extreme
        result = detect_anomalies(entries, min_history_days=5)
        if len(result) >= 2:
            assert abs(result[0]["z_score"]) >= abs(result[1]["z_score"])


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
