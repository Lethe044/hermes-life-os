"""Recommendation ledger: every suggestion given is filed, and followed ones are judged by what came after."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


def rec(p="sleep", value=6.1, **kw):
    s = {"type": "threshold", "metric": p, "value": value, "message": f"Average {p} has been low ({value}) lately."}
    s.update(kw)
    return s


def rows():
    import storage
    return storage.load_recs()


def d(p, tool, args=None):
    return p.dispatch_tool(tool, args or {})


class TestRecord:
    def test_new_suggestions_are_filed(self, planner):
        import recledger
        assert recledger.record([rec("sleep"), rec("stress", 7.5), {"type": "streak", "habit": "meditate", "message": "2 days from 30."}]) == 3
        r = rows()
        assert [x["key"] for x in r] == ["threshold:sleep", "threshold:stress", "streak:meditate"]
        assert set(r[0]) == {"id", "key", "type", "metric", "message", "value", "first_seen", "last_seen", "times_seen", "status", "note", "resolved_on"}
        assert (r[0]["status"], r[0]["times_seen"], r[0]["first_seen"], r[0]["value"]) == ("open", 1, "2026-10-13", 6.1)
        assert r[2]["metric"] is None and r[2]["value"] is None

    def test_the_same_open_suggestion_is_counted_once_a_day(self, planner):
        import recledger
        recledger.record([rec("sleep", 6.1)])
        assert recledger.record([rec("sleep", 6.0)]) == 0
        assert rows()[0]["times_seen"] == 1 and rows()[0]["value"] == 6.0 and len(rows()) == 1
        planner.set_now(datetime(2026, 10, 14, 9))
        recledger.record([rec("sleep", 5.9)])
        assert (rows()[0]["times_seen"], rows()[0]["last_seen"], rows()[0]["first_seen"]) == (2, "2026-10-14", "2026-10-13")

    def test_a_resolved_one_that_comes_back_is_a_new_entry(self, planner):
        import recledger
        recledger.record([rec("sleep")])
        d(planner, "mark_recommendation", {"recommendation": "sleep", "status": "followed"})
        assert recledger.record([rec("sleep")]) == 1
        assert [r["status"] for r in rows()] == ["followed", "open"]

    def test_messages_without_a_metric_are_keyed_by_their_text(self, planner):
        import recledger
        recledger.record([{"type": "correlation", "message": "Sleep and mood move together."}])
        recledger.record([{"type": "correlation", "message": "  sleep AND mood move together. "}])
        assert len(rows()) == 1

    @pytest.mark.parametrize("bad", [None, "x", 5, {}, [None, 1, "x", {}, {"message": ""}, {"message": 5}, {"message": "  "}]])
    def test_junk_is_ignored(self, planner, bad):
        import recledger
        assert recledger.record(bad) == 0 and rows() == []

    def test_open_ones_not_seen_for_a_month_expire(self, planner):
        import recledger
        recledger.record([rec("sleep")])
        planner.set_now(datetime(2026, 11, 20, 9))
        recledger.record([])
        assert rows()[0]["status"] == "expired" and rows()[0]["resolved_on"] == "2026-11-20"
        assert d(planner, "get_recommendation_history", {"status": "expired"}).count("sleep") >= 1

    def test_the_ledger_is_capped(self, planner):
        import recledger
        recledger.record([{"type": "x", "message": f"suggestion number {n}"} for n in range(210)])
        assert len(rows()) == 200

    def test_resolved_entries_are_dropped_before_open_ones(self, planner):
        import recledger, storage
        recledger.record([{"type": "x", "message": f"s{n}"} for n in range(200)])
        r = storage.load_recs()
        r[0]["status"] = "skipped"
        storage.save_recs(r)
        recledger.record([{"type": "x", "message": "one more"}])
        assert len(rows()) == 200 and all(x["message"] != "s0" for x in rows())

    def test_get_recommendations_files_what_it_shows(self, planner, monkeypatch):
        import recommendations
        monkeypatch.setattr(recommendations, "get_recommendations", lambda days=14: [rec("sleep")])
        out = d(planner, "get_recommendations")
        assert out == "- Average sleep has been low (6.1) lately."
        assert rows()[0]["key"] == "threshold:sleep"

    def test_a_broken_ledger_never_changes_what_the_user_is_told(self, planner, monkeypatch):
        import recommendations, recledger
        monkeypatch.setattr(recommendations, "get_recommendations", lambda days=14: [rec("sleep")])
        monkeypatch.setattr(recledger, "record", lambda s: 1 / 0)
        assert d(planner, "get_recommendations") == "- Average sleep has been low (6.1) lately."


class TestMark:
    def test_followed_with_a_note(self, planner):
        import recledger
        recledger.record([rec("sleep")])
        out = d(planner, "mark_recommendation", {"recommendation": "sleep", "status": "Followed", "note": " bed at 22:30 "})
        assert out.startswith("Recommendation updated: Average sleep has been low (6.1) lately. [followed; seen 1 time, since 2026-10-13] [id=")
        assert "followed on 2026-10-13: bed at 22:30" in out
        r = rows()[0]
        assert (r["status"], r["resolved_on"], r["note"]) == ("followed", "2026-10-13", "bed at 22:30")

    def test_skipped_and_reopened(self, planner):
        import recledger
        recledger.record([rec("sleep")])
        d(planner, "mark_recommendation", {"recommendation": "sleep", "status": "skipped"})
        assert rows()[0]["resolved_on"] == "2026-10-13"
        d(planner, "mark_recommendation", {"recommendation": "sleep", "status": "open"})
        assert (rows()[0]["status"], rows()[0]["resolved_on"]) == ("open", None)

    @pytest.mark.parametrize("args,msg", [({"status": "done"}, "status must be followed, skipped or open"), ({"status": None}, "status must be"),
                                          ({"status": "followed", "recommendation": "zzz"}, "no recommendation matches 'zzz'"),
                                          ({"status": "followed", "recommendation": ""}, "say which recommendation"),
                                          ({"status": "followed", "note": "n" * 161}, "at most 160")])
    def test_errors(self, planner, args, msg):
        import recledger
        recledger.record([rec("sleep")])
        out = d(planner, "mark_recommendation", {"recommendation": "sleep", **args})
        assert out.startswith("Recommendation not changed: ") and msg in out
        assert rows()[0]["status"] == "open"

    def test_ambiguous(self, planner):
        import recledger
        recledger.record([rec("sleep"), rec("stress", 7.5)])
        assert "matches 2 recommendations" in d(planner, "mark_recommendation", {"recommendation": "average", "status": "skipped"})


class TestHistory:
    def test_listing_by_status(self, planner):
        import recledger
        recledger.record([rec("sleep"), rec("stress", 7.5), rec("hydration", 3.0)])
        d(planner, "mark_recommendation", {"recommendation": "stress", "status": "skipped"})
        assert d(planner, "get_recommendation_history").startswith("2 recommendations (open):")
        assert d(planner, "get_recommendation_history", {"status": "skipped"}).startswith("1 recommendation (skipped):")
        assert d(planner, "get_recommendation_history", {"status": "all"}).startswith("3 recommendations (all):")
        assert d(planner, "get_recommendation_history", {"status": "bad"}).startswith("Cannot show the ledger: status must be one of")

    def test_empty(self, planner):
        assert d(planner, "get_recommendation_history").startswith("No open recommendations in the ledger.")
        assert d(planner, "get_recommendation_history", {"status": "skipped"}) == "No skipped recommendations in the ledger."
        assert d(planner, "get_recommendation_history", {"status": "all"}) == "No recommendations in the ledger."

    def test_long_lists_are_cut(self, planner):
        import recledger
        recledger.record([{"type": "x", "message": f"suggestion {n}"} for n in range(20)])
        out = d(planner, "get_recommendation_history")
        assert out.splitlines()[0] == "20 recommendations (open):" and out.endswith("... and 5 more")


def series(start, values, metric="sleep"):
    out = {}
    for i, v in enumerate(values):
        day = (start + timedelta(days=i)).isoformat()
        out[day] = {metric: v}
    return out


class TestOutcome:
    def row(self, **kw):
        base = {"status": "followed", "metric": "sleep", "resolved_on": "2026-10-13"}
        base.update(kw)
        return base

    def test_better(self, planner):
        import recledger
        from datetime import date
        daily = {**series(date(2026, 10, 6), [6.0] * 7), **series(date(2026, 10, 14), [7.0] * 5)}
        planner.set_now(datetime(2026, 10, 18, 9))
        assert recledger.outcome(self.row(), daily) == "sleep averaged 6.0 in the week before and 7.0 in the 5 days after (+1.0, moving the right way)"

    def test_worse_for_sleep_and_better_for_stress_when_lower(self, planner):
        import recledger
        from datetime import date
        planner.set_now(datetime(2026, 10, 18, 9))
        daily = {**series(date(2026, 10, 6), [7.0] * 7), **series(date(2026, 10, 14), [6.0] * 5)}
        assert recledger.outcome(self.row(), daily).endswith("(-1.0, not moving the right way)")
        stress = {**series(date(2026, 10, 6), [8.0] * 7, "stress"), **series(date(2026, 10, 14), [6.0] * 5, "stress")}
        assert recledger.outcome(self.row(metric="stress"), stress).endswith("(-2.0, moving the right way)")

    def test_about_the_same(self, planner):
        import recledger
        from datetime import date
        planner.set_now(datetime(2026, 10, 18, 9))
        daily = {**series(date(2026, 10, 6), [7.0] * 7), **series(date(2026, 10, 14), [7.1] * 5)}
        assert recledger.outcome(self.row(), daily).endswith("(+0.1, about the same)")

    def test_too_early_and_too_thin(self, planner):
        import recledger
        from datetime import date
        planner.set_now(datetime(2026, 10, 15, 9))
        daily = {**series(date(2026, 10, 6), [6.0] * 7), **series(date(2026, 10, 14), [7.0] * 2)}
        assert recledger.outcome(self.row(), daily) == "Too early to compare: 1 more day(s) with sleep logged are needed."
        assert recledger.outcome(self.row(), series(date(2026, 10, 14), [7.0] * 2)) == "Not enough sleep logs in the week before to compare."

    @pytest.mark.parametrize("kw", [{"status": "skipped"}, {"status": "open"}, {"metric": None}, {"resolved_on": "x"}, {"resolved_on": None}])
    def test_no_outcome_when_it_does_not_apply(self, planner, kw):
        import recledger
        assert recledger.outcome(self.row(**kw), {}) is None

    def test_the_history_shows_the_outcome(self, planner, monkeypatch):
        import recledger
        from datetime import date
        recledger.record([rec("sleep")])
        d(planner, "mark_recommendation", {"recommendation": "sleep", "status": "followed"})
        planner.set_now(datetime(2026, 10, 18, 9))
        monkeypatch.setattr(recledger, "_daily", lambda days=90: {**series(date(2026, 10, 6), [6.0] * 7), **series(date(2026, 10, 14), [7.0] * 5)})
        out = d(planner, "get_recommendation_history", {"status": "followed"})
        assert "    sleep averaged 6.0 in the week before and 7.0 in the 5 days after (+1.0, moving the right way)" in out

    def test_an_unreadable_log_never_breaks_the_history(self, planner, monkeypatch):
        import recledger
        recledger.record([rec("sleep")])
        d(planner, "mark_recommendation", {"recommendation": "sleep", "status": "followed"})
        monkeypatch.setattr(recledger, "_daily", lambda days=90: 1 / 0)
        assert d(planner, "get_recommendation_history", {"status": "followed"}).startswith("1 recommendation (followed):")
