"""Body metrics: logging with units and validation, trends, targets, journal and entry-tool integration."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


def log(p, metric="weight", value=80, **kw):
    return p.dispatch_tool("log_body_metric", {"metric": metric, "value": value, **kw})


def rows():
    import storage
    return storage.load_body()


def weights(p, values, unit=None, start="2026-09-29"):
    """One weight reading per day starting at `start`."""
    day = datetime.strptime(start, "%Y-%m-%d")
    for i, v in enumerate(values):
        kw = {"unit": unit} if unit else {}
        out = log(p, "weight", v, date=(day + timedelta(days=i)).strftime("%Y-%m-%d"), **kw)
        assert out.startswith("Logged"), out


class TestLogging:
    def test_basic(self, planner):
        out = log(planner)
        r = rows()[0]
        assert out.startswith("Logged: Weight 80 kg on 2026-10-13 [id=") and r["metric"] == "weight"
        assert r["value"] == 80 and r["unit"] == "kg" and r["date"] == "2026-10-13" and len(r["id"]) == 8

    def test_journal_entry_is_linked(self, planner):
        import storage
        log(planner)
        m = storage.get_all_memory()[-1]
        assert m["type"] == "body" and m["log_id"] == rows()[0]["id"] and m["content"] == "Weight 80 kg"

    @pytest.mark.parametrize("alias,metric", [("Body Weight", "weight"), ("BP", "blood_pressure"), ("pulse", "resting_hr"),
                                              ("heart rate", "resting_hr"), ("blood sugar", "blood_glucose"),
                                              ("body-fat", "body_fat"), ("temp", "temperature"), ("O2", "spo2")])
    def test_aliases(self, planner, alias, metric):
        value = {"blood_pressure": 120, "resting_hr": 60, "blood_glucose": 90, "body_fat": 20,
                 "temperature": 36.6, "spo2": 98}.get(metric, 80)
        kw = {"diastolic": 80} if metric == "blood_pressure" else {}
        assert log(planner, alias, value, **kw).startswith("Logged")
        assert rows()[0]["metric"] == metric

    def test_unknown_metric(self, planner):
        out = log(planner, "mood", 5)
        assert out.startswith("Not logged: unknown metric 'mood'") and rows() == []

    @pytest.mark.parametrize("metric,value,extra", [
        ("weight", 5, {}), ("weight", 700, {}), ("weight", 0, {}), ("weight", -3, {}), ("body_fat", 1, {}),
        ("resting_hr", 300, {}), ("temperature", 98.6, {}), ("spo2", 120, {}), ("waist", 5, {}),
        ("blood_glucose", 5, {}), ("weight", float("nan"), {}), ("weight", float("inf"), {}),
        ("weight", "heavy", {}), ("weight", True, {}), ("weight", None, {}),
    ])
    def test_implausible_or_non_numbers_are_refused(self, planner, metric, value, extra):
        out = log(planner, metric, value, **extra)
        assert out.startswith("Not logged: ") and rows() == []

    def test_range_message_names_the_unit(self, planner):
        assert "roughly 20 to 400 kg" in log(planner, "weight", 700)

    @pytest.mark.parametrize("metric,value,unit,canonical", [
        ("weight", 176.4, "lb", 80.0), ("weight", 12.6, "st", 80.0), ("waist", 31.5, "in", 80.0),
        ("blood_glucose", 5.0, "mmol/L", 90.0), ("temperature", 98.6, "F", 37.0), ("weight", 80, "KG", 80.0),
    ])
    def test_unit_conversion(self, planner, metric, value, unit, canonical):
        import body
        assert round(body.to_canonical(metric, value, unit), 0) == round(canonical, 0)
        assert log(planner, metric, value, unit=unit).startswith("Logged")

    def test_units_are_stored_as_typed_and_shown_back(self, planner):
        log(planner, "weight", 176, unit="lbs")
        log(planner, "temperature", 98.6, unit="f")
        log(planner, "blood_glucose", 5.5, unit="mmol/l")
        assert [(r["value"], r["unit"]) for r in rows()] == [(176, "lb"), (98.6, "F"), (5.5, "mmol/L")]

    def test_bad_unit(self, planner):
        out = log(planner, "weight", 80, unit="furlongs")
        assert out.startswith("Not logged: unit 'furlongs' is not valid for weight") and rows() == []
        assert "Use one of: kg, lb" in out

    def test_notes_are_kept_and_trimmed(self, planner):
        log(planner, notes="  after run  ")
        assert rows()[0]["notes"] == "after run"
        log(planner, notes="x" * 500)
        assert len(rows()[1]["notes"]) == 200

    def test_blank_notes_are_not_stored(self, planner):
        log(planner, notes="   ")
        assert "notes" not in rows()[0]

    def test_backdating_and_validation(self, planner):
        import storage
        log(planner, date="2026-10-01")
        assert rows()[0]["date"] == "2026-10-01"
        assert storage.get_all_memory()[-1]["timestamp"] == "2026-10-01T12:00:00Z"
        out = log(planner, date="2026-10-14")
        assert out.startswith("Not logged: ") and "in the future" in out and len(rows()) == 1

    def test_batchable(self, planner):
        out = planner.dispatch_tool("log_many", {"entries": [
            {"tool": "log_body_metric", "args": {"metric": "weight", "value": 80, "date": "2026-10-10"}},
            {"tool": "log_body_metric", "args": {"metric": "weight", "value": 79.5, "date": "2026-10-11"}}]})
        assert out.startswith("Logged 2 of 2") and len(rows()) == 2

    def test_trend_hint_after_two_readings(self, planner):
        log(planner, date="2026-10-11")
        out = log(planner, value=79, date="2026-10-12")
        assert "2 readings in 30 days, trend: falling." in out

    def test_cap(self, planner):
        import storage
        storage.save_body([{"id": str(i), "date": "2026-10-01", "metric": "weight", "value": 80, "unit": "kg"}
                           for i in range(20000)])
        assert "already holds 20000 rows" in log(planner)


class TestBloodPressure:
    def test_needs_both_numbers(self, planner):
        out = log(planner, "blood_pressure", 120)
        assert out.startswith("Not logged: a blood pressure reading needs both numbers") and rows() == []

    def test_logged_with_category(self, planner):
        out = log(planner, "blood_pressure", 118, diastolic=76)
        r = rows()[0]
        assert (r["value"], r["value2"]) == (118, 76) and "118/76 mmHg" in out
        assert "Normal range (information only, not medical advice)" in out

    @pytest.mark.parametrize("sys_,dia,category", [(118, 76, "normal range"), (125, 78, "elevated"),
                                                   (132, 78, "stage 1"), (125, 85, "stage 1"), (145, 85, "stage 2"),
                                                   (135, 95, "stage 2"), (185, 100, "very high"), (150, 121, "very high")])
    def test_categories(self, sys_, dia, category):
        import body
        assert category in body.bp_category(sys_, dia)

    @pytest.mark.parametrize("sys_,dia,msg", [(120, 130, "diastolic"), (120, 120, "lower"), (120, 20, "diastolic looks wrong")])
    def test_diastolic_checks(self, planner, sys_, dia, msg):
        assert msg in log(planner, "blood_pressure", sys_, diastolic=dia)

    def test_diastolic_on_another_metric(self, planner):
        assert "diastolic only applies to blood pressure" in log(planner, "weight", 80, diastolic=70)

    def test_trend_shows_both_numbers(self, planner):
        log(planner, "blood_pressure", 120, diastolic=80, date="2026-10-10")
        log(planner, "blood_pressure", 130, diastolic=84, date="2026-10-12")
        out = planner.dispatch_tool("get_body_trend", {"metric": "blood_pressure"})
        assert "latest 130.0/84.0 mmHg, average 125.0/82.0" in out and "not medical advice" in out

    def test_no_bp_target(self, planner):
        assert "not supported for blood pressure" in planner.dispatch_tool(
            "set_body_goal", {"metric": "bp", "target": 120})


class TestTrend:
    def test_no_data(self, planner):
        assert planner.dispatch_tool("get_body_trend", {"metric": "weight"}) == "No weight readings in the last 30 days."

    def test_overview_without_metric(self, planner):
        assert planner.dispatch_tool("get_body_trend", {}).startswith("No body measurements yet")
        log(planner, "weight", 80)
        log(planner, "waist", 90)
        log(planner, "blood_pressure", 120, diastolic=80)
        out = planner.dispatch_tool("get_body_trend", {})
        assert "Weight 80 kg (2026-10-13)" in out and "Waist 90 cm" in out and "120/80 mmHg" in out

    def test_single_reading(self, planner):
        log(planner, "weight", 80)
        out = planner.dispatch_tool("get_body_trend", {"metric": "weight"})
        assert "latest 80.0 kg" in out and "Log on more than one day to see a trend." in out and "Change" not in out

    def test_falling_trend_numbers(self, planner):
        weights(planner, [82, 81.5, 81, 80.5, 80])
        out = planner.dispatch_tool("get_body_trend", {"metric": "weight"})
        assert "latest 80.0 kg, average 81.0, range 80.0 to 82.0" in out
        assert "Change since 2026-09-29: -2.0 kg." in out and "Trend: falling, about -3.50 kg per week." in out

    def test_rising_and_stable(self, planner):
        weights(planner, [80, 80.5, 81, 81.5, 82])
        assert "rising, about +3.50" in planner.dispatch_tool("get_body_trend", {"metric": "weight"})
        weights(planner, [80, 80, 80, 80, 80], start="2026-10-09")  # 10-09..10-13, the last 3 days are flat
        out = planner.dispatch_tool("get_body_trend", {"metric": "weight", "days": 3})
        assert "Trend: stable." in out

    def test_same_day_readings_have_no_slope(self, planner):
        log(planner, "weight", 80)
        log(planner, "weight", 81)
        out = planner.dispatch_tool("get_body_trend", {"metric": "weight"})
        assert "Log on more than one day" in out

    def test_window_filters_old_readings(self, planner):
        log(planner, "weight", 90, date="2026-08-01")
        log(planner, "weight", 80)
        out = planner.dispatch_tool("get_body_trend", {"metric": "weight", "days": 30})
        assert "(1 reading(s))" in out and "latest 80.0" in out

    def test_shown_in_the_unit_of_the_latest_reading(self, planner):
        weights(planner, [176, 175, 174], unit="lb")
        out = planner.dispatch_tool("get_body_trend", {"metric": "weight"})
        assert "latest 174.0 lb" in out and "Change since 2026-09-29: -2.0 lb" in out

    def test_mixed_units_are_compared_fairly(self, planner):
        log(planner, "weight", 80, date="2026-10-01")
        log(planner, "weight", 176.37, unit="lb", date="2026-10-11")  # = 80 kg
        out = planner.dispatch_tool("get_body_trend", {"metric": "weight"})
        assert "Trend: stable." in out and "Change since 2026-10-01: +0.0" in out.replace("-0.0", "+0.0")

    def test_temperature_in_fahrenheit(self, planner):
        log(planner, "temperature", 98.6, unit="F", date="2026-10-11")
        log(planner, "temperature", 100.4, unit="F", date="2026-10-12")
        out = planner.dispatch_tool("get_body_trend", {"metric": "temperature"})
        assert "latest 100.4 F" in out and "Change since 2026-10-11: +1.8 F" in out

    def test_bad_arguments(self, planner):
        assert planner.dispatch_tool("get_body_trend", {"metric": "mood"}).startswith("Cannot show trend: unknown metric")
        assert planner.dispatch_tool("get_body_trend", {"metric": "weight", "days": "soon"}).startswith("Cannot show trend")

    def test_rows_with_bad_values_are_ignored(self, planner):
        import storage
        storage.save_body([{"id": "a", "date": "2026-10-12", "metric": "weight", "value": "x"},
                           {"id": "b", "date": "2026-10-12", "metric": "bogus", "value": 1},
                           {"id": "c", "metric": "weight", "value": 80}, "junk", None,
                           {"id": "d", "date": "2026-10-12", "metric": "weight", "value": 80, "unit": "kg"}])
        assert "(1 reading(s))" in planner.dispatch_tool("get_body_trend", {"metric": "weight"})


class TestGoals:
    def test_set_and_progress_with_eta(self, planner):
        weights(planner, [82, 81.5, 81, 80.5, 80])
        out = planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75})
        assert out == "Target set: weight 75 kg. Currently 80.0 kg, 5.0 to go."
        trend = planner.dispatch_tool("get_body_trend", {"metric": "weight"})
        assert "Target 75 kg: 5.0 kg to go, at the current pace around 2026-10-23 (in 10 days)." in trend

    def test_moving_away(self, planner):
        weights(planner, [80, 80.5, 81, 81.5, 82])
        planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75})
        assert "the trend is moving away from it" in planner.dispatch_tool("get_body_trend", {"metric": "weight"})

    def test_goal_above_current_with_rising_trend(self, planner):
        weights(planner, [70, 70.5, 71, 71.5, 72])
        planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75})
        assert "to go, at the current pace around" in planner.dispatch_tool("get_body_trend", {"metric": "weight"})

    def test_reached(self, planner):
        log(planner, "weight", 75, date="2026-10-12")
        log(planner, "weight", 75.05, date="2026-10-13")
        planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75})
        assert "reached." in planner.dispatch_tool("get_body_trend", {"metric": "weight"})

    def test_goal_in_pounds(self, planner):
        weights(planner, [176, 175, 174], unit="lb")
        out = planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 165, "unit": "lb"})
        assert "Target set: weight 165 lb. Currently 174.0 lb, 9.0 to go." in out

    def test_one_goal_per_metric_and_readings_untouched(self, planner):
        log(planner)
        planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75})
        planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 70})
        import body
        assert body.goals()["weight"]["target"] == 70 and len(body.readings()) == 1
        assert sum(1 for r in rows() if r.get("type") == "goal") == 1

    def test_clear(self, planner):
        planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75})
        assert planner.dispatch_tool("set_body_goal", {"metric": "weight", "clear": True}) == "Target for weight removed."
        assert planner.dispatch_tool("set_body_goal", {"metric": "weight", "clear": True}) == "No target was set for weight."

    def test_goal_without_readings(self, planner):
        assert planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75}) == "Target set: weight 75 kg."

    @pytest.mark.parametrize("target,msg", [(5, "looks wrong"), ("x", "must be a number"), (None, "must be a number")])
    def test_invalid_target(self, planner, target, msg):
        out = planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": target})
        assert out.startswith("Target not changed: ") and msg in out and rows() == []

    def test_goal_rows_are_not_readings(self, planner):
        import body
        planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75})
        assert body.readings() == [] and "No body measurements" in planner.dispatch_tool("get_body_trend", {})


class TestEntryTools:
    def test_listed_edited_deleted_undone(self, planner):
        import storage
        log(planner, "weight", 80, date="2026-10-12")
        log(planner, "waist", 90)
        out = planner.dispatch_tool("list_logs", {"tracker": "body"})
        assert "Weight 80 kg" in out and "Waist 90 cm" in out
        rid = rows()[0]["id"]
        assert planner.dispatch_tool("edit_log", {"tracker": "body", "log_id": rid,
                                                   "fields": {"value": 79.5}}).startswith("Updated")
        assert rows()[0]["value"] == 79.5
        assert storage.get_all_memory()[0]["content"] == "Weight 79.5 kg"
        assert planner.dispatch_tool("undo_last_log", {}).startswith("Undid the last body entry")
        assert planner.dispatch_tool("delete_log", {"tracker": "body", "log_id": rid}).startswith("Deleted")
        assert [r for r in rows() if r.get("metric")] == []

    def test_goals_are_invisible_to_the_entry_tools(self, planner):
        planner.dispatch_tool("set_body_goal", {"metric": "weight", "target": 75})
        assert planner.dispatch_tool("list_logs", {"tracker": "body"}) == "No body entries found in the last 7 days."
        assert planner.dispatch_tool("undo_last_log", {"tracker": "body"}).startswith("Nothing to undo")
        assert len(rows()) == 1

    def test_edit_validation(self, planner):
        log(planner)
        rid = rows()[0]["id"]
        for fields in ({"value": 0}, {"value": "x"}, {"value": -1}, {"diastolic": 0}):
            assert planner.dispatch_tool("edit_log", {"tracker": "body", "log_id": rid,
                                                       "fields": fields}).startswith("Not changed: ")
        assert rows()[0]["value"] == 80

    def test_day_view_search_gaps(self, planner):
        log(planner, "weight", 80, date="2026-10-12", notes="after breakfast")
        assert "body (1)" in planner.dispatch_tool("get_day_log", {"date": "2026-10-12"})
        assert "[body id=" in planner.dispatch_tool("search_logs", {"query": "breakfast"})
        assert "2026-10-11" in planner.dispatch_tool("get_logging_gaps", {"tracker": "body", "days": 2})

    def test_delete_entry_cascade(self, planner):
        import storage
        log(planner)
        out = planner.dispatch_tool("delete_entry", {"entry_id": storage.get_all_memory()[-1]["id"]})
        assert "linked body entry was removed too" in out and rows() == []

    def test_doctor_does_not_flag_body_links(self, planner):
        import doctor
        log(planner)
        assert [f["level"] for f in doctor.check_entry_ids()] == ["ok"]

    def test_schema(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        assert schemas["log_body_metric"]["parameters"]["properties"]["date"] == planner._ENTRY_DATE_PROP
        assert "body" in schemas["list_logs"]["parameters"]["properties"]["tracker"]["enum"]
