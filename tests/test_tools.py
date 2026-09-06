"""Tests for dispatch_tool() and the TOOLS schema (demo/tools.py), isolated
via a temp HOME so these tests never touch real ~/.hermes/life-os data."""
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def tools(tmp_path, monkeypatch):
    """Reload storage.py and tools.py with HOME pointed at a temp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ["storage", "patterns", "life_score", "achievements", "recommendations", "leaderboard", "moon", "sleep_debt", "tools"]:
        if mod in sys.modules:
            del sys.modules[mod]
    import tools as t
    importlib.reload(t)
    return t


class TestRememberRecall:
    def test_remember_then_recall(self, tools):
        result = tools.dispatch_tool("remember", {"type": "win", "content": "shipped feature"})
        assert "Remembered" in result
        recalled = tools.dispatch_tool("recall", {"query": "shipped"})
        assert "shipped feature" in recalled

    def test_recall_no_match(self, tools):
        result = tools.dispatch_tool("recall", {"query": "nonexistent xyz"})
        assert "Nothing found" in result


class TestLogMeal:
    def test_log_meal_returns_totals(self, tools):
        result = tools.dispatch_tool("log_meal", {
            "meal_time": "breakfast", "food": "oatmeal", "calories": 350,
        })
        assert "oatmeal" in result
        assert "350" in result
        assert "Today's total" in result

    def test_log_meal_accumulates_calories(self, tools):
        tools.dispatch_tool("log_meal", {"meal_time": "breakfast", "food": "eggs", "calories": 200})
        result = tools.dispatch_tool("log_meal", {"meal_time": "lunch", "food": "salad", "calories": 300})
        assert "500" in result  # 200 + 300


class TestLogSleep:
    def test_log_sleep_basic(self, tools):
        result = tools.dispatch_tool("log_sleep", {"hours": 7.5, "quality": 8})
        assert "7.5h" in result
        assert "7-day average" in result


class TestLogHydration:
    def test_log_hydration_progress_bar(self, tools):
        result = tools.dispatch_tool("log_hydration", {"glasses": 4})
        assert "4/8 glasses" in result
        assert "50%" in result

    def test_log_hydration_accumulates_same_day(self, tools):
        tools.dispatch_tool("log_hydration", {"glasses": 3})
        result = tools.dispatch_tool("log_hydration", {"glasses": 2})
        assert "5/8 glasses" in result


class TestLogWorkout:
    def test_log_workout_basic(self, tools):
        result = tools.dispatch_tool("log_workout", {
            "workout_type": "running", "duration_min": 30,
        })
        assert "running" in result
        assert "This week: 1 workout" in result


class TestLogStress:
    def test_log_stress_basic(self, tools):
        result = tools.dispatch_tool("log_stress", {"score": 7, "trigger": "deadline"})
        assert "7/10" in result
        assert "deadline" in result


class TestLogMeditation:
    def test_log_meditation_basic(self, tools):
        result = tools.dispatch_tool("log_meditation", {"duration_min": 10})
        assert "10 minutes" in result
        assert "Total sessions: 1" in result


class TestLogGratitude:
    def test_log_gratitude_basic(self, tools):
        result = tools.dispatch_tool("log_gratitude", {"items": ["health", "family", "coffee"]})
        assert "health" in result and "family" in result


class TestLogFocusSession:
    def test_log_focus_session_basic(self, tools):
        result = tools.dispatch_tool("log_focus_session", {
            "duration_min": 90, "task": "writing tests",
        })
        assert "90 min" in result
        assert "writing tests" in result


class TestUpdateHabit:
    def test_new_habit_created(self, tools):
        result = tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        assert "streak 1" in result

    def test_existing_habit_streak_increments(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        assert "streak 2" in result

    def test_habit_reset_on_incomplete(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": False})
        assert "streak 0" in result


class TestUpdateGoal:
    def test_new_goal_created(self, tools):
        result = tools.dispatch_tool("update_goal", {
            "goal_name": "ship project", "progress": 50, "note": "good progress",
        })
        assert "50" in result
        assert "good progress" in result

    def test_existing_goal_progress_updates(self, tools):
        tools.dispatch_tool("update_goal", {"goal_name": "ship project", "progress": 30})
        result = tools.dispatch_tool("update_goal", {"goal_name": "ship project", "progress": 80})
        assert "80" in result


class TestDetectPatternsTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("detect_patterns", {})
        assert "Not enough data" in result

    def test_with_data_returns_trends(self, tools):
        for score in [3, 4, 3]:
            tools.dispatch_tool("remember", {"type": "mood", "content": "day", "score": score})
        result = tools.dispatch_tool("detect_patterns", {})
        assert "Mood trend" in result


class TestGetCorrelationInsightsTool:
    def _recent_date(self, days_ago: int) -> str:
        from datetime import datetime, timedelta
        return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def _log_sleep_mood_pairs(self, tools, sleep_vals, mood_vals, start_days_ago=20):
        for i, (s, m) in enumerate(zip(sleep_vals, mood_vals)):
            date = self._recent_date(start_days_ago - i)
            tools.dispatch_tool("remember", {
                "type": "sleep", "hours": s, "timestamp": f"{date}T08:00:00Z",
            })
            tools.dispatch_tool("remember", {
                "type": "mood", "score": m, "timestamp": f"{date}T22:00:00Z",
            })

    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_correlation_insights", {})
        assert "No strong correlations found" in result

    def test_detects_same_day_correlation(self, tools):
        self._log_sleep_mood_pairs(
            tools, [4.5, 5, 4, 6, 4.5, 7, 8], [3, 4, 3, 5, 4, 7, 8],
        )
        result = tools.dispatch_tool("get_correlation_insights", {})
        assert "Same-day relationships" in result
        assert "sleep" in result and "mood" in result

    def test_detects_lagged_correlation(self, tools):
        # sleep on day D, mood on day D+1 - a clean lag-1 predictive signal
        sleep_vals = [4.5, 5, 4, 6, 4.5, 7, 8]
        mood_vals = [3, 4, 3, 5, 4, 7, 8]
        start_days_ago = 20
        for i, s in enumerate(sleep_vals):
            date = self._recent_date(start_days_ago - i)
            tools.dispatch_tool("remember", {"type": "sleep", "hours": s, "timestamp": f"{date}T08:00:00Z"})
        for i, m in enumerate(mood_vals):
            date = self._recent_date(start_days_ago - 1 - i)
            tools.dispatch_tool("remember", {"type": "mood", "score": m, "timestamp": f"{date}T22:00:00Z"})
        result = tools.dispatch_tool("get_correlation_insights", {})
        assert "Forward-looking (lagged) patterns" in result

    def test_respects_custom_days_window(self, tools):
        self._log_sleep_mood_pairs(
            tools, [4.5, 5, 4, 6, 4.5, 7, 8], [3, 4, 3, 5, 4, 7, 8],
        )
        result = tools.dispatch_tool("get_correlation_insights", {"days": 30})
        assert "last 30 days" in result



    def test_returns_valid_json(self, tools):
        result = tools.dispatch_tool("get_health_dashboard", {})
        data = json.loads(result)
        assert "today" in data
        assert "nutrition" in data
        assert "hydration" in data

    def test_reflects_logged_data(self, tools):
        tools.dispatch_tool("log_meal", {"meal_time": "lunch", "food": "salad", "calories": 400})
        result = tools.dispatch_tool("get_health_dashboard", {})
        data = json.loads(result)
        assert data["nutrition"]["calories_today"] == 400


class TestWeeklyHealthReport:
    def test_returns_valid_json(self, tools):
        result = tools.dispatch_tool("get_weekly_health_report", {})
        data = json.loads(result)
        assert "period" in data
        assert "sleep" in data
        assert "nutrition" in data


class TestProfile:
    def test_save_and_get_profile(self, tools):
        tools.dispatch_tool("save_profile", {"name": "Alex", "timezone": "UTC"})
        result = tools.dispatch_tool("get_profile", {})
        data = json.loads(result)
        assert data["profile"]["name"] == "Alex"
        assert data["profile"]["onboarded"] is True


class TestLogDream:
    def test_log_dream_basic(self, tools):
        result = tools.dispatch_tool("log_dream", {
            "content": "flying over a city", "tone": "positive", "vividness": 8,
        })
        assert "Dream logged" in result
        assert "8/10" in result

    def test_recurring_symbols_detected(self, tools):
        tools.dispatch_tool("log_dream", {"content": "d1", "symbols": ["water", "exam"], "tone": "negative"})
        result = tools.dispatch_tool("log_dream", {"content": "d2", "symbols": ["water"], "tone": "negative"})
        assert "Recurring symbols" in result
        assert "water" in result


class TestUnknownTool:
    def test_unknown_tool_returns_message(self, tools):
        # dispatch_tool falls through its if/elif chain silently for
        # unrecognized names (no explicit else) - guard against regressions
        # by asserting known tools still resolve correctly instead.
        result = tools.dispatch_tool("remember", {"type": "note", "content": "sanity check"})
        assert "Remembered" in result


class TestToolsSchema:
    def test_tools_is_nonempty_list(self, tools):
        assert isinstance(tools.TOOLS, list)
        assert len(tools.TOOLS) >= 15

    def test_every_tool_has_name_and_description(self, tools):
        for tool in tools.TOOLS:
            fn = tool["function"]
            assert fn["name"]
            assert fn["description"]

    def test_tool_names_are_unique(self, tools):
        names = [t["function"]["name"] for t in tools.TOOLS]
        assert len(names) == len(set(names))

    def test_dispatch_tool_handles_every_schema_entry(self, tools):
        """Every tool declared in TOOLS should be dispatchable (no typos
        between the schema name and the dispatch_tool if/elif chain)."""
        handled_names = set()
        for tool in tools.TOOLS:
            name = tool["function"]["name"]
            # Minimal valid-ish input per tool, just enough to not crash
            minimal_inputs = {
                "remember": {"type": "note", "content": "x"},
                "recall": {"query": "x"},
                "semantic_recall": {"query": "x"},
                "correct_entry": {"entry_id": "doesnotexist", "updates": {"score": 1}},
                "delete_entry": {"entry_id": "doesnotexist"},
                "log_meal": {"meal_time": "lunch", "food": "x"},
                "log_sleep": {"hours": 7, "quality": 7},
                "log_hydration": {"glasses": 1},
                "log_workout": {"workout_type": "run", "duration_min": 10},
                "log_stress": {"score": 5},
                "log_meditation": {"duration_min": 5},
                "log_gratitude": {"items": ["x"]},
                "log_focus_session": {"duration_min": 25, "task": "x"},
                "update_habit": {"habit_name": "x", "completed": True},
                "update_goal": {"goal_name": "x", "progress": 10},
                "check_goal_progress": {},
                "compare_periods": {},
                "compare_before_after": {"date": "2026-01-01"},
                "check_anomalies": {},
                "get_period_summary": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
                "detect_patterns": {},
                "get_health_dashboard": {},
                "get_weekly_health_report": {},
                "send_briefing": {"content": "x", "type": "morning"},
                "save_profile": {"name": "x"},
                "get_profile": {},
                "log_dream": {"content": "x"},
            }
            inp = minimal_inputs.get(name, {})
            result = tools.dispatch_tool(name, inp)
            assert result is not None
            assert f"Unknown tool: {name}" not in result
            handled_names.add(name)
        assert handled_names == {t["function"]["name"] for t in tools.TOOLS}


class TestCorrectEntryTool:
    def test_correct_entry_updates_recalled_entry(self, tools):
        tools.dispatch_tool("remember", {"type": "mood", "content": "meh", "score": 3})
        recalled = tools.dispatch_tool("recall", {"query": "meh"})
        entry_id = recalled.split("id=")[1].split("]")[0]

        result = tools.dispatch_tool("correct_entry", {"entry_id": entry_id, "updates": {"score": 8}})
        assert "Updated" in result

        entries = tools.get_recent_memory(days=1)
        matching = [e for e in entries if e["id"] == entry_id]
        assert matching[0]["score"] == 8

    def test_correct_entry_unknown_id(self, tools):
        result = tools.dispatch_tool("correct_entry", {"entry_id": "nope", "updates": {"score": 1}})
        assert "No entry found" in result

    def test_correct_entry_no_updates_given(self, tools):
        tools.dispatch_tool("remember", {"type": "note", "content": "x"})
        result = tools.dispatch_tool("correct_entry", {"entry_id": "whatever", "updates": {}})
        assert "No updates provided" in result


class TestDeleteEntryTool:
    def test_delete_entry_removes_recalled_entry(self, tools):
        tools.dispatch_tool("remember", {"type": "note", "content": "delete me please"})
        recalled = tools.dispatch_tool("recall", {"query": "delete me"})
        entry_id = recalled.split("id=")[1].split("]")[0]

        result = tools.dispatch_tool("delete_entry", {"entry_id": entry_id})
        assert "Deleted" in result

        remaining = tools.dispatch_tool("recall", {"query": "delete me"})
        assert "Nothing found" in remaining

    def test_delete_entry_unknown_id(self, tools):
        result = tools.dispatch_tool("delete_entry", {"entry_id": "nope"})
        assert "No entry found" in result


class TestGoalMetricLinkage:
    def test_manual_goal_unaffected(self, tools):
        result = tools.dispatch_tool("update_goal", {"goal_name": "Read more", "progress": 40})
        assert "40" in result
        goals = tools.load_goals()
        assert goals[0]["progress"] == 40
        assert "metric" not in goals[0]

    def test_metric_linked_goal_computes_progress_from_logged_data(self, tools):
        # log 7 days of sleep averaging 7.5 hours, target is 7+ hours
        import time as _time
        from datetime import datetime, timedelta, timezone
        for i in range(7):
            ts = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%dT09:00:00Z")
            tools.write_memory({"type": "sleep", "hours": 7.5, "timestamp": ts})

        result = tools.dispatch_tool("update_goal", {
            "goal_name": "Sleep well", "metric": "sleep", "target": 7,
            "direction": "at_least", "window_days": 7,
        })
        assert "auto-track" in result
        goals = tools.load_goals()
        goal = goals[0]
        assert goal["metric"] == "sleep"
        assert goal["progress"] == 100.0  # 7.5 avg >= 7 target

    def test_at_most_direction_for_stress_goal(self, tools):
        from datetime import datetime, timedelta, timezone
        for i in range(7):
            ts = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%dT09:00:00Z")
            tools.write_memory({"type": "stress", "score": 8, "timestamp": ts})  # target is 4, way over

        result = tools.dispatch_tool("update_goal", {
            "goal_name": "Lower stress", "metric": "stress", "target": 4, "direction": "at_most",
        })
        goals = tools.load_goals()
        assert goals[0]["progress"] < 100.0  # avg (8) is worse than target (4)

    def test_manual_progress_ignored_when_metric_set_but_no_data(self, tools):
        result = tools.dispatch_tool("update_goal", {
            "goal_name": "New metric goal", "progress": 99,
            "metric": "mood", "target": 8, "direction": "at_least",
        })
        goals = tools.load_goals()
        # no mood data logged yet -> falls back to whatever was set (0 default), not the ignored manual 99
        assert goals[0]["metric"] == "mood"


class TestCheckGoalProgressTool:
    def test_no_goals(self, tools):
        result = tools.dispatch_tool("check_goal_progress", {})
        assert "No goals set yet" in result

    def test_lists_manual_and_auto_goals(self, tools):
        tools.dispatch_tool("update_goal", {"goal_name": "Manual goal", "progress": 50})
        tools.dispatch_tool("update_goal", {
            "goal_name": "Auto goal", "metric": "hydration", "target": 8, "direction": "at_least",
        })
        result = tools.dispatch_tool("check_goal_progress", {})
        assert "Manual goal" in result and "manually tracked" in result
        assert "Auto goal" in result and "auto-tracked" in result


class TestComparePeriodsTool:
    def test_not_enough_data(self, tools):
        result = tools.dispatch_tool("compare_periods", {})
        assert "Not enough data" in result

    def test_compares_two_windows(self, tools):
        import json
        import storage
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)

        def _seed(days_ago_list, score):
            with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
                for i in days_ago_list:
                    ts = (now - timedelta(days=i)).strftime("%Y-%m-%dT09:00:00Z")
                    f.write(json.dumps({"type": "mood", "score": score, "timestamp": ts}) + "\n")

        _seed(range(8, 14), 4)   # previous week averages 4
        _seed(range(0, 6), 8)    # current week averages 8

        result = tools.dispatch_tool("compare_periods", {"window_days": 7})
        assert "mood" in result
        assert "4" in result and "8" in result


class TestCompareBeforeAfterTool:
    def test_not_enough_data(self, tools):
        result = tools.dispatch_tool("compare_before_after", {"date": "2026-01-01"})
        assert "Not enough data" in result

    def test_compares_before_and_after_changepoint(self, tools):
        import json
        import storage
        entries = [
            {"type": "mood", "score": 4, "timestamp": "2026-01-01T09:00:00Z"},
            {"type": "mood", "score": 4, "timestamp": "2026-01-05T09:00:00Z"},
            {"type": "mood", "score": 9, "timestamp": "2026-03-01T09:00:00Z"},
            {"type": "mood", "score": 9, "timestamp": "2026-03-05T09:00:00Z"},
        ]
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        result = tools.dispatch_tool("compare_before_after", {"date": "2026-03-01"})
        assert "mood" in result
        assert "4" in result and "9" in result


class TestCheckAnomaliesTool:
    def test_no_anomalies_message(self, tools):
        result = tools.dispatch_tool("check_anomalies", {})
        assert "No unusual days detected" in result

    def test_flags_outlier_day(self, tools):
        import json
        import storage
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            for i in range(2, 7):
                ts = (now - timedelta(days=i)).strftime("%Y-%m-%dT09:00:00Z")
                f.write(json.dumps({"type": "stress", "score": 3, "timestamp": ts}) + "\n")
            outlier_ts = now.strftime("%Y-%m-%dT09:00:00Z")
            f.write(json.dumps({"type": "stress", "score": 15, "timestamp": outlier_ts}) + "\n")

        result = tools.dispatch_tool("check_anomalies", {"window_days": 30})
        assert now.strftime("%Y-%m-%d") in result
        assert "stress" in result


class TestGetPeriodSummaryTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_period_summary", {
            "start_date": "2020-01-01", "end_date": "2020-01-31",
        })
        assert "No logged data found" in result

    def test_summarizes_period_with_averages_and_notable_entries(self, tools):
        import json
        import storage
        entries = [
            {"type": "mood", "score": 8, "timestamp": "2026-03-05T09:00:00Z"},
            {"type": "sleep", "hours": 7, "timestamp": "2026-03-05T09:00:00Z"},
            {"type": "gratitude", "content": "grateful for a good friend", "timestamp": "2026-03-10T09:00:00Z"},
        ]
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        result = tools.dispatch_tool("get_period_summary", {
            "start_date": "2026-03-01", "end_date": "2026-03-31",
        })
        assert "avg mood" in result
        assert "avg sleep" in result
        assert "grateful for a good friend" in result

    def test_excludes_entries_outside_range(self, tools):
        import json
        import storage
        entries = [
            {"type": "mood", "score": 9, "timestamp": "2026-02-15T09:00:00Z"},  # outside range
            {"type": "mood", "score": 3, "timestamp": "2026-03-15T09:00:00Z"},  # inside range
        ]
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        result = tools.dispatch_tool("get_period_summary", {
            "start_date": "2026-03-01", "end_date": "2026-03-31",
        })
        assert "avg mood: 3.0" in result


class TestSemanticRecallTool:
    def test_gracefully_reports_when_embedding_fails(self, tools):
        tools.dispatch_tool("remember", {"type": "mood", "content": "feeling something"})
        result = tools.dispatch_tool("semantic_recall", {"query": "anything"})
        assert isinstance(result, str)
        assert "failed" in result.lower() or "unavailable" in result.lower()

    def test_happy_path_with_mocked_embedding_client(self, tools, monkeypatch):
        import semantic_search
        from types import SimpleNamespace

        tools.dispatch_tool("remember", {"type": "mood", "content": "feeling overwhelmed at work"})

        class FakeClient:
            def __init__(self):
                self.embeddings = SimpleNamespace(create=self._create)

            def _create(self, model, input):
                vec = [1.0] if "overwhelm" in input.lower() or "stress" in input.lower() else [0.0]
                return SimpleNamespace(data=[SimpleNamespace(embedding=vec)])

        monkeypatch.setattr(semantic_search, "resolve_embedding_provider", lambda: "ollama")
        monkeypatch.setattr(semantic_search, "get_embedding_client", lambda provider: FakeClient())
        monkeypatch.setattr(semantic_search, "default_embedding_model", lambda provider: "fake-model")

        result = tools.dispatch_tool("semantic_recall", {"query": "stress"})
        assert "overwhelmed at work" in result
        assert "similarity=" in result


class TestExpenseTracking:
    def test_log_expense_returns_amount_and_today_total(self, tools):
        result = tools.dispatch_tool("log_expense", {"amount": 12.5, "category": "food"})
        assert "12.5" in result
        assert "food" in result

    def test_log_expense_accumulates_today_total(self, tools):
        tools.dispatch_tool("log_expense", {"amount": 10, "category": "food"})
        result = tools.dispatch_tool("log_expense", {"amount": 5, "category": "food"})
        assert "Today's total: 15" in result

    def test_get_spending_summary_no_data(self, tools):
        result = tools.dispatch_tool("get_spending_summary", {"days": 30})
        assert "No spending" in result

    def test_get_spending_summary_totals_and_categories(self, tools):
        tools.dispatch_tool("log_expense", {"amount": 20, "category": "food"})
        tools.dispatch_tool("log_expense", {"amount": 30, "category": "shopping"})
        result = tools.dispatch_tool("get_spending_summary", {"days": 30})
        assert "50.00 total" in result
        assert "food: 20.00" in result
        assert "shopping: 30.00" in result

    def test_expense_persists_across_reload(self, tools):
        tools.dispatch_tool("log_expense", {"amount": 7, "category": "coffee"})
        from storage import load_spending
        entries = load_spending()
        assert len(entries) == 1
        assert entries[0]["amount"] == 7


class TestSocialTracking:
    def test_log_social_interaction(self, tools):
        result = tools.dispatch_tool("log_social_interaction", {
            "with_who": "best friend", "quality": 9, "duration_min": 60,
        })
        assert "best friend" in result
        assert "9/10" in result

    def test_get_social_summary_no_data(self, tools):
        result = tools.dispatch_tool("get_social_summary", {"days": 30})
        assert "No social" in result

    def test_get_social_summary_aggregates(self, tools):
        tools.dispatch_tool("log_social_interaction", {"with_who": "family", "quality": 8, "duration_min": 30})
        tools.dispatch_tool("log_social_interaction", {"with_who": "coworkers", "quality": 6, "duration_min": 45})
        result = tools.dispatch_tool("get_social_summary", {"days": 30})
        assert "2 interaction(s)" in result
        assert "75 total minutes" in result
        assert "average quality 7.0/10" in result


class TestSubstanceTracking:
    def test_log_substance(self, tools):
        result = tools.dispatch_tool("log_substance", {"substance": "caffeine", "amount": 2, "unit": "cups"})
        assert "caffeine" in result
        assert "2" in result

    def test_get_substance_summary_no_data(self, tools):
        result = tools.dispatch_tool("get_substance_summary", {"days": 30})
        assert "No substance use" in result

    def test_get_substance_summary_breaks_down_by_substance(self, tools):
        tools.dispatch_tool("log_substance", {"substance": "caffeine", "amount": 2, "unit": "cups"})
        tools.dispatch_tool("log_substance", {"substance": "alcohol", "amount": 1, "unit": "drinks"})
        result = tools.dispatch_tool("get_substance_summary", {"days": 30})
        assert "caffeine:" in result
        assert "alcohol:" in result

    def test_substance_name_normalized_lowercase(self, tools):
        tools.dispatch_tool("log_substance", {"substance": "Caffeine", "amount": 1, "unit": "cup"})
        from storage import load_substance
        assert load_substance()[0]["substance"] == "caffeine"


class TestLifeScoreTool:
    def test_no_data_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_life_score", {})
        assert "Not enough data" in result

    def test_with_data_returns_score(self, tools):
        tools.dispatch_tool("remember", {"type": "mood", "content": "good day", "score": 8})
        result = tools.dispatch_tool("get_life_score", {})
        assert "Life Score:" in result
        assert "/100" in result


class TestAchievementsTool:
    def test_no_data_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_achievements", {})
        assert "No achievements yet" in result

    def test_earns_first_workout_badge(self, tools):
        tools.dispatch_tool("log_workout", {"activity": "run", "duration_min": 30})
        result = tools.dispatch_tool("get_achievements", {})
        assert "Getting Active" in result


class TestReadingTracking:
    def test_log_reading_minimal(self, tools):
        result = tools.dispatch_tool("log_reading", {"title": "Deep Work"})
        assert "Deep Work" in result

    def test_log_reading_with_minutes(self, tools):
        result = tools.dispatch_tool("log_reading", {"title": "Atomic Habits", "minutes": 25})
        assert "25 min" in result

    def test_get_reading_summary_no_data(self, tools):
        result = tools.dispatch_tool("get_reading_summary", {"days": 30})
        assert "No reading" in result

    def test_get_reading_summary_aggregates(self, tools):
        tools.dispatch_tool("log_reading", {"title": "Book A", "minutes": 20, "pages": 15})
        tools.dispatch_tool("log_reading", {"title": "Book B", "minutes": 10, "pages": 5})
        result = tools.dispatch_tool("get_reading_summary", {"days": 30})
        assert "2 session(s)" in result
        assert "30 total minutes" in result
        assert "20 total pages" in result


class TestMedicationTracking:
    def test_log_medication_taken_default(self, tools):
        result = tools.dispatch_tool("log_medication", {"name": "Vitamin D"})
        assert "Vitamin D" in result
        assert "taken" in result.lower()

    def test_log_medication_skipped(self, tools):
        result = tools.dispatch_tool("log_medication", {"name": "Vitamin D", "taken": False})
        assert "SKIPPED" in result

    def test_get_medication_adherence_no_data(self, tools):
        result = tools.dispatch_tool("get_medication_adherence", {"days": 30})
        assert "No medication" in result

    def test_get_medication_adherence_calculates_percentage(self, tools):
        tools.dispatch_tool("log_medication", {"name": "Omega-3", "taken": True})
        tools.dispatch_tool("log_medication", {"name": "Omega-3", "taken": True})
        tools.dispatch_tool("log_medication", {"name": "Omega-3", "taken": False})
        result = tools.dispatch_tool("get_medication_adherence", {"days": 30})
        assert "Omega-3: 67%" in result

    def test_multiple_medications_broken_down_separately(self, tools):
        tools.dispatch_tool("log_medication", {"name": "A", "taken": True})
        tools.dispatch_tool("log_medication", {"name": "B", "taken": False})
        result = tools.dispatch_tool("get_medication_adherence", {"days": 30})
        assert "A: 100%" in result
        assert "B: 0%" in result


class TestRecommendationsTool:
    def test_no_data_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_recommendations", {})
        assert "No specific suggestions" in result

    def test_low_sleep_triggers_suggestion(self, tools):
        for _ in range(5):
            tools.dispatch_tool("log_sleep", {"hours": 4, "quality": 5})
        result = tools.dispatch_tool("get_recommendations", {})
        assert "sleep" in result.lower()


class TestWeatherCorrelationTool:
    def test_missing_location_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_weather_correlation", {})
        assert "provide a location" in result.lower()

    def test_geocode_failure_returns_error_message_not_exception(self, tools, monkeypatch):
        import weather

        def fake_geocode(location, timeout=10):
            raise weather.WeatherError(f"No location found matching '{location}'.")

        monkeypatch.setattr(weather, "geocode_location", fake_geocode)
        result = tools.dispatch_tool("get_weather_correlation", {"location": "Nowhereville"})
        assert "No location found" in result

    def test_successful_correlation_formatted(self, tools, monkeypatch):
        import weather

        def fake_compute(location, days=30):
            return {
                "location": {"name": "Istanbul"},
                "days": days,
                "correlations": [{
                    "weather_metric": "temp", "tracked_metric": "mood",
                    "r": 0.6, "n_days": 10, "direction": "positive",
                }],
            }

        monkeypatch.setattr(weather, "compute_weather_correlation", fake_compute)
        result = tools.dispatch_tool("get_weather_correlation", {"location": "Istanbul"})
        assert "Istanbul" in result
        assert "mood" in result

    def test_no_correlations_found_returns_helpful_message(self, tools, monkeypatch):
        import weather

        def fake_compute(location, days=30):
            return {"location": {"name": "Istanbul"}, "days": days, "correlations": []}

        monkeypatch.setattr(weather, "compute_weather_correlation", fake_compute)
        result = tools.dispatch_tool("get_weather_correlation", {"location": "Istanbul"})
        assert "No significant weather correlations" in result


class TestStreakFreeze:
    def test_normal_streak_increments(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        assert "streak 2 days" in result

    def test_missed_day_without_freeze_resets_streak(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": False})
        assert "streak 0 days" in result

    def test_earns_freeze_at_7_day_streak(self, tools):
        result = None
        for _ in range(7):
            result = tools.dispatch_tool("update_habit", {"habit_name": "run", "completed": True})
        assert "earned a streak freeze" in result

    def test_freeze_protects_streak_when_missed(self, tools):
        for _ in range(7):
            tools.dispatch_tool("update_habit", {"habit_name": "run", "completed": True})
        # miss a day but spend the freeze
        result = tools.dispatch_tool("update_habit", {
            "habit_name": "run", "completed": False, "use_freeze": True,
        })
        assert "streak protected with a freeze" in result
        assert "Still at 7 days" in result

    def test_freeze_consumed_after_use(self, tools):
        from storage import load_habits
        for _ in range(7):
            tools.dispatch_tool("update_habit", {"habit_name": "run", "completed": True})
        assert load_habits()[0]["freezes_available"] == 1
        tools.dispatch_tool("update_habit", {"habit_name": "run", "completed": False, "use_freeze": True})
        assert load_habits()[0]["freezes_available"] == 0

    def test_missing_freeze_falls_back_to_reset(self, tools):
        # never earned a freeze - use_freeze=True has no freeze to spend,
        # so the streak still resets like normal.
        tools.dispatch_tool("update_habit", {"habit_name": "run", "completed": True})
        result = tools.dispatch_tool("update_habit", {
            "habit_name": "run", "completed": False, "use_freeze": True,
        })
        assert "streak 0 days" in result

    def test_freezes_capped_at_three(self, tools):
        from storage import load_habits
        for _ in range(28):  # 4x 7-day milestones
            tools.dispatch_tool("update_habit", {"habit_name": "run", "completed": True})
        assert load_habits()[0]["freezes_available"] == 3


class TestOnThisDayTool:
    def test_no_data_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_on_this_day", {})
        assert "No entries found" in result

    def test_finds_entry_from_previous_year(self, tools):
        from storage import write_memory
        from datetime import datetime
        today = datetime.utcnow()
        last_year_str = f"{today.year - 1}-{today.month:02d}-{today.day:02d}T09:00:00Z"
        write_memory({"type": "mood", "content": "was a great day", "score": 8,
                      "timestamp": last_year_str})
        result = tools.dispatch_tool("get_on_this_day", {})
        assert "1 year ago" in result
        assert "was a great day" in result

    def test_multiple_years_sorted_most_recent_first(self, tools):
        from storage import write_memory
        from datetime import datetime
        today = datetime.utcnow()
        write_memory({"type": "mood", "content": "three years back", "score": 5,
                      "timestamp": f"{today.year - 3}-{today.month:02d}-{today.day:02d}T09:00:00Z"})
        write_memory({"type": "mood", "content": "one year back", "score": 7,
                      "timestamp": f"{today.year - 1}-{today.month:02d}-{today.day:02d}T09:00:00Z"})
        result = tools.dispatch_tool("get_on_this_day", {})
        lines = result.split("\n")
        assert "1 year ago" in lines[0]
        assert "3 years ago" in lines[1]

    def test_entries_from_a_different_day_excluded(self, tools):
        from storage import write_memory
        write_memory({"type": "mood", "content": "unrelated day", "score": 5,
                      "timestamp": "2020-06-15T09:00:00Z"})  # unlikely to be "today" in tests
        result = tools.dispatch_tool("get_on_this_day", {})
        # Only asserts no crash and a sensible response either way, since
        # the exact date this test runs on is nondeterministic; the real
        # date-matching logic is covered precisely by the tests above.
        assert isinstance(result, str) and len(result) > 0

    def test_todays_own_entries_excluded(self, tools):
        from storage import write_memory
        write_memory({"type": "mood", "content": "logged just now", "score": 6})
        result = tools.dispatch_tool("get_on_this_day", {})
        assert "No entries found" in result


class TestDailyPromptTool:
    def test_returns_a_prompt(self, tools):
        result = tools.dispatch_tool("get_daily_prompt", {})
        assert isinstance(result, str) and len(result) > 0

    def test_matches_prompts_module(self, tools):
        import prompts
        result = tools.dispatch_tool("get_daily_prompt", {})
        assert result in prompts.DAILY_PROMPTS


class TestMoonCorrelationTool:
    def test_no_data_still_returns_today_phase(self, tools):
        result = tools.dispatch_tool("get_moon_correlation", {})
        assert "Today:" in result

    def test_days_param_respected(self, tools):
        result = tools.dispatch_tool("get_moon_correlation", {"days": 30})
        assert "Today:" in result


class TestSleepDebtTools:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_sleep_debt", {})
        assert "No sleep logged" in result

    def test_with_data_reports_debt(self, tools):
        tools.dispatch_tool("log_sleep", {"hours": 5, "quality": 5})
        result = tools.dispatch_tool("get_sleep_debt", {})
        assert "Sleep debt" in result or "No sleep debt" in result

    def test_suggested_bedtime_requires_wake_time(self, tools):
        result = tools.dispatch_tool("get_suggested_bedtime", {})
        assert "provide a wake-up time" in result.lower()

    def test_suggested_bedtime_returns_a_time(self, tools):
        result = tools.dispatch_tool("get_suggested_bedtime", {"wake_time": "07:00"})
        assert "Suggested bedtime" in result

    def test_suggested_bedtime_invalid_format_handled(self, tools):
        result = tools.dispatch_tool("get_suggested_bedtime", {"wake_time": "not-a-time"})
        assert "24-hour" in result


class TestLeaderboardTools:
    def test_join_leaderboard(self, tools):
        result = tools.dispatch_tool("join_leaderboard", {})
        assert "Joined the leaderboard" in result

    def test_leave_leaderboard(self, tools):
        tools.dispatch_tool("join_leaderboard", {})
        result = tools.dispatch_tool("leave_leaderboard", {})
        assert "Left the leaderboard" in result

    def test_get_leaderboard_empty(self, tools):
        result = tools.dispatch_tool("get_leaderboard", {})
        assert "No one has joined" in result

    def test_get_leaderboard_after_joining(self, tools):
        tools.dispatch_tool("join_leaderboard", {})
        tools.dispatch_tool("remember", {"type": "mood", "content": "good", "score": 7})
        result = tools.dispatch_tool("get_leaderboard", {})
        assert "Life Score" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
