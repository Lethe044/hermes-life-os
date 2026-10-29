"""Objectives and key results."""

from __future__ import annotations

from datetime import date

import pytest


def objective(p, name="Get fit", **kw):
    args = {"name": name, "period": "2026-Q4", **kw}
    out = p.dispatch_tool("add_objective", args)
    assert out.startswith("Objective added: "), out
    return out.split("\n")[0].split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_okrs()


RUN = {"name": "Run", "target": 100, "unit": "km"}
WEIGHT = {"name": "Weight", "start_value": 85, "target": 80, "unit": "kg"}


class TestPeriod:
    @pytest.mark.parametrize("text,expected", [
        ("week", ("2026-10-12", "2026-10-18")), ("month", ("2026-10-01", "2026-10-31")),
        ("quarter", ("2026-10-01", "2026-12-31")), ("year", ("2026-01-01", "2026-12-31")),
        ("2026-Q1", ("2026-01-01", "2026-03-31")), ("2026-q2", ("2026-04-01", "2026-06-30")),
        ("Q3", ("2026-07-01", "2026-09-30")), ("Q4 2027", ("2027-10-01", "2027-12-31")),
        ("2027-Q4", ("2027-10-01", "2027-12-31")), ("2026-02", ("2026-02-01", "2026-02-28")),
        ("2028-02", ("2028-02-01", "2028-02-29")), ("2026", ("2026-01-01", "2026-12-31")), (None, ("2026-10-01", "2026-12-31")),
        ("", ("2026-10-01", "2026-12-31")), (" WEEK ", ("2026-10-12", "2026-10-18"))])
    def test_good(self, planner, text, expected):
        import okrs
        assert okrs.parse_period(text) == expected

    @pytest.mark.parametrize("bad", ["fortnight", "2026-Q5", "2026-13", "1999", "2101-Q1", "Q0", 5, "2026-0"])
    def test_bad(self, planner, bad):
        import okrs
        with pytest.raises(ValueError):
            okrs.parse_period(bad)

    def test_dates_instead_of_period(self, planner):
        oid = objective(planner, period=None, start="2026-10-05", end="2026-10-30")
        assert (rows()[0]["start"], rows()[0]["end"]) == ("2026-10-05", "2026-10-30") and oid

    def test_start_defaults_to_today(self, planner):
        objective(planner, period=None, end="2026-11-01")
        assert rows()[0]["start"] == "2026-10-13"

    @pytest.mark.parametrize("kw,msg", [({"start": "2026-10-05"}, "give an end date"),
                                        ({"period": "week", "end": "2026-10-30"}, "either a period or start and end"),
                                        ({"start": "2026-10-30", "end": "2026-10-05"}, "end date cannot be before"),
                                        ({"start": "2026-01-01", "end": "2027-12-31"}, "at most 400 days"),
                                        ({"start": "x", "end": "2026-12-01"}, "")])
    def test_bad_dates_rejected(self, planner, kw, msg):
        out = planner.dispatch_tool("add_objective", {"name": "x", **kw})
        assert out.startswith("Objective not added: ") and msg in out and rows() == []


