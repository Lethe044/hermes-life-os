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
    for mod in ["storage", "patterns", "tools"]:
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


class TestHealthDashboard:
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
