"""Tests for demo/recommendations.py - the rule-based suggestion
engine."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def recommendations(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "recommendations"):
        if mod in sys.modules:
            del sys.modules[mod]
    import recommendations as rec
    importlib.reload(rec)
    import storage
    storage.set_active_profile(None)
    return rec


class TestThresholdSuggestions:
    def test_no_data_no_suggestions(self, recommendations):
        assert recommendations._threshold_suggestions({}) == []

    def test_low_sleep_triggers_suggestion(self, recommendations):
        daily = {"2026-01-01": {"sleep": 5.0}, "2026-01-02": {"sleep": 5.5}}
        suggestions = recommendations._threshold_suggestions(daily)
        assert any(s["metric"] == "sleep" for s in suggestions)

    def test_good_sleep_no_suggestion(self, recommendations):
        daily = {"2026-01-01": {"sleep": 8.0}, "2026-01-02": {"sleep": 7.5}}
        suggestions = recommendations._threshold_suggestions(daily)
        assert not any(s["metric"] == "sleep" for s in suggestions)

    def test_high_stress_triggers_suggestion(self, recommendations):
        daily = {"2026-01-01": {"stress": 8.0}, "2026-01-02": {"stress": 9.0}}
        suggestions = recommendations._threshold_suggestions(daily)
        assert any(s["metric"] == "stress" for s in suggestions)

    def test_low_stress_no_suggestion(self, recommendations):
        daily = {"2026-01-01": {"stress": 2.0}}
        suggestions = recommendations._threshold_suggestions(daily)
        assert not any(s["metric"] == "stress" for s in suggestions)

    def test_low_hydration_triggers_suggestion(self, recommendations):
        daily = {"2026-01-01": {"hydration": 2.0}}
        suggestions = recommendations._threshold_suggestions(daily)
        assert any(s["metric"] == "hydration" for s in suggestions)

    def test_message_includes_actual_value(self, recommendations):
        daily = {"2026-01-01": {"sleep": 5.0}}
        suggestions = recommendations._threshold_suggestions(daily)
        sleep_suggestion = next(s for s in suggestions if s["metric"] == "sleep")
        assert "5.0" in sleep_suggestion["message"]


class TestStreakSuggestions:
    def test_no_habits_no_suggestions(self, recommendations):
        assert recommendations._streak_suggestions([]) == []

    def test_near_7_day_milestone_triggers(self, recommendations):
        habits = [{"name": "meditate", "streak": 6}]
        suggestions = recommendations._streak_suggestions(habits)
        assert len(suggestions) == 1
        assert suggestions[0]["days_left"] == 1
        assert "meditate" in suggestions[0]["message"]

    def test_far_from_milestone_no_suggestion(self, recommendations):
        habits = [{"name": "meditate", "streak": 1}]
        assert recommendations._streak_suggestions(habits) == []

    def test_already_past_milestone_no_suggestion_for_that_one(self, recommendations):
        # streak of 8 is past the 7-day milestone and not near 30 yet
        habits = [{"name": "meditate", "streak": 8}]
        assert recommendations._streak_suggestions(habits) == []

    def test_multiple_habits_each_evaluated(self, recommendations):
        habits = [
            {"name": "run", "streak": 29},
            {"name": "read", "streak": 1},
        ]
        suggestions = recommendations._streak_suggestions(habits)
        assert len(suggestions) == 1
        assert suggestions[0]["habit"] == "run"
        assert suggestions[0]["days_left"] == 1


class TestGetRecommendations:
    def test_no_data_returns_empty_list(self, recommendations):
        assert recommendations.get_recommendations() == []

    def test_combines_threshold_and_streak_suggestions(self, recommendations):
        import storage
        for _ in range(3):
            storage.write_memory({"type": "sleep", "content": "slept", "hours": 4.5})
        storage.save_habits([{"name": "meditate", "streak": 6}])
        suggestions = recommendations.get_recommendations()
        types = {s["type"] for s in suggestions}
        assert "threshold" in types
        assert "streak" in types

    def test_every_suggestion_has_a_message(self, recommendations):
        import storage
        storage.save_habits([{"name": "run", "streak": 29}])
        for s in recommendations.get_recommendations():
            assert "message" in s and isinstance(s["message"], str) and s["message"]