class TestAdd:
    def test_shape(self, planner):
        oid = objective(planner, key_results=[RUN, WEIGHT], notes=" stay fit ")
        r = rows()[0]
        assert r["id"] == oid and r["status"] == "active" and r["notes"] == "stay fit" and r["created"] == "2026-10-13"
        run, weight = r["key_results"]
        assert (run["start_value"], run["target"], run["current"], run["unit"], run["history"]) == (0, 100, 0, "km", [])
        assert (weight["start_value"], weight["target"], weight["current"]) == (85, 80, 85)

    def test_output(self, planner):
        out = planner.dispatch_tool("add_objective", {"name": "Get fit", "period": "2026-Q4", "key_results": [RUN]})
        assert out.startswith("Objective added: Get fit: 0% done, 14% of the time used - slightly behind (2026-10-01 to 2026-12-31) [id=")
        assert "\n    - Run: 0/100 km (0%, from 0) [id=" in out

    @pytest.mark.parametrize("kw,msg", [
        ({"name": ""}, "needs a name"), ({"name": "n" * 81}, "at most 80"),
        ({"key_results": "run"}, "must be a list"), ({"key_results": ["run"]}, "must be a list"),
        ({"key_results": [{"name": "a", "target": 0}]}, "must differ"),
        ({"key_results": [{"name": "a", "target": 5, "start_value": 5}]}, "must differ"),
        ({"key_results": [{"name": "a", "target": "x"}]}, "target must be a number"),
        ({"key_results": [{"name": "a", "target": True}]}, "target must be a number"),
        ({"key_results": [{"name": "a", "target": float("inf")}]}, "target must be a number"),
        ({"key_results": [{"name": "a", "target": 1e12}]}, "target must be a number"),
        ({"key_results": [{"name": "", "target": 5}]}, "needs a name"),
        ({"key_results": [{"name": "a", "target": 5, "unit": "u" * 16}]}, "at most 15"),
        ({"key_results": [{"name": "a", "target": 5}, {"name": "A", "target": 6}]}, "two key results called"),
        ({"key_results": [{"name": f"k{i}", "target": 5} for i in range(9)]}, "at most 8"),
        ({"notes": 5}, "notes must be text"),
    ])
    def test_rejected_and_nothing_stored(self, planner, kw, msg):
        out = planner.dispatch_tool("add_objective", {"name": "x", "period": "week", **kw})
        assert out.startswith("Objective not added: ") and msg in out, out
        assert rows() == []

    def test_one_bad_key_result_adds_no_objective(self, planner):
        planner.dispatch_tool("add_objective", {"name": "x", "key_results": [RUN, {"name": "bad", "target": "?"}]})
        assert rows() == []

    def test_duplicate_active_name(self, planner):
        objective(planner)
        assert "already an active objective called 'get fit'" in planner.dispatch_tool("add_objective", {"name": "get fit"})
        planner.dispatch_tool("update_okr", {"objective": "fit", "fields": {"status": "dropped"}})
        objective(planner)  # the dropped one does not count
        assert len(rows()) == 2

    def test_limit(self, planner, monkeypatch):
        import okrs
        monkeypatch.setattr(okrs, "MAX_OBJECTIVES", 1)
        objective(planner)
        assert "already have 1 objectives" in planner.dispatch_tool("add_objective", {"name": "two"})


