"""Hydration in the entry tools: the glass log can be listed, edited, deleted and undone,
and the running 'today' counter follows."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

DEMO = Path(__file__).parent.parent / "demo"
sys.path.insert(0, str(DEMO))

import clock  # noqa: E402 - needs the demo/ path set up above


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None) or ""
        if path.startswith(str(DEMO)) and name != "clock":
            del sys.modules[name]
    when = datetime(2026, 10, 12, 9, 0)
    monkeypatch.setattr(clock, "now", lambda: when)
    import tools
    importlib.reload(tools)
    import storage
    storage.set_active_profile(None)
    return tools


def water(app, glasses, **extra):
    app.dispatch_tool("log_hydration", {"glasses": glasses, **extra})


def rows():
    import entries
    return entries.list_logs("hydration", days=400, limit=200)


def state():
    import storage
    return storage.load_hydration()


class TestIds:
    def test_new_glass_logs_carry_ids_and_link_the_journal(self, app):
        import storage
        water(app, 2)
        row = state()["log"][0]
        assert len(row["id"]) == 8
        assert storage.get_all_memory()[-1]["log_id"] == row["id"]

    def test_legacy_log_rows_get_ids_once(self, app):
        import storage
        storage.save_hydration({"goal": 8, "today": 3, "last_date": "2026-10-12",
                                "log": [{"date": "2026-10-12", "glasses": 3, "time": "08:00"}]})
        first = rows()[0]["id"]
        assert rows()[0]["id"] == first == state()["log"][0]["id"]


class TestList:
    def test_list_and_label(self, app):
        water(app, 2)
        out = app.dispatch_tool("list_logs", {"tracker": "hydration"})
        assert "2026-10-12  2 glass(es) of water" in out

    def test_empty(self, app):
        assert app.dispatch_tool("list_logs", {"tracker": "hydration"}) == \
            "No hydration entries found in the last 7 days."

    def test_goal_and_counter_survive_listing(self, app):
        import storage
        water(app, 2)
        h = state()
        h["goal"] = 10
        storage.save_hydration(h)
        rows()
        assert state()["goal"] == 10 and state()["today"] == 2


class TestDeleteAndUndo:
    def test_delete_recounts_today(self, app):
        water(app, 2)
        water(app, 3)
        gone = rows()[0]["id"] if rows()[0]["glasses"] == 3 else rows()[1]["id"]
        out = app.dispatch_tool("delete_log", {"tracker": "hydration", "log_id": gone})
        assert out.startswith("Deleted [id=")
        assert state()["today"] == 2 and len(state()["log"]) == 1

    def test_delete_last_glass_resets_today_to_zero(self, app):
        water(app, 2)
        app.dispatch_tool("delete_log", {"tracker": "hydration", "log_id": rows()[0]["id"]})
        assert state()["today"] == 0

    def test_delete_old_entry_leaves_today_alone(self, app):
        water(app, 4)
        water(app, 2, date="2026-10-09")
        old = next(r for r in rows() if r["date"] == "2026-10-09")["id"]
        app.dispatch_tool("delete_log", {"tracker": "hydration", "log_id": old})
        assert state()["today"] == 4

    def test_delete_removes_journal_entry_and_refreshes_siblings(self, app):
        import storage
        water(app, 2, date="2026-10-09")
        water(app, 3, date="2026-10-09")
        first = next(r for r in rows() if r["glasses"] == 2)["id"]
        app.dispatch_tool("delete_log", {"tracker": "hydration", "log_id": first})
        mem = [m for m in storage.get_all_memory() if m["type"] == "hydration"]
        assert len(mem) == 1 and mem[0]["glasses"] == 3

    def test_undo_hydration(self, app):
        water(app, 2)
        water(app, 3)
        out = app.dispatch_tool("undo_last_log", {"tracker": "hydration"})
        assert "3 glass(es) of water" in out and state()["today"] == 2

    def test_undo_without_tracker_finds_hydration(self, app):
        app.dispatch_tool("log_meal", {"meal_time": "lunch", "food": "x", "calories": 1})
        water(app, 2)
        assert app.dispatch_tool("undo_last_log", {}).startswith("Undid the last hydration entry")
        assert state()["today"] == 0

    def test_delete_entry_cascade_recounts(self, app):
        import storage
        water(app, 2)
        mem = storage.get_all_memory()[-1]
        out = app.dispatch_tool("delete_entry", {"entry_id": mem["id"]})
        assert "linked hydration entry was removed too" in out
        assert state()["today"] == 0 and state()["log"] == []


class TestEdit:
    def test_edit_glasses_recounts_today_and_syncs_journal(self, app):
        import storage
        water(app, 2)
        water(app, 3)
        row = next(r for r in rows() if r["glasses"] == 2)
        out = app.dispatch_tool("edit_log", {"tracker": "hydration", "log_id": row["id"], "fields": {"glasses": 5}})
        assert out.startswith("Updated [id=")
        assert state()["today"] == 8
        mem = {m["log_id"]: m for m in storage.get_all_memory()}
        assert mem[row["id"]]["content"] == "5 glasses water" and mem[row["id"]]["glasses"] == 8

    def test_moving_an_entry_off_today_recounts(self, app):
        water(app, 2)
        water(app, 3)
        row = next(r for r in rows() if r["glasses"] == 3)
        app.dispatch_tool("edit_log", {"tracker": "hydration", "log_id": row["id"], "fields": {"date": "2026-10-09"}})
        assert state()["today"] == 2

    def test_moving_an_entry_onto_today_recounts(self, app):
        water(app, 2)
        water(app, 3, date="2026-10-09")
        row = next(r for r in rows() if r["date"] == "2026-10-09")
        app.dispatch_tool("edit_log", {"tracker": "hydration", "log_id": row["id"], "fields": {"date": "2026-10-12"}})
        assert state()["today"] == 5

    def test_moving_onto_today_when_the_counter_was_stale(self, app):
        import storage
        water(app, 3, date="2026-10-09")
        h = state()
        assert h.get("last_date") != "2026-10-12"
        row = rows()[0]
        app.dispatch_tool("edit_log", {"tracker": "hydration", "log_id": row["id"], "fields": {"date": "2026-10-12"}})
        assert state()["today"] == 3 and state()["last_date"] == "2026-10-12"

    def test_move_updates_journal_stamp(self, app):
        import storage
        water(app, 2)
        app.dispatch_tool("edit_log", {"tracker": "hydration", "log_id": rows()[0]["id"],
                                       "fields": {"date": "2026-10-01"}})
        assert storage.get_all_memory()[-1]["timestamp"] == "2026-10-01T12:00:00Z"

    @pytest.mark.parametrize("fields,msg", [({"glasses": 0}, "1 to 100"), ({"glasses": 101}, "1 to 100"),
                                            ({"glasses": 1.5}, "1 to 100"), ({"date": "2026-10-13"}, "in the future"),
                                            ({"bogus": 1}, "cannot be edited")])
    def test_invalid_edits_change_nothing(self, app, fields, msg):
        water(app, 2)
        before = state()
        out = app.dispatch_tool("edit_log", {"tracker": "hydration", "log_id": rows()[0]["id"], "fields": fields})
        assert out.startswith("Not changed: ") and msg in out
        assert state() == before

    def test_edit_without_any_journal_twin(self, app):
        import storage
        storage.save_hydration({"goal": 8, "today": 2, "last_date": "2026-10-12",
                                "log": [{"date": "2026-10-12", "glasses": 2}]})
        rid = rows()[0]["id"]
        app.dispatch_tool("edit_log", {"tracker": "hydration", "log_id": rid, "fields": {"glasses": 4}})
        assert state()["today"] == 4


class TestRegistry:
    def test_in_the_tool_enum(self, app):
        import entries
        assert "hydration" in entries.tracker_names()
        assert "hydration" in app._TRACKER_NAMES
        assert entries.gap_tracker_names().count("hydration") == 1

    def test_gaps_still_work(self, app):
        water(app, 1, date="2026-10-11")
        assert "2026-10-10" in app.dispatch_tool("get_logging_gaps", {"tracker": "hydration", "days": 2})

    def test_summary_still_reads_the_log(self, app):
        water(app, 4, date="2026-10-10")
        assert "4" in app.dispatch_tool("get_hydration_summary", {"days": 7})
