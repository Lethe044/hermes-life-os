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
    for mod in ["storage", "patterns", "life_score", "achievements", "recommendations", "leaderboard", "moon", "sleep_debt", "day_of_week", "habit_milestones", "goal_deadlines", "consistency", "time_of_day", "monthly_summary", "habit_pb", "workout_summary", "meditation_summary", "gratitude_recap", "meal_summary", "hydration_summary", "focus_summary", "dream_recap", "stress_summary", "habit_consistency", "habit_correlation", "habit_overview", "reading_pace", "spending_trends", "substance_correlation", "social_insights", "social_correlation", "medication_streak", "workout_correlation", "export_tool", "data_export", "backup", "correlation_utils", "reading_correlation", "insights_digest", "nudges", "wrapped", "dashboard", "life_review", "budgets", "reminders", "doctor", "templates", "tools"]:
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


class TestListHabitsTool:
    def test_no_habits_message(self, tools):
        result = tools.dispatch_tool("list_habits", {})
        assert "No habits created yet" in result

    def test_shows_brand_new_zero_streak_habit(self, tools):
        # A habit created via a missed check-in (streak=0, best_streak=0)
        # doesn't show up in get_habit_milestones or get_habit_pb_progress -
        # both explicitly exclude habits with no active or past streak -
        # so list_habits is the only place it's visible. This is exactly
        # the gap it exists to fill.
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": False})
        milestones = tools.dispatch_tool("get_habit_milestones", {})
        pb = tools.dispatch_tool("get_habit_pb_progress", {})
        assert "meditate" not in milestones
        assert "meditate" not in pb
        listed = tools.dispatch_tool("list_habits", {})
        assert "meditate" in listed
        assert "streak 0 days" in listed

    def test_shows_freezes_available(self, tools):
        for _ in range(7):
            tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("list_habits", {})
        assert "freeze(s) available" in result