class TestKeyResults:
    def test_add_and_limits(self, planner):
        objective(planner)
        out = planner.dispatch_tool("add_key_result", {"objective": "fit", "name": "Read", "target": 12, "unit": "books"})
        assert out.startswith("Key result added to Get fit: Read: 0/12 books (0%, from 0) [id=")
        assert "already has a key result called 'read'" in planner.dispatch_tool("add_key_result", {"objective": "fit", "name": "read", "target": 3})
        for i in range(7):
            assert planner.dispatch_tool("add_key_result", {"objective": "fit", "name": f"k{i}", "target": 5}).startswith("Key result added")
        assert "already has 8 key results" in planner.dispatch_tool("add_key_result", {"objective": "fit", "name": "last", "target": 5})
        assert len(rows()[0]["key_results"]) == 8

    def test_unknown_objective(self, planner):
        assert planner.dispatch_tool("add_key_result", {"objective": "zzz", "name": "a", "target": 5}).startswith("Key result not added: no objective matches")

    def test_record_value_and_add(self, planner):
        objective(planner, key_results=[RUN, WEIGHT])
        out = planner.dispatch_tool("record_key_result", {"objective": "fit", "key_result": "run", "value": 25})
        assert out.startswith("Recorded: Run: 25/100 km (25%, from 0)") and "Objective Get fit: 13% done" in out
        planner.dispatch_tool("record_key_result", {"objective": "fit", "key_result": "run", "add": 10})
        planner.dispatch_tool("record_key_result", {"objective": "fit", "key_result": "run", "add": -5})
        assert rows()[0]["key_results"][0]["current"] == 30

    def test_same_day_updates_replace_the_history_point(self, planner):
        objective(planner, key_results=[RUN])
        for v in (5, 10, 15):
            planner.dispatch_tool("record_key_result", {"objective": "fit", "value": v})
        assert rows()[0]["key_results"][0]["history"] == [{"date": "2026-10-13", "value": 15}]
        planner.set_now(__import__("datetime").datetime(2026, 10, 14, 9, 0))
        planner.dispatch_tool("record_key_result", {"objective": "fit", "add": 5})
        assert [h["value"] for h in rows()[0]["key_results"][0]["history"]] == [15, 20]

    def test_history_is_capped(self, planner, monkeypatch):
        import okrs
        monkeypatch.setattr(okrs, "MAX_HISTORY", 3)
        objective(planner, key_results=[RUN])
        kr = rows()[0]["key_results"][0]
        kr["history"] = [{"date": f"2026-09-0{i}", "value": i} for i in range(1, 6)]
        import storage
        storage.save_okrs(rows_with(kr))
        planner.dispatch_tool("record_key_result", {"objective": "fit", "value": 9})
        assert [h["value"] for h in rows()[0]["key_results"][0]["history"]] == [4, 5, 9]

    def test_single_key_result_needs_no_name(self, planner):
        objective(planner, key_results=[RUN])
        assert planner.dispatch_tool("record_key_result", {"objective": "fit", "value": 5}).startswith("Recorded: Run: 5/100")

    def test_several_key_results_need_a_name(self, planner):
        objective(planner, key_results=[RUN, WEIGHT])
        assert "say which key result" in planner.dispatch_tool("record_key_result", {"objective": "fit", "value": 5})

    def test_ambiguous_and_unknown_key_result(self, planner):
        objective(planner, key_results=[{"name": "Run long", "target": 5}, {"name": "Run fast", "target": 5}])
        assert "matches 2 key results" in planner.dispatch_tool("record_key_result", {"objective": "fit", "key_result": "run", "value": 1})
        assert "no key result matching 'swim'" in planner.dispatch_tool("record_key_result", {"objective": "fit", "key_result": "swim", "value": 1})

    @pytest.mark.parametrize("kw,msg", [({}, "either value"), ({"value": 1, "add": 1}, "either value"),
                                        ({"value": "x"}, "value must be a number"), ({"add": True}, "add must be a number"),
                                        ({"value": float("nan")}, "value must be a number"), ({"add": 2e9}, "add must be a number")])
    def test_record_rejected(self, planner, kw, msg):
        objective(planner, key_results=[RUN])
        out = planner.dispatch_tool("record_key_result", {"objective": "fit", **kw})
        assert out.startswith("Not recorded: ") and msg in out
        assert rows()[0]["key_results"][0]["current"] == 0 and rows()[0]["key_results"][0]["history"] == []

    def test_add_overflowing_the_limit_is_rejected(self, planner):
        objective(planner, key_results=[RUN])
        planner.dispatch_tool("record_key_result", {"objective": "fit", "value": 900_000_000})
        out = planner.dispatch_tool("record_key_result", {"objective": "fit", "add": 900_000_000})
        assert "the new total must be a number" in out and rows()[0]["key_results"][0]["current"] == 900_000_000

    def test_update_and_delete_key_result(self, planner):
        objective(planner, key_results=[RUN, WEIGHT])
        out = planner.dispatch_tool("update_okr", {"objective": "fit", "key_result": "run", "fields": {"target": 200, "unit": "mi", "name": "Run far", "current": 50}})
        assert out.startswith("Key result updated: Run far: 50/200 mi (25%, from 0)")
        assert "must differ" in planner.dispatch_tool("update_okr", {"objective": "fit", "key_result": "far", "fields": {"target": 0}})
        assert "already has a key result called 'WEIGHT'" in planner.dispatch_tool("update_okr", {"objective": "fit", "key_result": "far", "fields": {"name": "WEIGHT"}})
        assert "cannot change color of a key result" in planner.dispatch_tool("update_okr", {"objective": "fit", "key_result": "far", "fields": {"color": 1}})
        assert planner.dispatch_tool("delete_okr", {"objective": "fit", "key_result": "far"}) == "Deleted key result Run far from Get fit. This can't be undone."
        assert [k["name"] for k in rows()[0]["key_results"]] == ["Weight"]


def rows_with(kr):
    r = rows()
    r[0]["key_results"][0] = kr
    return r


