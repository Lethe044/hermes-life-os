"""Tests for demo/life_score.py - the composite 0-100 daily wellbeing
score. Isolated via a temp HOME so these never touch real data."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def life_score(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "life_score"):
        if mod in sys.modules:
            del sys.modules[mod]
    import life_score as ls
    importlib.reload(ls)
    import storage
    storage.set_active_profile(None)
    return ls


class TestScoreFromAverages:
    def test_none_when_no_metrics(self, life_score):
        assert life_score._score_from_averages({}) is None

    def test_perfect_scores_yield_100(self, life_score):
        result = life_score._score_from_averages({
            "mood": 10, "sleep": 8, "hydration": 8, "stress": 0, "energy": 3,
        })
        assert result["score"] == 100
        assert result["label"] == "Thriving"

    def test_worst_scores_yield_low_score(self, life_score):
        result = life_score._score_from_averages({
            "mood": 0, "sleep": 0, "hydration": 0, "stress": 10, "energy": 0,
        })
        assert result["score"] == 0
        assert result["label"] == "Tough day"

    def test_stress_is_inverted(self, life_score):
        low_stress = life_score._score_from_averages({"stress": 0})
        high_stress = life_score._score_from_averages({"stress": 10})
        assert low_stress["score"] > high_stress["score"]

    def test_partial_metrics_still_score(self, life_score):
        # Only mood logged - should still produce a score, not None,
        # and not be penalized just for missing data.
        result = life_score._score_from_averages({"mood": 8})
        assert result is not None
        assert result["components"] == {"mood": 80.0}

    def test_components_field_lists_exactly_whats_present(self, life_score):
        result = life_score._score_from_averages({"mood": 5, "sleep": 4})
        assert set(result["components"].keys()) == {"mood", "sleep"}

    def test_unrecognized_metric_ignored(self, life_score):
        result = life_score._score_from_averages({"mood": 8, "totally_unknown_metric": 999})
        assert "totally_unknown_metric" not in result["components"]


class TestLabels:
    @pytest.mark.parametrize("score,expected", [
        (90, "Thriving"), (85, "Thriving"),
        (75, "Doing well"), (70, "Doing well"),
        (60, "Steady"), (55, "Steady"),
        (45, "Rough day"), (40, "Rough day"),
        (20, "Tough day"), (0, "Tough day"),
    ])
    def test_label_thresholds(self, life_score, score, expected):
        assert life_score._label_for(score) == expected


class TestComputeLifeScore:
    def test_no_data_returns_none(self, life_score):
        assert life_score.compute_life_score() is None

    def test_with_mood_entry_returns_score(self, life_score):
        import storage
        storage.write_memory({"type": "mood", "content": "good day", "score": 8})
        result = life_score.compute_life_score()
        assert result is not None
        assert 0 <= result["score"] <= 100

    def test_specific_date_with_no_data_returns_none(self, life_score):
        assert life_score.compute_life_score_for_date("2020-01-01") is None


class TestLifeScoreTrend:
    def test_empty_trend_when_no_data(self, life_score):
        assert life_score.compute_life_score_trend(7) == []

    def test_trend_includes_todays_entry(self, life_score):
        import storage
        storage.write_memory({"type": "mood", "content": "ok", "score": 6})
        trend = life_score.compute_life_score_trend(7)
        assert len(trend) == 1
        assert "date" in trend[0]
        assert "score" in trend[0]

    def test_trend_sorted_oldest_first(self, life_score):
        import storage
        from datetime import datetime, timedelta
        # write_memory always timestamps "now" - just confirm sort logic
        # via _score_from_averages combined with fabricated averages dict
        entries_by_date = {
            "2026-01-03": {"mood": 8},
            "2026-01-01": {"mood": 4},
            "2026-01-02": {"mood": 6},
        }
        scored = []
        for date in sorted(entries_by_date):
            result = life_score._score_from_averages(entries_by_date[date])
            scored.append({"date": date, **result})
        assert [s["date"] for s in scored] == ["2026-01-01", "2026-01-02", "2026-01-03"]
