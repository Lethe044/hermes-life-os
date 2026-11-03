"""Library backlog."""

from __future__ import annotations

from datetime import datetime


def test_add_and_list(planner):
    d = planner.dispatch_tool
    assert d("add_library_item", {"title": "Dune", "creator": "Frank Herbert"}).startswith("Added: Dune by Frank Herbert (book, want)")
    assert "already in your library" in d("add_library_item", {"title": "dune"})
    assert d("add_library_item", {"title": "Dune", "kind": "movie"}).startswith("Added:")
    assert "2 items (all)" in d("get_library", {})
    assert "1 item (book)" in d("get_library", {"kind": "book"})
    assert d("get_library", {"kind": "vinyl"}).startswith("Cannot show the library:")
    assert d("add_library_item", {"title": "x", "kind": "vinyl"}).startswith("Item not added:")


def test_status_flow_and_progress(planner):
    import library
    d = planner.dispatch_tool
    d("add_library_item", {"title": "Hades", "kind": "game"})
    d("update_library_item", {"item": "hades", "fields": {"progress": 30}})
    row = library.listing()[0]
    assert row["status"] == "doing" and row["started"] == "2026-10-13"
    d("update_library_item", {"item": "hades", "fields": {"progress": 100}})
    row = library.listing()[0]
    assert row["status"] == "done" and row["finished"] == "2026-10-13"
    d("update_library_item", {"item": "hades", "fields": {"status": "want"}})
    row = library.listing()[0]
    assert row["progress"] == 0 and row["finished"] is None


def test_finish_with_rating_and_validation(planner):
    d = planner.dispatch_tool
    d("add_library_item", {"title": "Arrival", "kind": "movie"})
    assert "movie, done, 4/5" in d("finish_library_item", {"item": "arrival", "rating": 4})
    assert "from 1 to 5" in d("update_library_item", {"item": "arrival", "fields": {"rating": 9}})
    assert d("update_library_item", {"item": "arrival", "fields": {"colour": 1}}).startswith("Item not changed:")
    assert d("update_library_item", {"item": "arrival", "fields": {"progress": 101}}).startswith("Item not changed:")


def test_suggest_prefers_in_progress_then_oldest(planner):
    import library
    d = planner.dispatch_tool
    assert d("suggest_library_item", {}).startswith("Nothing is waiting")
    d("add_library_item", {"title": "First"})
    planner.set_now(datetime(2026, 10, 14, 9, 0))
    d("add_library_item", {"title": "Second"})
    assert "Next up: First" in d("suggest_library_item", {})
    d("update_library_item", {"item": "second", "fields": {"status": "doing"}})
    assert "Next up: Second" in d("suggest_library_item", {}) and "already started" in d("suggest_library_item", {})
    assert library.suggest("movie") is None


def test_stats(planner):
    d = planner.dispatch_tool
    d("add_library_item", {"title": "A", "kind": "book"})
    d("add_library_item", {"title": "B", "kind": "show"})
    d("finish_library_item", {"item": "A", "rating": 5})
    d("finish_library_item", {"item": "B", "rating": 3})
    out = d("get_library_stats", {})
    assert "2 items - 0 in progress, 0 waiting, 2 done" in out and "average rating 4.0/5" in out and "Five-star picks: A" in out
    assert "Nothing finished in 2020" in d("get_library_stats", {"year": 2020})
    assert d("get_library_stats", {"year": "x"}).startswith("Cannot show stats:")


def test_stale_nudge_and_delete(planner):
    import library
    d = planner.dispatch_tool
    d("add_library_item", {"title": "Slow book", "status": "doing"})
    assert library.nudges() == []
    planner.set_now(datetime(2026, 11, 20, 9, 0))
    assert "Slow book" in library.nudges()[0]
    assert "Deleted Slow book" in d("delete_library_item", {"item": "slow"})
    assert d("delete_library_item", {"item": "slow"}).startswith("Item not deleted:")