class TestProgress:
    def test_going_down(self, planner):
        import okrs
        kr = {"start_value": 85, "target": 80, "current": 82.5}
        assert okrs.kr_progress(kr) == 0.5
        assert okrs.kr_progress({**kr, "current": 90}) == 0.0      # moved the wrong way
        assert okrs.kr_progress({**kr, "current": 70}) == 1.0      # past the target is capped

    @pytest.mark.parametrize("kr", [{}, {"start_value": 1, "target": 1, "current": 1}, {"start_value": "a", "target": 5, "current": 1},
                                    {"start_value": 0, "target": True, "current": 1}, {"start_value": 0, "target": 5, "current": None},
                                    {"start_value": 0, "target": float("inf"), "current": 1}])
    def test_unusable_numbers_count_as_zero(self, planner, kr):
        import okrs
        assert okrs.kr_progress(kr) == 0.0

    def test_objective_is_the_average(self, planner):
        import okrs
        o = {"key_results": [{"start_value": 0, "target": 10, "current": 10}, {"start_value": 0, "target": 10, "current": 0}, "junk"]}
        assert okrs.progress(o) == 0.5 and okrs.progress({}) == 0.0

    def test_expected_share(self, planner):
        import okrs
        o = {"start": "2026-10-01", "end": "2026-10-20"}
        assert okrs.expected(o, date(2026, 9, 30)) == 0.0
        assert okrs.expected(o, date(2026, 10, 1)) == 1 / 20
        assert okrs.expected(o, date(2026, 10, 10)) == 0.5
        assert okrs.expected(o, date(2026, 10, 20)) == 1.0 and okrs.expected(o, date(2027, 1, 1)) == 1.0
        assert okrs.expected({"start": "x", "end": "y"}) is None

    @pytest.mark.parametrize("done,label", [(80, "ahead of pace"), (50, "on track"), (47, "on track"), (40, "slightly behind"),
                                            (31, "slightly behind"), (20, "behind"), (0, "behind"), (100, "achieved")])
    def test_pace_labels(self, planner, done, label):
        import okrs
        o = {"start": "2026-10-01", "end": "2026-10-20", "key_results": [{"start_value": 0, "target": 100, "current": done}]}
        assert okrs.pace(o, date(2026, 10, 10)) == label

    def test_other_states(self, planner):
        import okrs
        kr = [{"start_value": 0, "target": 100, "current": 10}]
        base = {"start": "2026-10-01", "end": "2026-10-20", "key_results": kr}
        assert okrs.pace({**base, "status": "dropped"}) == "dropped" and okrs.pace({**base, "status": "done"}) == "done"
        assert okrs.pace({**base, "key_results": []}) == "no key results yet"
        assert okrs.pace(base, date(2026, 9, 1)) == "not started" and okrs.pace(base, date(2026, 11, 1)) == "missed"
        assert okrs.pace({**base, "start": "x"}) == "dates unreadable"