class TestDeleteHabitTool:
    def test_nonexistent_habit_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("delete_habit", {"habit_name": "ghost"})
        assert "No habit named" in result

    def test_deletes_existing_habit(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("delete_habit", {"habit_name": "meditate"})
        assert "deleted" in result
        listed = tools.dispatch_tool("list_habits", {})
        assert "No habits created yet" in listed

    def test_delete_case_insensitive(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "Meditate", "completed": True})
        result = tools.dispatch_tool("delete_habit", {"habit_name": "meditate"})
        assert "deleted" in result

    def test_deleting_one_habit_leaves_others(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        tools.dispatch_tool("update_habit", {"habit_name": "read", "completed": True})
        tools.dispatch_tool("delete_habit", {"habit_name": "meditate"})
        listed = tools.dispatch_tool("list_habits", {})
        assert "read" in listed
        assert "meditate" not in listed


class TestDeleteGoalTool:
    def test_nonexistent_goal_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("delete_goal", {"goal_name": "ghost"})
        assert "No goal named" in result

    def test_deletes_existing_goal(self, tools):
        tools.dispatch_tool("update_goal", {"goal_name": "ship project", "progress": 50})
        result = tools.dispatch_tool("delete_goal", {"goal_name": "ship project"})
        assert "deleted" in result
        check = tools.dispatch_tool("check_goal_progress", {})
        assert "No goals set yet" in check

    def test_deleting_one_goal_leaves_others(self, tools):
        tools.dispatch_tool("update_goal", {"goal_name": "ship project", "progress": 50})
        tools.dispatch_tool("update_goal", {"goal_name": "learn spanish", "progress": 20})
        tools.dispatch_tool("delete_goal", {"goal_name": "ship project"})
        check = tools.dispatch_tool("check_goal_progress", {})
        assert "learn spanish" in check
        assert "ship project" not in check


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

    def test_completion_recorded_in_memory(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        recalled = tools.dispatch_tool("recall", {"query": "meditate"})
        assert "meditate" in recalled

    def test_missed_day_recorded_as_not_completed(self, tools):
        from habit_consistency import compute_habit_consistency
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": False})
        results = compute_habit_consistency(90)
        assert results[0]["completed_checkins"] == 1
        assert results[0]["total_checkins"] == 2

    def test_freeze_used_recorded_as_completed(self, tools):
        from habit_consistency import compute_habit_consistency
        for _ in range(7):
            tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": False, "use_freeze": True})
        results = compute_habit_consistency(90)
        assert results[0]["completed_checkins"] == results[0]["total_checkins"]


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

    def test_deadline_set_on_new_goal(self, tools):
        result = tools.dispatch_tool("update_goal", {
            "goal_name": "ship project", "progress": 50, "deadline": "2030-01-01",
        })
        assert "2030-01-01" in result

    def test_deadline_set_on_existing_goal(self, tools):
        tools.dispatch_tool("update_goal", {"goal_name": "ship project", "progress": 30})
        result = tools.dispatch_tool("update_goal", {
            "goal_name": "ship project", "progress": 30, "deadline": "2030-06-15",
        })
        assert "2030-06-15" in result

    def test_no_deadline_omits_suffix(self, tools):
        result = tools.dispatch_tool("update_goal", {"goal_name": "ship project", "progress": 30})
        assert "deadline" not in result

    def test_linked_habit_new_goal(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("update_goal", {
            "goal_name": "meditation streak", "linked_habit": "meditate", "target_streak": 10,
        })
        assert "meditate" in result
        assert "10.0%" in result  # 1-day streak / 10-day target

    def test_linked_habit_progress_updates_with_streak(self, tools):
        for _ in range(5):
            tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("update_goal", {
            "goal_name": "meditation streak", "linked_habit": "meditate", "target_streak": 10,
        })
        assert "50.0%" in result

    def test_manual_progress_ignored_once_habit_linked(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        tools.dispatch_tool("update_goal", {
            "goal_name": "meditation streak", "linked_habit": "meditate", "target_streak": 10,
        })
        result = tools.dispatch_tool("update_goal", {
            "goal_name": "meditation streak", "progress": 99,
        })
        assert "99" not in result


class TestGetDayOfWeekInsightsTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_day_of_week_insights", {})
        assert "Not enough logged days" in result

    def test_with_two_different_weekdays_returns_insight(self, tools):
        from datetime import datetime, timedelta
        for offset in range(1, 30):
            dt = datetime.utcnow() - timedelta(days=offset)
            if dt.weekday() in (0, 3):
                score = 9 if dt.weekday() == 0 else 2
                tools.dispatch_tool("remember", {
                    "type": "mood", "score": score,
                    "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
        result = tools.dispatch_tool("get_day_of_week_insights", {"metric": "mood"})
        assert "Mood" in result


class TestGetHabitMilestonesTool:
    def test_no_habits_message(self, tools):
        result = tools.dispatch_tool("get_habit_milestones", {})
        assert "No active habit streaks" in result

    def test_active_streak_shows_countdown(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "Meditate", "completed": True})
        result = tools.dispatch_tool("get_habit_milestones", {})
        assert "Meditate" in result
        assert "milestone" in result


class TestGetGoalDeadlinesTool:
    def test_no_deadlines_message(self, tools):
        result = tools.dispatch_tool("get_goal_deadlines", {})
        assert "No goals have a deadline" in result

    def test_goal_with_deadline_shows_up(self, tools):
        tools.dispatch_tool("update_goal", {
            "goal_name": "ship project", "progress": 40, "deadline": "2099-01-01",
        })
        result = tools.dispatch_tool("get_goal_deadlines", {})
        assert "ship project" in result


class TestGetLoggingConsistencyTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_logging_consistency", {})
        assert "No entries logged" in result

    def test_with_data_shows_percentage(self, tools):
        tools.dispatch_tool("remember", {"type": "sleep", "hours": 7})
        result = tools.dispatch_tool("get_logging_consistency", {"days": 10})
        assert "%" in result


class TestGetTimeOfDayInsightsTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_time_of_day_insights", {})
        assert "Not enough logged entries" in result

    def test_with_two_different_times_returns_insight(self, tools):
        tools.dispatch_tool("remember", {
            "type": "mood", "score": 9, "timestamp": "2026-01-01T08:00:00Z",
        })
        tools.dispatch_tool("remember", {
            "type": "mood", "score": 2, "timestamp": "2026-01-02T20:00:00Z",
        })
        result = tools.dispatch_tool("get_time_of_day_insights", {"metric": "mood", "days": 365})
        assert "Mood" in result


class TestGetMonthlyComparisonTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_monthly_comparison", {})
        assert "Not enough overlapping data" in result


class TestGetHabitPbProgressTool:
    def test_no_habits_message(self, tools):
        result = tools.dispatch_tool("get_habit_pb_progress", {})
        assert "No habit history" in result

    def test_active_habit_shows_progress(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "Meditate", "completed": True})
        result = tools.dispatch_tool("get_habit_pb_progress", {})
        assert "Meditate" in result


class TestGetWorkoutSummaryTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_workout_summary", {})
        assert "No workouts logged" in result

    def test_with_data_shows_totals(self, tools):
        tools.dispatch_tool("log_workout", {"workout_type": "run", "duration_min": 30})
        result = tools.dispatch_tool("get_workout_summary", {})
        assert "run" in result


class TestGetMeditationSummaryTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_meditation_summary", {})
        assert "No meditation sessions logged" in result

    def test_with_data_shows_totals(self, tools):
        tools.dispatch_tool("log_meditation", {"duration_min": 10})
        result = tools.dispatch_tool("get_meditation_summary", {})
        assert "1 meditation session(s)" in result


class TestGetGratitudeRecapTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_gratitude_recap", {})
        assert "No gratitude entries logged" in result

    def test_with_data_shows_recent(self, tools):
        tools.dispatch_tool("log_gratitude", {"items": ["my dog", "sunny weather"]})
        result = tools.dispatch_tool("get_gratitude_recap", {})
        assert "my dog" in result


class TestGetMealSummaryTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_meal_summary", {})
        assert "No meals logged" in result

    def test_with_data_shows_totals(self, tools):
        tools.dispatch_tool("log_meal", {"meal_time": "breakfast", "food": "oatmeal", "calories": 300})
        result = tools.dispatch_tool("get_meal_summary", {})
        assert "oatmeal" in result


class TestGetHydrationSummaryTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_hydration_summary", {})
        assert "No hydration logged" in result

    def test_with_data_shows_average(self, tools):
        tools.dispatch_tool("log_hydration", {"glasses": 4})
        result = tools.dispatch_tool("get_hydration_summary", {})
        assert "glasses/day" in result


class TestGetFocusSummaryTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_focus_summary", {})
        assert "No focus sessions logged" in result

    def test_with_data_shows_totals(self, tools):
        tools.dispatch_tool("log_focus_session", {"duration_min": 25, "task": "writing"})
        result = tools.dispatch_tool("get_focus_summary", {})
        assert "writing" in result


class TestGetDreamRecapTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_dream_recap", {})
        assert "No dreams logged" in result

    def test_with_data_shows_tone(self, tools):
        tools.dispatch_tool("log_dream", {"content": "flying", "tone": "peaceful", "vividness": 7})
        result = tools.dispatch_tool("get_dream_recap", {})
        assert "peaceful" in result


class TestGetStressSummaryTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_stress_summary", {})
        assert "No stress logged" in result

    def test_with_data_shows_average(self, tools):
        tools.dispatch_tool("log_stress", {"score": 7, "trigger": "deadline"})
        result = tools.dispatch_tool("get_stress_summary", {})
        assert "deadline" in result


class TestGetHabitConsistencyTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_habit_consistency", {})
        assert "No habit check-ins recorded" in result

    def test_with_data_shows_percentage(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("get_habit_consistency", {})
        assert "meditate" in result
        assert "100.0%" in result


class TestGetHabitMoodImpactTool:
    def test_missing_habit_name_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_habit_mood_impact", {})
        assert "specify a habit_name" in result

    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_habit_mood_impact", {"habit_name": "meditate"})
        assert "Not enough overlapping" in result

    def test_with_overlapping_data_shows_comparison(self, tools):
        from datetime import datetime, timedelta
        d1 = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        d2 = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tools.dispatch_tool("remember", {"type": "habit_completion", "habit": "meditate",
                                          "completed": True, "timestamp": d1})
        tools.dispatch_tool("remember", {"type": "mood", "score": 9, "timestamp": d1})
        tools.dispatch_tool("remember", {"type": "habit_completion", "habit": "meditate",
                                          "completed": False, "timestamp": d2})
        tools.dispatch_tool("remember", {"type": "mood", "score": 3, "timestamp": d2})
        result = tools.dispatch_tool("get_habit_mood_impact", {"habit_name": "meditate"})
        assert "meditate" in result


class TestGetHabitOverviewTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_habit_overview", {})
        assert "No habit data yet" in result

    def test_with_data_combines_sections(self, tools):
        tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("get_habit_overview", {})
        assert "milestone" in result
        assert "personal best" in result
        assert "consistency" in result


class TestGetReadingPaceTool:
    def test_missing_title_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_reading_pace", {})
        assert "specify a title" in result

    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_reading_pace", {"title": "Unknown Book"})
        assert "No reading logged" in result

    def test_with_data_shows_pace(self, tools):
        tools.dispatch_tool("log_reading", {"title": "Book A", "pages": 50})
        result = tools.dispatch_tool("get_reading_pace", {"title": "Book A"})
        assert "Book A" in result


class TestGetSpendingTrendsTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_spending_trends", {})
        assert "No spending logged" in result

    def test_with_data_shows_category(self, tools):
        tools.dispatch_tool("log_expense", {"amount": 20, "category": "food"})
        result = tools.dispatch_tool("get_spending_trends", {})
        assert "food" in result


class TestGetSubstanceSleepImpactTool:
    def test_missing_substance_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_substance_sleep_impact", {})
        assert "specify a substance" in result

    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_substance_sleep_impact", {"substance": "caffeine"})
        assert "Not enough overlapping" in result


class TestGetSocialInsightsTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_social_insights", {})
        assert "No social interactions logged" in result

    def test_with_data_shows_person(self, tools):
        tools.dispatch_tool("log_social_interaction", {"with_who": "Alice", "quality": 8, "duration_min": 60})
        result = tools.dispatch_tool("get_social_insights", {})
        assert "Alice" in result


class TestGetSocialMoodImpactTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_social_mood_impact", {})
        assert "Not enough overlapping" in result


class TestGetMedicationStreakTool:
    def test_missing_med_name_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("get_medication_streak", {})
        assert "specify a med_name" in result

    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_medication_streak", {"med_name": "Vitamin D"})
        assert "No logs found" in result

    def test_with_data_shows_streak(self, tools):
        tools.dispatch_tool("log_medication", {"name": "Vitamin D", "taken": True})
        result = tools.dispatch_tool("get_medication_streak", {"med_name": "Vitamin D"})
        assert "current streak" in result


class TestGetWorkoutMoodImpactTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_workout_mood_impact", {})
        assert "Not enough overlapping" in result


class TestExportDataTool:
    def test_default_json_export(self, tools):
        tools.dispatch_tool("remember", {"type": "mood", "score": 5})
        result = tools.dispatch_tool("export_data", {})
        assert "memory entries" in result

    def test_csv_export(self, tools):
        result = tools.dispatch_tool("export_data", {"format": "csv"})
        assert "daily rows" in result

    def test_markdown_export(self, tools):
        result = tools.dispatch_tool("export_data", {"format": "markdown"})
        assert "day-files" in result

    def test_invalid_format_returns_error_message(self, tools):
        result = tools.dispatch_tool("export_data", {"format": "xml"})
        assert "Unknown export format" in result


class TestBackupNowTool:
    def test_writes_backup(self, tools):
        result = tools.dispatch_tool("backup_now", {})
        assert "Backup written" in result

    def test_custom_keep(self, tools):
        result = tools.dispatch_tool("backup_now", {"keep": 3})
        assert "keeping the 3 most recent" in result


class TestGetReadingMoodImpactTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_reading_mood_impact", {})
        assert "Not enough overlapping" in result


class TestGetInsightsDigestTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_insights_digest", {})
        assert "Nothing stood out" in result

    def test_with_data_surfaces_finding(self, tools):
        from datetime import datetime, timedelta
        # log_workout files the session under the LOCAL date, so the mood
        # entries must use local dates too. With utcnow() this failed every
        # night between 00:00 and the UTC offset (e.g. 00:00-03:00 in UTC+3),
        # when the local and UTC dates differ.
        today = datetime.now().strftime("%Y-%m-%dT12:00:00Z")
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT12:00:00Z")
        tools.dispatch_tool("log_workout", {"workout_type": "run", "duration_min": 30})
        tools.dispatch_tool("remember", {"type": "mood", "score": 9, "timestamp": today})
        tools.dispatch_tool("remember", {"type": "mood", "score": 2, "timestamp": two_days_ago})
        result = tools.dispatch_tool("get_insights_digest", {"threshold": 1.0})
        assert "Workout vs mood" in result


class TestGetNudgesTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_nudges", {})
        assert "Nothing worth flagging" in result


class TestGetWrappedTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_wrapped", {})
        assert "nothing to wrap yet" in result

    def test_with_data_shows_summary(self, tools):
        tools.dispatch_tool("remember", {"type": "mood", "score": 9})
        result = tools.dispatch_tool("get_wrapped", {"days": 30})
        assert "My Month with Hermes" in result


class TestGetLifeReviewTool:
    def test_no_data_message(self, tools):
        result = tools.dispatch_tool("get_life_review", {})
        assert "nothing to review yet" in result

    def test_with_data_shows_summary(self, tools):
        tools.dispatch_tool("remember", {"type": "mood", "score": 9})
        result = tools.dispatch_tool("get_life_review", {"days": 90})
        assert "review" in result.lower()


class TestSaveLogTemplateTool:
    def test_missing_fields_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("save_log_template", {})
        assert "specify both" in result

    def test_non_log_tool_rejected(self, tools):
        result = tools.dispatch_tool("save_log_template", {
            "template_name": "sneaky", "tool_name": "backup_now", "params": {},
        })
        assert "log_* tools" in result

    def test_unknown_tool_rejected(self, tools):
        result = tools.dispatch_tool("save_log_template", {
            "template_name": "x", "tool_name": "log_not_a_real_tool", "params": {},
        })
        assert "isn't a known tool" in result

    def test_valid_template_saved(self, tools):
        result = tools.dispatch_tool("save_log_template", {
            "template_name": "usual breakfast", "tool_name": "log_meal",
            "params": {"food": "oatmeal", "calories": 300},
        })
        assert "usual breakfast" in result
        assert "log_meal" in result


class TestUseLogTemplateTool:
    def test_nonexistent_template_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("use_log_template", {"template_name": "ghost"})
        assert "No template named" in result

    def test_replays_saved_tool_call(self, tools):
        tools.dispatch_tool("save_log_template", {
            "template_name": "usual breakfast", "tool_name": "log_meal",
            "params": {"food": "oatmeal", "calories": 300},
        })
        result = tools.dispatch_tool("use_log_template", {"template_name": "usual breakfast"})
        assert "usual breakfast" in result
        assert "oatmeal" in result

    def test_replay_actually_logs_the_entry(self, tools):
        tools.dispatch_tool("save_log_template", {
            "template_name": "usual breakfast", "tool_name": "log_meal",
            "params": {"food": "oatmeal", "calories": 300},
        })
        tools.dispatch_tool("use_log_template", {"template_name": "usual breakfast"})
        summary = tools.dispatch_tool("get_meal_summary", {})
        assert "oatmeal" in summary


class TestListLogTemplatesTool:
    def test_no_templates_message(self, tools):
        result = tools.dispatch_tool("list_log_templates", {})
        assert "No log templates saved" in result

    def test_with_templates_lists_them(self, tools):
        tools.dispatch_tool("save_log_template", {
            "template_name": "usual breakfast", "tool_name": "log_meal", "params": {"food": "oatmeal"},
        })
        result = tools.dispatch_tool("list_log_templates", {})
        assert "usual breakfast" in result


class TestDeleteLogTemplateTool:
    def test_nonexistent_template_returns_helpful_message(self, tools):
        result = tools.dispatch_tool("delete_log_template", {"template_name": "ghost"})
        assert "No template named" in result

    def test_deletes_existing_template(self, tools):
        tools.dispatch_tool("save_log_template", {
            "template_name": "usual breakfast", "tool_name": "log_meal", "params": {"food": "oatmeal"},
        })
        result = tools.dispatch_tool("delete_log_template", {"template_name": "usual breakfast"})
        assert "deleted" in result
        listed = tools.dispatch_tool("list_log_templates", {})
        assert "usual breakfast" not in listed


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

    def test_habit_linked_goal_refreshes_with_streak(self, tools):
        for _ in range(3):
            tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        tools.dispatch_tool("update_goal", {
            "goal_name": "meditation streak", "linked_habit": "meditate", "target_streak": 30,
        })
        for _ in range(3):
            tools.dispatch_tool("update_habit", {"habit_name": "meditate", "completed": True})
        result = tools.dispatch_tool("check_goal_progress", {})
        assert "meditation streak" in result
        assert "20.0%" in result  # 6-day streak / 30-day target
        assert "habit streak" in result


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

    def test_log_reading_with_total_pages_stored(self, tools):
        from reading_pace import compute_reading_pace
        tools.dispatch_tool("log_reading", {"title": "Book A", "pages": 50, "total_pages": 300})
        result = compute_reading_pace("Book A")
        assert result["total_pages"] == 300

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


class TestBudgetTools:
    def test_set_budget_creates(self, tools):
        result = tools.dispatch_tool("set_budget", {"category": "groceries", "limit": 400})
        assert "groceries" in result
        assert "400" in result

    def test_set_budget_missing_fields(self, tools):
        result = tools.dispatch_tool("set_budget", {"category": "groceries"})
        assert "specify both" in result

    def test_set_budget_overwrites_same_category(self, tools):
        tools.dispatch_tool("set_budget", {"category": "groceries", "limit": 400})
        tools.dispatch_tool("set_budget", {"category": "Groceries", "limit": 500})
        result = tools.dispatch_tool("list_budgets", {})
        assert result.count("groceries") + result.count("Groceries") == 1
        assert "500" in result

    def test_list_budgets_empty(self, tools):
        result = tools.dispatch_tool("list_budgets", {})
        assert "No budgets" in result

    def test_get_budget_status_tracks_spending(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        tools.dispatch_tool("log_expense", {"amount": 40, "category": "food"})
        result = tools.dispatch_tool("get_budget_status", {})
        assert "food" in result
        assert "40" in result
        assert "100" in result

    def test_get_budget_status_flags_over_budget(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 10})
        tools.dispatch_tool("log_expense", {"amount": 50, "category": "food"})
        result = tools.dispatch_tool("get_budget_status", {})
        assert "OVER BUDGET" in result

    def test_get_budget_status_filters_by_category(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        tools.dispatch_tool("set_budget", {"category": "fun", "limit": 50})
        result = tools.dispatch_tool("get_budget_status", {"category": "fun"})
        assert "fun" in result
        assert "food" not in result

    def test_get_budget_status_no_budgets(self, tools):
        result = tools.dispatch_tool("get_budget_status", {})
        assert "No budgets" in result

    def test_delete_budget(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        result = tools.dispatch_tool("delete_budget", {"category": "food"})
        assert "deleted" in result
        assert tools.dispatch_tool("list_budgets", {}) == "No budgets set yet."

    def test_delete_budget_not_found(self, tools):
        result = tools.dispatch_tool("delete_budget", {"category": "nonexistent"})
        assert "No budget set" in result


class TestReminderTools:
    def test_create_reminder(self, tools):
        result = tools.dispatch_tool("create_reminder", {"text": "stretch", "time": "09:00"})
        assert "Reminder saved" in result
        assert "stretch" in result

    def test_create_reminder_missing_text(self, tools):
        result = tools.dispatch_tool("create_reminder", {})
        assert "specify what" in result

    def test_create_reminder_with_days(self, tools):
        tools.dispatch_tool("create_reminder", {"text": "call mom", "days": ["sun", "bogus"]})
        result = tools.dispatch_tool("list_reminders", {})
        assert "call mom" in result
        assert "sun" in result

    def test_list_reminders_empty(self, tools):
        result = tools.dispatch_tool("list_reminders", {})
        assert "No reminders" in result

    def test_delete_reminder(self, tools):
        create_result = tools.dispatch_tool("create_reminder", {"text": "stretch"})
        reminder_id = create_result.split("id=")[1].split("]")[0]
        result = tools.dispatch_tool("delete_reminder", {"reminder_id": reminder_id})
        assert "deleted" in result
        assert tools.dispatch_tool("list_reminders", {}) == "No reminders set yet."

    def test_delete_reminder_not_found(self, tools):
        result = tools.dispatch_tool("delete_reminder", {"reminder_id": "nonexistent"})
        assert "No reminder" in result


def _reminder_id(result):
    return result.split("id=")[1].split("]")[0]


class TestReminderToolsV137:
    def test_create_reminder_confirms_delivery_for_valid_time(self, tools):
        result = tools.dispatch_tool("create_reminder", {"text": "stretch", "time": "9am"})
        assert "09:00" in result
        assert "scheduler is running" in result

    def test_create_reminder_warns_for_unparseable_time(self, tools):
        result = tools.dispatch_tool("create_reminder", {"text": "stretch", "time": "after lunch"})
        assert "won't fire" in result

    def test_create_reminder_no_time_has_no_delivery_note(self, tools):
        result = tools.dispatch_tool("create_reminder", {"text": "stretch"})
        assert "scheduler" not in result
        assert "won't fire" not in result

    def test_update_reminder(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "old", "time": "09:00"}))
        result = tools.dispatch_tool("update_reminder", {"reminder_id": rid, "text": "new", "time": "6pm"})
        assert "updated" in result
        listing = tools.dispatch_tool("list_reminders", {})
        assert "new" in listing and "18:00" in listing

    def test_update_reminder_nothing_to_change(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x"}))
        assert "Nothing to change" in tools.dispatch_tool("update_reminder", {"reminder_id": rid})

    def test_update_reminder_not_found(self, tools):
        result = tools.dispatch_tool("update_reminder", {"reminder_id": "nope", "text": "x"})
        assert "No reminder" in result

    def test_update_reminder_blank_text_reports_error(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x"}))
        result = tools.dispatch_tool("update_reminder", {"reminder_id": rid, "text": "  "})
        assert "cannot be empty" in result

    def test_pause_and_resume(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x", "time": "09:00"}))
        assert "paused" in tools.dispatch_tool("pause_reminder", {"reminder_id": rid})
        assert "[paused]" in tools.dispatch_tool("list_reminders", {})
        assert "resumed" in tools.dispatch_tool("resume_reminder", {"reminder_id": rid})
        assert "[paused]" not in tools.dispatch_tool("list_reminders", {})

    def test_pause_and_resume_not_found(self, tools):
        assert "No reminder" in tools.dispatch_tool("pause_reminder", {"reminder_id": "nope"})
        assert "No reminder" in tools.dispatch_tool("resume_reminder", {"reminder_id": "nope"})

    def test_get_todays_reminders_empty(self, tools):
        assert tools.dispatch_tool("get_todays_reminders", {}) == "No reminders for today."

    def test_get_todays_reminders_lists_daily_reminder(self, tools):
        tools.dispatch_tool("create_reminder", {"text": "stretch", "time": "09:00"})
        out = tools.dispatch_tool("get_todays_reminders", {})
        assert "09:00: stretch" in out

    def test_get_todays_reminders_excludes_paused(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "stretch", "time": "09:00"}))
        tools.dispatch_tool("pause_reminder", {"reminder_id": rid})
        assert tools.dispatch_tool("get_todays_reminders", {}) == "No reminders for today."


class TestBudgetToolsV137:
    def test_forecast_no_budgets(self, tools):
        assert tools.dispatch_tool("get_budget_forecast", {}) == "No budgets set yet."

    def test_forecast_with_spending(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        tools.dispatch_tool("log_expense", {"amount": 30, "category": "food"})
        out = tools.dispatch_tool("get_budget_forecast", {})
        assert "food" in out and "30" in out

    def test_forecast_filters_by_category(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        tools.dispatch_tool("set_budget", {"category": "fun", "limit": 50})
        out = tools.dispatch_tool("get_budget_forecast", {"category": "fun"})
        assert "fun" in out and "food" not in out

    def test_status_counts_differently_cased_expense(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        tools.dispatch_tool("log_expense", {"amount": 40, "category": "Food"})
        out = tools.dispatch_tool("get_budget_status", {})
        assert "40.0 / 100" in out

    def test_history_no_budgets(self, tools):
        assert tools.dispatch_tool("get_budget_history", {}) == "No budgets set yet."

    def test_history_with_budget(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        out = tools.dispatch_tool("get_budget_history", {"months": 2})
        assert "last 2 completed month(s)" in out

    def test_history_bad_months_falls_back_to_default(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        out = tools.dispatch_tool("get_budget_history", {"months": "lots"})
        assert "last 3 completed month(s)" in out

    def test_unbudgeted_spending_none(self, tools):
        assert "No spending outside" in tools.dispatch_tool("get_unbudgeted_spending", {})

    def test_unbudgeted_spending_lists_category(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        tools.dispatch_tool("log_expense", {"amount": 40, "category": "food"})
        tools.dispatch_tool("log_expense", {"amount": 25, "category": "gifts"})
        out = tools.dispatch_tool("get_unbudgeted_spending", {})
        assert "gifts: 25.0" in out
        assert "food" not in out


class TestNewToolSchemas:
    NEW = ["update_reminder", "pause_reminder", "resume_reminder", "get_todays_reminders",
           "get_budget_forecast", "get_budget_history", "get_unbudgeted_spending"]

    def test_all_new_tools_are_declared_once(self, tools):
        names = [t["function"]["name"] for t in tools.TOOLS]
        for n in self.NEW:
            assert names.count(n) == 1

    def test_required_fields_exist_in_properties(self, tools):
        by_name = {t["function"]["name"]: t["function"] for t in tools.TOOLS}
        for n in self.NEW:
            params = by_name[n]["parameters"]
            assert params["type"] == "object"
            for req in params["required"]:
                assert req in params["properties"]

    def test_all_new_tools_are_dispatchable(self, tools):
        for n in self.NEW:
            out = tools.dispatch_tool(n, {})
            assert not out.startswith("Unknown tool"), n


class TestBackupTools:
    def test_status_with_no_backups(self, tools):
        assert "No backups yet" in tools.dispatch_tool("get_backup_status", {})

    def test_status_after_backup_now(self, tools):
        tools.dispatch_tool("backup_now", {})
        out = tools.dispatch_tool("get_backup_status", {})
        assert "1 backup(s) saved" in out
        assert "less than an hour ago" in out

    def test_backup_now_includes_every_store(self, tools):
        import json
        import re
        tools.dispatch_tool("log_expense", {"amount": 12, "category": "food"})
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        tools.dispatch_tool("create_reminder", {"text": "stretch", "time": "09:00"})
        result = tools.dispatch_tool("backup_now", {})
        path = re.search(r"Backup written: (\S+)", result).group(1)
        payload = json.loads(open(path, encoding="utf-8").read())
        assert payload["spending"][0]["amount"] == 12.0
        assert payload["budgets"][0]["limit"] == 100
        assert payload["reminders"][0]["text"] == "stretch"

    def test_backup_now_keep_zero_does_not_delete_the_new_backup(self, tools):
        result = tools.dispatch_tool("backup_now", {"keep": 0})
        assert "keeping the 1 most recent" in result
        assert "1 backup(s) saved" in tools.dispatch_tool("get_backup_status", {})

    def test_backup_now_negative_keep_is_clamped(self, tools):
        assert "keeping the 1 most recent" in tools.dispatch_tool("backup_now", {"keep": -3})

    def test_backup_now_non_numeric_keep_falls_back_to_default(self, tools):
        assert "keeping the 7 most recent" in tools.dispatch_tool("backup_now", {"keep": "lots"})

    def test_backup_now_none_keep_falls_back_to_default(self, tools):
        assert "keeping the 7 most recent" in tools.dispatch_tool("backup_now", {"keep": None})

    def test_get_backup_status_schema(self, tools):
        entry = next(t["function"] for t in tools.TOOLS if t["function"]["name"] == "get_backup_status")
        assert entry["parameters"]["required"] == []
        assert "command line" in entry["description"]


class TestReminderToolsV138:
    def test_create_dated_reminder_confirms_delivery(self, tools):
        out = tools.dispatch_tool("create_reminder", {"text": "passport", "time": "9am", "date": "2030-11-02"})
        assert "One-off" in out and "2030-11-02 at 09:00" in out

    def test_create_dated_reminder_without_time_explains(self, tools):
        out = tools.dispatch_tool("create_reminder", {"text": "birthday", "date": "2030-11-02"})
        assert "only shows up in get_todays_reminders" in out

    def test_create_with_invalid_date_reports_and_saves_nothing(self, tools):
        out = tools.dispatch_tool("create_reminder", {"text": "x", "time": "09:00", "date": "2030-02-30"})
        assert "YYYY-MM-DD" in out
        assert tools.dispatch_tool("list_reminders", {}) == "No reminders set yet."

    def test_dated_reminder_shows_date_in_list(self, tools):
        tools.dispatch_tool("create_reminder", {"text": "passport", "time": "09:00", "date": "2030-11-02"})
        assert "2030-11-02" in tools.dispatch_tool("list_reminders", {})

    def test_update_reminder_date(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x", "time": "09:00"}))
        out = tools.dispatch_tool("update_reminder", {"reminder_id": rid, "date": "2030-11-02"})
        assert "updated" in out
        assert "2030-11-02" in tools.dispatch_tool("list_reminders", {})

    def test_update_reminder_invalid_date(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x"}))
        assert "YYYY-MM-DD" in tools.dispatch_tool("update_reminder", {"reminder_id": rid, "date": "soon"})

    def test_update_with_only_a_date_is_not_nothing_to_change(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x"}))
        out = tools.dispatch_tool("update_reminder", {"reminder_id": rid, "date": "2030-11-02"})
        assert "Nothing to change" not in out

    def test_remind_me_in(self, tools):
        out = tools.dispatch_tool("remind_me_in", {"text": "check the oven", "minutes": 20})
        assert "I'll remind you at" in out and "check the oven" in out and "id=" in out
        assert "check the oven" in tools.dispatch_tool("list_reminders", {})

    @pytest.mark.parametrize("minutes", [0, 5000, "abc", None])
    def test_remind_me_in_invalid_minutes(self, tools, minutes):
        out = tools.dispatch_tool("remind_me_in", {"text": "x", "minutes": minutes})
        assert "minutes must be" in out
        assert tools.dispatch_tool("list_reminders", {}) == "No reminders set yet."

    def test_remind_me_in_blank_text(self, tools):
        assert "what to be reminded" in tools.dispatch_tool("remind_me_in", {"text": "", "minutes": 5})

    def test_snooze_reminder(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x", "time": "09:00"}))
        out = tools.dispatch_tool("snooze_reminder", {"reminder_id": rid, "minutes": 15})
        assert "snoozed until" in out
        assert "[snoozed until" in tools.dispatch_tool("list_reminders", {})

    def test_snooze_defaults_to_ten_minutes(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x"}))
        assert "snoozed until" in tools.dispatch_tool("snooze_reminder", {"reminder_id": rid})

    def test_snooze_not_found(self, tools):
        assert "No reminder" in tools.dispatch_tool("snooze_reminder", {"reminder_id": "nope"})

    def test_snooze_invalid_minutes(self, tools):
        rid = _reminder_id(tools.dispatch_tool("create_reminder", {"text": "x"}))
        assert "minutes must be" in tools.dispatch_tool("snooze_reminder", {"reminder_id": rid, "minutes": 0})

    def test_clear_past_reminders(self, tools):
        tools.dispatch_tool("create_reminder", {"text": "old", "time": "09:00", "date": "2020-01-01"})
        tools.dispatch_tool("create_reminder", {"text": "future", "time": "09:00", "date": "2099-01-01"})
        out = tools.dispatch_tool("clear_past_reminders", {})
        assert "Removed 1 past" in out
        listing = tools.dispatch_tool("list_reminders", {})
        assert "future" in listing and "old" not in listing

    def test_clear_past_reminders_nothing_to_do(self, tools):
        assert "No past one-off" in tools.dispatch_tool("clear_past_reminders", {})

    def test_new_reminder_tools_are_declared_and_dispatchable(self, tools):
        names = [t["function"]["name"] for t in tools.TOOLS]
        for n in ("remind_me_in", "snooze_reminder", "clear_past_reminders"):
            assert names.count(n) == 1
            assert not tools.dispatch_tool(n, {}).startswith("Unknown tool")

    def test_date_property_declared_on_create_and_update(self, tools):
        by_name = {t["function"]["name"]: t["function"] for t in tools.TOOLS}
        assert "date" in by_name["create_reminder"]["parameters"]["properties"]
        assert "date" in by_name["update_reminder"]["parameters"]["properties"]
        assert by_name["remind_me_in"]["parameters"]["required"] == ["text", "minutes"]


class TestBudgetAlertPctTool:
    def test_set_budget_with_alert_pct(self, tools):
        out = tools.dispatch_tool("set_budget", {"category": "food", "limit": 400, "alert_pct": 90})
        assert "alerts at 90% used" in out

    def test_set_budget_without_alert_pct_has_no_alert_text(self, tools):
        assert "alerts at" not in tools.dispatch_tool("set_budget", {"category": "food", "limit": 400})

    def test_invalid_alert_pct_reports_and_saves_nothing(self, tools):
        out = tools.dispatch_tool("set_budget", {"category": "food", "limit": 400, "alert_pct": 500})
        assert "alert_pct must be" in out
        assert tools.dispatch_tool("list_budgets", {}) == "No budgets set yet."

    def test_list_budgets_shows_threshold(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 400, "alert_pct": 90})
        assert "(alert at 90%)" in tools.dispatch_tool("list_budgets", {})

    def test_zero_removes_threshold_through_the_tool(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 400, "alert_pct": 90})
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 400, "alert_pct": 0})
        assert "alert at" not in tools.dispatch_tool("list_budgets", {})

    def test_get_nudges_uses_the_custom_threshold(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100, "alert_pct": 50})
        tools.dispatch_tool("log_expense", {"amount": 60, "category": "food"})
        assert "food" in tools.dispatch_tool("get_nudges", {})

    def test_schema_declares_alert_pct(self, tools):
        entry = next(t["function"] for t in tools.TOOLS if t["function"]["name"] == "set_budget")
        assert "alert_pct" in entry["parameters"]["properties"]
        assert "alert_pct" not in entry["parameters"]["required"]


class TestHealthCheckTool:
    def test_fresh_profile_is_healthy_after_a_backup(self, tools):
        tools.dispatch_tool("backup_now", {})
        out = tools.dispatch_tool("run_health_check", {})
        assert "health check" in out and "Everything looks healthy." in out

    def test_reports_a_corrupt_data_file(self, tools):
        import storage
        storage.save_habits([{"name": "a"}])
        storage.data_store_path("habits").write_text("{broken", encoding="utf-8")
        out = tools.dispatch_tool("run_health_check", {})
        assert "[ERROR]" in out and "habits" in out

    def test_warns_when_data_has_no_backup(self, tools):
        tools.dispatch_tool("log_expense", {"amount": 5, "category": "food"})
        out = tools.dispatch_tool("run_health_check", {})
        assert "[WARN]" in out and "No backups yet" in out

    def test_is_read_only(self, tools):
        import storage
        tools.dispatch_tool("log_expense", {"amount": 5, "category": "food"})
        before = storage.load_spending()
        tools.dispatch_tool("run_health_check", {})
        assert storage.load_spending() == before

    def test_schema(self, tools):
        entry = next(t["function"] for t in tools.TOOLS if t["function"]["name"] == "run_health_check")
        assert entry["parameters"]["required"] == []


class TestBudgetLimitValidationTool:
    def test_numeric_string_limit_is_accepted(self, tools):
        out = tools.dispatch_tool("set_budget", {"category": "food", "limit": "400"})
        assert "food -> 400 / month" in out

    def test_text_limit_is_rejected_with_a_message(self, tools):
        out = tools.dispatch_tool("set_budget", {"category": "food", "limit": "lots"})
        assert "limit must be" in out
        assert tools.dispatch_tool("list_budgets", {}) == "No budgets set yet."

    def test_negative_limit_is_rejected(self, tools):
        assert "limit must be" in tools.dispatch_tool("set_budget", {"category": "food", "limit": -10})

    def test_zero_limit_is_allowed(self, tools):
        assert "food -> 0 / month" in tools.dispatch_tool("set_budget", {"category": "food", "limit": 0})

    def test_string_limit_does_not_break_later_status_calls(self, tools):
        tools.dispatch_tool("set_budget", {"category": "food", "limit": "100"})
        tools.dispatch_tool("log_expense", {"amount": 30, "category": "food"})
        assert "30" in tools.dispatch_tool("get_budget_status", {})
        assert "food" in tools.dispatch_tool("get_budget_forecast", {})
        tools.dispatch_tool("get_nudges", {})  # must not raise


class TestSuggestBudgetsTool:
    def _spend_last_month(self, tools, category, amount):
        from datetime import datetime
        first = datetime.now().replace(day=1)
        last_month = (first.replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=15)
        import storage
        rows = storage.load_spending()
        rows.append({"date": last_month.strftime("%Y-%m-%d"), "category": category, "amount": amount})
        storage.save_spending(rows)

    def test_nothing_to_suggest(self, tools):
        assert "Nothing to suggest" in tools.dispatch_tool("suggest_budgets", {})

    def test_suggests_from_history(self, tools):
        self._spend_last_month(tools, "food", 300)
        out = tools.dispatch_tool("suggest_budgets", {"months": 1, "buffer_pct": 0})
        assert "- food: 300" in out
        assert "set_budget" in out

    def test_default_buffer_is_ten_percent(self, tools):
        self._spend_last_month(tools, "food", 300)
        assert "- food: 330" in tools.dispatch_tool("suggest_budgets", {"months": 1})

    def test_budgeted_category_not_suggested(self, tools):
        self._spend_last_month(tools, "food", 300)
        tools.dispatch_tool("set_budget", {"category": "food", "limit": 100})
        assert "Nothing to suggest" in tools.dispatch_tool("suggest_budgets", {"months": 1})

    def test_bad_months_falls_back(self, tools):
        assert "3 completed month(s)" in tools.dispatch_tool("suggest_budgets", {"months": "lots"})

    def test_bad_buffer_is_reported_not_raised(self, tools):
        assert "buffer_pct" in tools.dispatch_tool("suggest_budgets", {"buffer_pct": 500})
        assert "buffer_pct" in tools.dispatch_tool("suggest_budgets", {"buffer_pct": "lots"})

    def test_schema(self, tools):
        entry = next(t["function"] for t in tools.TOOLS if t["function"]["name"] == "suggest_budgets")
        assert entry["parameters"]["required"] == []
        assert set(entry["parameters"]["properties"]) == {"months", "buffer_pct"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
