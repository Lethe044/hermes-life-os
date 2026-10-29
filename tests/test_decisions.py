"""Decision journal: write it down, review it, compare confidence with outcomes."""

from __future__ import annotations

import pytest


def dec(p, title="Switch to standing desk", **kw):
    out = p.dispatch_tool("add_decision", {"title": title, **kw})
    assert out.startswith("Decision saved: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_decisions()


class TestAdd:
    def test_shape_and_defaults(self, planner):
        out = planner.dispatch_tool("add_decision", {"title": " Switch  desk ", "options": ["keep", "switch"], "choice": "switch",
                                                     "reasoning": " back ", "expected": "less pain", "confidence": 8})
        assert out.startswith("Decision saved: Switch desk: chose 'switch' (confidence 8/10), review 2026-11-12 (in 30 days) [id=")
        d = rows()[0]
        assert set(d) == {"id", "title", "options", "choice", "reasoning", "expected", "confidence", "review", "status", "outcome",
                          "rating", "lessons", "created", "reviewed_on"}
        assert (d["status"], d["options"], d["reasoning"], d["rating"], d["outcome"], d["reviewed_on"]) == ("open", ["keep", "switch"], "back", None, "", None)

    def test_minimal(self, planner):
        out = planner.dispatch_tool("add_decision", {"title": "Move?"})
        assert out.startswith("Decision saved: Move?, review 2026-11-12 (in 30 days) [id=")

    def test_choice_is_added_to_the_options(self, planner):
        dec(planner, options="a, b", choice="c")
        assert rows()[0]["options"] == ["a", "b", "c"]
        dec(planner, "Other", options=["a"], choice="A")
        assert rows()[1]["options"] == ["a"]

    def test_review_dates(self, planner):
        dec(planner, "A", review="in 2 days")
        dec(planner, "B", review="2026-12-01")
        dec(planner, "C", review="friday")
        assert [d["review"] for d in rows()] == ["2026-10-15", "2026-12-01", "2026-10-16"]

    @pytest.mark.parametrize("kw,msg", [
        ({"title": ""}, "cannot be empty"), ({"title": "t" * 101}, "at most 100"), ({"options": [1]}, "options must be"),
        ({"options": [str(n) for n in range(11)]}, "at most 10"), ({"options": ["o" * 61]}, "at most 60"), ({"choice": "c" * 61}, "at most 60"),
        ({"reasoning": "r" * 301}, "at most 300"), ({"confidence": 0}, "from 1 to 10"), ({"confidence": 11}, "from 1 to 10"),
        ({"confidence": True}, "from 1 to 10"), ({"confidence": 2.5}, "from 1 to 10"), ({"confidence": "x"}, "from 1 to 10"),
        ({"review": "never"}, "couldn't understand the review date"), ({"review": "2026-10-01"}, "cannot be in the past")])
    def test_rejected(self, planner, kw, msg):
        out = planner.dispatch_tool("add_decision", {"title": "T", **kw})
        assert out.startswith("Decision not saved: ") and msg in out
        assert rows() == []

    def test_limit(self, planner):
        import storage
        storage.save_decisions([{"id": f"i{n}", "title": f"t{n}", "status": "open", "review": "2026-12-01"} for n in range(300)])
        assert "already have 300" in planner.dispatch_tool("add_decision", {"title": "More"})


class TestReview:
    def test_review_flow(self, planner):
        dec(planner, confidence=8)
        out = planner.dispatch_tool("review_decision", {"decision": "desk", "outcome": "Back is better", "rating": 4, "lessons": "Earlier"})
        assert out.startswith("Reviewed: Switch to standing desk (confidence 8/10), turned out 4/5: Back is better; lesson: Earlier [id=")
        d = rows()[0]
        assert (d["status"], d["rating"], d["reviewed_on"], d["lessons"]) == ("reviewed", 4, "2026-10-13", "Earlier")

    @pytest.mark.parametrize("kw,msg", [({"outcome": ""}, "cannot be empty"), ({"rating": None}, "rate how it turned out"),
                                        ({"rating": 0}, "from 1 to 5"), ({"rating": 6}, "from 1 to 5"), ({"rating": 2.5}, "from 1 to 5"),
                                        ({"rating": True}, "from 1 to 5"), ({"outcome": "o" * 301}, "at most 300")])
    def test_errors(self, planner, kw, msg):
        dec(planner)
        out = planner.dispatch_tool("review_decision", {"decision": "desk", "outcome": "ok", "rating": 3, **kw})
        assert out.startswith("Decision not reviewed: ") and msg in out
        assert rows()[0]["status"] == "open"

    def test_twice_is_refused(self, planner):
        dec(planner)
        planner.dispatch_tool("review_decision", {"decision": "desk", "outcome": "ok", "rating": 3})
        assert "already reviewed on 2026-10-13" in planner.dispatch_tool("review_decision", {"decision": "desk", "outcome": "x", "rating": 1})
        assert rows()[0]["rating"] == 3

    def test_notes_of_a_reviewed_decision_can_still_change(self, planner):
        dec(planner)
        planner.dispatch_tool("review_decision", {"decision": "desk", "outcome": "ok", "rating": 3})
        planner.dispatch_tool("update_decision", {"decision": "desk", "fields": {"lessons": "later", "outcome": "better"}})
        assert (rows()[0]["lessons"], rows()[0]["outcome"]) == ("later", "better")


class TestListing:
    def test_modes(self, planner):
        dec(planner, "Soon", review="tomorrow")
        dec(planner, "Later", review="2026-12-01")
        dec(planner, "Done")
        planner.dispatch_tool("review_decision", {"decision": "Done", "outcome": "fine", "rating": 3})
        opened = planner.dispatch_tool("get_decisions", {})
        assert opened.splitlines()[0] == "2 decisions (open):" and opened.index("Soon") < opened.index("Later") and "Done" not in opened
        assert planner.dispatch_tool("get_decisions", {"status": "reviewed"}).startswith("1 decision (reviewed):")
        assert planner.dispatch_tool("get_decisions", {"status": "all"}).startswith("3 decisions (all):")
        assert planner.dispatch_tool("get_decisions", {"status": "due"}) == "No decision is waiting for a review."
        assert planner.dispatch_tool("get_decisions", {"status": "x"}) == "Cannot show decisions: status must be open, due, reviewed or all."

    def test_empty(self, planner):
        assert planner.dispatch_tool("get_decisions", {}).startswith("No decisions to show.")
        assert planner.dispatch_tool("get_decisions", {"status": "reviewed"}).startswith("No reviewed decisions yet.")

    def test_due(self, planner):
        import decisions
        dec(planner, "Today", review="2026-10-13")
        dec(planner, "Later", review="in 5 days")
        planner.set_now(__import__("datetime").datetime(2026, 10, 20, 9))
        out = planner.dispatch_tool("get_decisions", {"status": "due"})
        assert out.startswith("2 decisions (due):")
        assert decisions.nudges() == ["Time to review your decision 'Today' (7 days ago)."]
        assert decisions.agenda_lines() == ["Today (review was due 7 days ago)", "Later (review was due 2 days ago)"]

    def test_nudge_today(self, planner):
        import decisions
        dec(planner, "Today", review="today")
        assert decisions.nudges() == ["Time to review your decision 'Today'."]
        assert decisions.agenda_lines() == ["Today (review due today)"]

    def test_calibration_needs_three_rated(self, planner):
        for i, (conf, rating) in enumerate([(9, 5), (9, 4), (3, 2), (4, 3)]):
            dec(planner, f"D{i}", confidence=conf)
            planner.dispatch_tool("review_decision", {"decision": f"D{i}", "outcome": "x", "rating": rating})
            if i == 1:
                assert "averaged" not in planner.dispatch_tool("get_decisions", {"status": "reviewed"})
        out = planner.dispatch_tool("get_decisions", {"status": "reviewed"})
        assert out.splitlines()[-1] == "4 reviewed decisions averaged 3.5/5; the ones you were sure about (8+ out of 10) averaged 4.5/5, the others 2.5/5."

    def test_calibration_without_confidence(self, planner):
        import decisions
        rows3 = [{"status": "reviewed", "rating": r} for r in (1, 2, 3)]
        assert decisions.calibration(rows3) == "3 reviewed decisions averaged 2.0/5."
        assert decisions.calibration(rows3[:2]) is None

    def test_unreadable_review_dates_are_skipped(self, planner):
        import decisions, storage
        storage.save_decisions([{"id": "a", "title": "x", "status": "open", "review": "zz"}, "junk"])
        assert decisions.due_for_review() == []
        assert planner.dispatch_tool("get_decisions", {}).startswith("1 decision (open):")


class TestUpdateDelete:
    def test_update(self, planner):
        dec(planner)
        out = planner.dispatch_tool("update_decision", {"decision": "desk", "fields": {
            "title": "Desk", "options": "a, b", "choice": "a", "reasoning": "r", "expected": "e", "confidence": 5, "review": "in 3 days"}})
        assert out.startswith("Decision updated: Desk: chose 'a' (confidence 5/10), review 2026-10-16 (in 3 days)")

    def test_confidence_can_be_cleared(self, planner):
        dec(planner, confidence=5)
        planner.dispatch_tool("update_decision", {"decision": "desk", "fields": {"confidence": None}})
        assert rows()[0]["confidence"] is None

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"status": "x"}, "cannot change status"), ({"confidence": 99}, "from 1 to 10"),
                                            ({"review": "2020-01-01"}, "cannot be in the past"), ({"title": ""}, "cannot be empty")])
    def test_bad_updates(self, planner, fields, msg):
        dec(planner)
        before = rows()
        assert msg in planner.dispatch_tool("update_decision", {"decision": "desk", "fields": fields})
        assert rows() == before

    def test_delete(self, planner):
        dec(planner)
        assert planner.dispatch_tool("delete_decision", {"decision": "desk"}) == "Deleted decision Switch to standing desk. This can't be undone."
        assert rows() == []
