"""Notes: quick capture with tags, pins and search."""

from __future__ import annotations

from datetime import datetime

import pytest


def add(p, text="Try the new ramen place", **kw):
    out = p.dispatch_tool("add_note", {"text": text, **kw})
    assert out.startswith("Note saved: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_notes()


class TestAdd:
    def test_minimal(self, planner):
        nid = add(planner)
        r = rows()[0]
        assert r == {"id": nid, "text": "Try the new ramen place", "created": "2026-10-13",
                     "updated": "2026-10-13", "tags": [], "pinned": False}

    def test_tags_from_a_string_and_a_list(self, planner):
        add(planner, "a", tags="#Gifts, ayse  Gifts")
        add(planner, "b", tags=["Food", "#food", "  "])
        assert [r["tags"] for r in rows()] == [["gifts", "ayse"], ["food"]]

    def test_pinned(self, planner):
        add(planner, pinned=True)
        assert rows()[0]["pinned"] is True

    def test_text_is_trimmed_but_keeps_line_breaks(self, planner):
        add(planner, "  line one\nline two \n")
        assert rows()[0]["text"] == "line one\nline two"

    @pytest.mark.parametrize("text", ["", "   ", None, 5, "x" * 2001])
    def test_bad_text(self, planner, text):
        assert planner.dispatch_tool("add_note", {"text": text}).startswith("Note not saved: ") and rows() == []

    @pytest.mark.parametrize("tags", [5, [1], ["x" * 31], [f"t{i}" for i in range(11)]])
    def test_bad_tags(self, planner, tags):
        assert planner.dispatch_tool("add_note", {"text": "a", "tags": tags}).startswith("Note not saved: ")
        assert rows() == []

    def test_limit(self, planner):
        import storage
        storage.save_notes([{"id": str(i), "text": "t"} for i in range(5000)])
        assert "already have 5000" in planner.dispatch_tool("add_note", {"text": "x"})

    def test_output_shows_tags_and_pin(self, planner):
        out = planner.dispatch_tool("add_note", {"text": "gift", "tags": ["a", "b"], "pinned": True})
        assert out.startswith("Note saved: [pinned] gift #a #b (2026-10-13) [id=")


class TestList:
    def test_empty(self, planner):
        assert planner.dispatch_tool("list_notes", {}) == "No notes yet."

    def test_pinned_first_then_newest(self, planner):
        add(planner, "old")
        planner.set_now(datetime(2026, 10, 14, 9, 0))
        add(planner, "new")
        planner.set_now(datetime(2026, 10, 15, 9, 0))
        add(planner, "pinned old", pinned=True)
        lines = planner.dispatch_tool("list_notes", {}).split("\n")
        assert lines[0] == "3 notes:"
        assert [l.split(" (")[0] for l in lines[1:]] == ["- [pinned] pinned old", "- new", "- old"]

    def test_filter_by_tag_and_pin(self, planner):
        add(planner, "a", tags="x")
        add(planner, "b", tags="y", pinned=True)
        assert "a" in planner.dispatch_tool("list_notes", {"tag": "#X"}) and "b (" not in planner.dispatch_tool("list_notes", {"tag": "x"})
        assert planner.dispatch_tool("list_notes", {"pinned": True}).startswith("1 note:")
        assert planner.dispatch_tool("list_notes", {"pinned": False}).startswith("1 note:")

    def test_limit(self, planner):
        for i in range(5):
            add(planner, f"n{i}")
        assert planner.dispatch_tool("list_notes", {"limit": 2}).startswith("2 notes:")

    @pytest.mark.parametrize("limit", ["many", 0, -3, None])
    def test_bad_limit(self, planner, limit):
        add(planner)
        assert planner.dispatch_tool("list_notes", {"limit": limit}).startswith("Cannot list notes: ")

    def test_long_notes_are_previewed(self, planner):
        add(planner, "w" * 200)
        assert "..." in planner.dispatch_tool("list_notes", {}) and "w" * 200 not in planner.dispatch_tool("list_notes", {})

    def test_limit_is_capped_at_one_hundred(self, planner):
        import storage
        storage.save_notes([{"id": str(i), "text": f"t{i}", "created": "2026-10-01"} for i in range(150)])
        assert planner.dispatch_tool("list_notes", {"limit": 500}).startswith("100 notes:")


class TestSearch:
    def test_all_words_must_match(self, planner):
        add(planner, "ramen place downtown")
        add(planner, "ramen recipe")
        assert planner.dispatch_tool("search_notes", {"query": "ramen place"}).startswith("1 note:")
        assert planner.dispatch_tool("search_notes", {"query": "RAMEN"}).startswith("2 notes:")

    def test_searches_tags_too(self, planner):
        add(planner, "something", tags="gifts")
        assert planner.dispatch_tool("search_notes", {"query": "#gifts"}).startswith("1 note:")

    def test_no_hits(self, planner):
        assert planner.dispatch_tool("search_notes", {"query": " zzz "}) == "No notes match 'zzz'."

    @pytest.mark.parametrize("query", ["", "  ", None, 5])
    def test_bad_query(self, planner, query):
        assert planner.dispatch_tool("search_notes", {"query": query}).startswith("Cannot search notes: ")

    def test_bad_limit(self, planner):
        add(planner)
        assert "whole number" in planner.dispatch_tool("search_notes", {"query": "ramen", "limit": "x"})


class TestEditDelete:
    def test_resolve_by_id_and_words(self, planner):
        nid = add(planner, "unique phrase here")
        for ref in (nid, "unique phrase", "PHRASE"):
            assert planner.dispatch_tool("update_note", {"note": ref, "fields": {"pinned": True}}).startswith("Note updated: ")

    def test_update_fields_and_updated_date(self, planner):
        add(planner, "old text", tags="a")
        planner.set_now(datetime(2026, 10, 20, 9, 0))
        out = planner.dispatch_tool("update_note", {"note": "old", "fields": {"text": "new text", "tags": "b c", "pinned": True}})
        r = rows()[0]
        assert (r["text"], r["tags"], r["pinned"], r["created"], r["updated"]) == ("new text", ["b", "c"], True, "2026-10-13", "2026-10-20")
        assert "[pinned] new text #b #c" in out

    def test_clear_tags(self, planner):
        add(planner, "t", tags="a")
        planner.dispatch_tool("update_note", {"note": "t", "fields": {"tags": []}})
        assert rows()[0]["tags"] == []

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"bogus": 1}, "cannot change bogus"),
                                            ({"text": " "}, "needs some text"), ({"pinned": "yes"}, "pinned must be true or false"),
                                            ({"tags": 5}, "tags must be"), ("text", "nothing to change")])
    def test_invalid_updates_change_nothing(self, planner, fields, msg):
        add(planner)
        before = rows()
        out = planner.dispatch_tool("update_note", {"note": "ramen", "fields": fields})
        assert out.startswith("Note not changed: ") and msg in out and rows() == before

    def test_partially_invalid_update_changes_nothing(self, planner):
        add(planner, "keep")
        planner.dispatch_tool("update_note", {"note": "keep", "fields": {"text": "changed", "pinned": "x"}})
        assert rows()[0]["text"] == "keep"

    def test_ambiguous_and_unknown(self, planner):
        add(planner, "ramen one")
        add(planner, "ramen two")
        assert "matches 2 notes" in planner.dispatch_tool("delete_note", {"note": "ramen"})
        assert "no note matches 'zzz'" in planner.dispatch_tool("delete_note", {"note": "zzz"})
        assert "say which note" in planner.dispatch_tool("delete_note", {})
        assert len(rows()) == 2

    def test_delete(self, planner):
        add(planner, "one")
        add(planner, "two")
        assert planner.dispatch_tool("delete_note", {"note": "one"}) == "Deleted note: one. This can't be undone."
        assert [r["text"] for r in rows()] == ["two"]


class TestRobustness:
    def test_handwritten_rows(self, planner):
        import storage
        storage.save_notes([{"text": "legacy"}, "junk", None, {"id": "k", "text": "k", "tags": None, "pinned": None}])
        assert planner.dispatch_tool("list_notes", {}).startswith("2 notes:")
        assert planner.dispatch_tool("search_notes", {"query": "legacy"}).startswith("1 note:")
        assert all(r["id"] for r in storage.load_notes() if isinstance(r, dict))

    def test_not_a_list_store(self, planner):
        import storage
        storage.save_notes({"x": 1})
        assert planner.dispatch_tool("list_notes", {}) == "No notes yet."

    def test_separate_from_the_journal(self, planner):
        import storage
        add(planner)
        assert storage.get_all_memory() == []

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        add(planner, "keep me")
        path = backup.run_backup()
        storage.save_notes([])
        restore.restore_backup(path, only="notes", safety_backup=False)
        assert rows()[0]["text"] == "keep me"

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        for n in ("add_note", "list_notes", "search_notes", "update_note", "delete_note"):
            assert n in schemas
        assert schemas["add_note"]["parameters"]["required"] == ["text"]