class TestListingAndUpdate:
    def test_listing_sorted_by_end_and_filtered(self, planner):
        objective(planner, "Later", period="year"); objective(planner, "Sooner", period="week")
        objective(planner, "Over", period="month")
        planner.dispatch_tool("update_okr", {"objective": "over", "fields": {"status": "done"}})
        out = planner.dispatch_tool("get_okrs", {})
        assert out.startswith("2 objectives (active):") and out.index("Sooner") < out.index("Later") and "Over" not in out
        assert planner.dispatch_tool("get_okrs", {"status": "done"}).startswith("1 objective (done):")
        assert planner.dispatch_tool("get_okrs", {"status": "all"}).startswith("3 objectives:")
        assert planner.dispatch_tool("get_okrs", {"status": "dropped"}) == "No dropped objectives."
        assert "Cannot show objectives: status must be" in planner.dispatch_tool("get_okrs", {"status": "later"})

    def test_empty(self, planner):
        assert planner.dispatch_tool("get_okrs", {}) == "No objectives yet. Add one with add_objective."

    def test_detail_with_history(self, planner):
        objective(planner, key_results=[RUN])
        planner.dispatch_tool("record_key_result", {"objective": "fit", "value": 12.5})
        out = planner.dispatch_tool("get_okrs", {"objective": "fit"})
        assert "history: 2026-10-13: 12.5" in out and "- Run: 12.5/100 km (13%, from 0)" in out

    def test_update_objective_fields(self, planner):
        objective(planner)
        out = planner.dispatch_tool("update_okr", {"objective": "fit", "fields": {"name": "Fitter", "notes": "n", "start": "2026-10-05", "end": "2026-12-01", "status": "done"}})
        assert out.startswith("Objective updated: Fitter: ") and "(2026-10-05 to 2026-12-01)" in out
        r = rows()[0]
        assert (r["notes"], r["status"]) == ("n", "done")

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"status": "paused"}, "status must be"),
                                            ({"end": "2026-09-01"}, "end date cannot be before"), ({"start": "2024-01-01"}, "at most 400 days"),
                                            ({"target": 5}, "cannot change target"), ({"name": ""}, "needs a name")])
    def test_update_rejected(self, planner, fields, msg):
        objective(planner)
        out = planner.dispatch_tool("update_okr", {"objective": "fit", "fields": fields})
        assert out.startswith("Not changed: ") and msg in out and rows()[0]["status"] == "active"

    def test_renaming_into_an_active_name(self, planner):
        objective(planner, "A"); objective(planner, "B")
        assert "already an active objective called 'a'" in planner.dispatch_tool("update_okr", {"objective": "B", "fields": {"name": "a"}})

    def test_delete_objective(self, planner):
        objective(planner, key_results=[RUN])
        assert planner.dispatch_tool("delete_okr", {"objective": "fit"}) == "Deleted objective Get fit and its key results. This can't be undone."
        assert rows() == []
        assert planner.dispatch_tool("delete_okr", {"objective": "fit"}).startswith("Not deleted: no objective matches")

    def test_ambiguous_objective(self, planner):
        objective(planner, "Get fit"); objective(planner, "Get rich")
        assert "matches 2 objectives" in planner.dispatch_tool("delete_okr", {"objective": "get"})

    def test_damaged_rows_never_crash(self, planner):
        import storage
        storage.save_okrs(["x", None, {"id": "a", "name": "odd", "start": "bad", "end": None, "key_results": "nope"},
                           {"id": "b", "name": "odd2", "start": "2026-10-01", "end": "2026-10-31", "key_results": [None, "x", {"id": "k"}]}])
        assert planner.dispatch_tool("get_okrs", {"status": "all"}).startswith("2 objectives:")
        assert planner.dispatch_tool("get_okrs", {"objective": "odd2"}).startswith("odd2: 0% done")
        import okrs
        assert okrs.nudges() == [] and okrs.agenda_lines() == []


class TestNudgesAndAgenda:
    def make(self, planner, end, done):
        planner.dispatch_tool("add_objective", {"name": "Ship", "start": "2026-10-01", "end": end,
                                                "key_results": [{"name": "Tests", "target": 100}]})
        planner.dispatch_tool("record_key_result", {"objective": "ship", "value": done})

    def test_nudge_for_unfinished_objective_about_to_end(self, planner):
        import okrs
        self.make(planner, "2026-10-18", 40)
        assert okrs.nudges() == ["Objective 'Ship' ends in 5 days and is 40% done."]
        assert okrs.agenda_lines() == ["Ship: ends in 5 days, 40% done"]

    @pytest.mark.parametrize("end,text", [("2026-10-13", "ends today"), ("2026-10-14", "ends tomorrow")])
    def test_wording(self, planner, end, text):
        import okrs
        self.make(planner, end, 10)
        assert text in okrs.nudges()[0]

    @pytest.mark.parametrize("end,done", [("2026-10-30", 10), ("2026-10-18", 70), ("2026-10-12", 10)])
    def test_no_nudge(self, planner, end, done):
        import okrs
        self.make(planner, end, done)
        assert okrs.nudges() == []

    def test_dropped_objective_is_quiet(self, planner):
        import okrs
        self.make(planner, "2026-10-18", 10)
        planner.dispatch_tool("update_okr", {"objective": "ship", "fields": {"status": "dropped"}})
        assert okrs.nudges() == []

    def test_agenda_section(self, planner):
        self.make(planner, "2026-10-18", 40)
        assert "Objectives about to end:\n  Ship: ends in 5 days, 40% done" in planner.dispatch_tool("get_today_agenda", {})
