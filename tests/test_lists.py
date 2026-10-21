"""Lists: named checklists (shopping, packing, ...)."""

from __future__ import annotations

import pytest


def add(p, items, **kw):
    return p.dispatch_tool("add_list_items", {"items": items, **kw})


def rows():
    import storage
    return storage.load_lists()


def texts(list_name="shopping"):
    return [r["text"] for r in rows() if r["list"] == list_name]


class TestAdd:
    def test_comma_separated_string(self, planner):
        assert add(planner, "milk, eggs, bread") == "Added to shopping: milk, eggs, bread."
        assert texts() == ["milk", "eggs", "bread"]

    def test_newlines_and_blank_parts(self, planner):
        add(planner, "milk,, \n eggs ,\nbread,")
        assert texts() == ["milk", "eggs", "bread"]

    def test_list_of_items(self, planner):
        add(planner, ["milk", "  two   words "])
        assert texts() == ["milk", "two words"]

    def test_row_shape(self, planner):
        add(planner, ["milk"], quantity="2 l")
        r = rows()[0]
        assert r["quantity"] == "2 l" and r["done"] is False and r["added"] == "2026-10-13" and r["done_date"] is None
        assert len(r["id"]) == 8

    def test_custom_list_name_is_normalized(self, planner):
        assert add(planner, "tent", list="  Camping   TRIP ") == "Added to camping trip: tent."
        assert texts("camping trip") == ["tent"]

    def test_blank_list_name_is_the_default(self, planner):
        add(planner, "milk", list="  ")
        assert texts() == ["milk"]

    def test_duplicates_are_skipped_case_insensitively(self, planner):
        add(planner, "milk")
        assert add(planner, ["MILK", "eggs"]) == "Added to shopping: eggs. Already on the list: MILK."
        assert texts() == ["milk", "eggs"]

    def test_only_duplicates_adds_nothing(self, planner):
        add(planner, "milk")
        assert add(planner, "milk") == "Already on the list: milk."
        assert len(rows()) == 1

    def test_a_ticked_item_can_be_added_again(self, planner):
        add(planner, "milk")
        planner.dispatch_tool("check_list_item", {"item": "milk"})
        assert add(planner, "milk") == "Added to shopping: milk."
        assert len(rows()) == 2

    def test_same_item_on_two_lists(self, planner):
        add(planner, "milk")
        add(planner, "milk", list="party")
        assert len(rows()) == 2

    @pytest.mark.parametrize("items", ["", "   ", ",,", [], None, 5, {"a": 1}])
    def test_nothing_to_add(self, planner, items):
        assert add(planner, items).startswith("Not added: ") and rows() == []

    @pytest.mark.parametrize("items", [["ok", ""], ["ok", 5], ["ok", None], ["x" * 121]])
    def test_a_bad_item_adds_nothing(self, planner, items):
        assert add(planner, items).startswith("Not added: ") and rows() == []

    def test_too_many_in_one_call(self, planner):
        assert "at most 50" in add(planner, [f"i{n}" for n in range(51)])
        assert rows() == []

    def test_quantity_needs_a_single_item(self, planner):
        assert "only be given when adding one item" in add(planner, "a, b", quantity="2")
        assert rows() == []

    def test_quantity_length(self, planner):
        assert "at most 30" in add(planner, "a", quantity="q" * 31)

    def test_blank_quantity_is_none(self, planner):
        add(planner, "a, b", quantity="  ")
        assert all(r["quantity"] is None for r in rows())

    @pytest.mark.parametrize("name", [5, ["x"], "n" * 41])
    def test_bad_list_names(self, planner, name):
        assert add(planner, "a", list=name).startswith("Not added: ") and rows() == []

    def test_total_limit(self, planner):
        import storage
        storage.save_lists([{"id": str(i), "list": "x", "text": f"t{i}"} for i in range(3000)])
        assert "lists are full" in add(planner, "one more")


class TestShow:
    def test_empty(self, planner):
        assert planner.dispatch_tool("get_list", {}) == "The shopping list is empty."
        assert planner.dispatch_tool("get_list", {"list": "x"}) == "The x list is empty."
        assert planner.dispatch_tool("get_lists", {}) == "No lists yet. Add items with add_list_items."

    def test_open_first_then_ticked(self, planner):
        add(planner, "a, b, c")
        planner.dispatch_tool("check_list_item", {"item": "a"})
        out = planner.dispatch_tool("get_list", {}).split("\n")
        assert out[0] == "Shopping: 2 to get, 1 ticked"
        assert out[1].startswith("[ ] b") and out[2].startswith("[ ] c") and out[3].startswith("[x] a")

    def test_quantity_is_shown(self, planner):
        add(planner, "rice", quantity="1 kg")
        assert "[ ] rice (1 kg) [id=" in planner.dispatch_tool("get_list", {})

    def test_overview_sorted_by_size(self, planner):
        add(planner, "a", list="small")
        add(planner, "a, b, c", list="big")
        planner.dispatch_tool("check_list_item", {"item": "a", "list": "big"})
        assert planner.dispatch_tool("get_lists", {}) == "2 lists:\n- big: 2 open, 1 ticked\n- small: 1 open"

    def test_one_list_does_not_show_another(self, planner):
        add(planner, "a")
        add(planner, "b", list="other")
        assert planner.dispatch_tool("get_list", {}).split("\n")[1:] == [f"[ ] a [id={rows()[0]['id']}]"]


class TestCheck:
    def test_tick_by_words_and_by_id(self, planner):
        add(planner, "whole milk, eggs")
        assert planner.dispatch_tool("check_list_item", {"item": "milk"}) == "Ticked: whole milk."
        eid = [r for r in rows() if r["text"] == "eggs"][0]["id"]
        assert planner.dispatch_tool("check_list_item", {"item": eid}) == "Ticked: eggs."
        assert all(r["done"] and r["done_date"] == "2026-10-13" for r in rows())

    def test_several_at_once(self, planner):
        add(planner, "a, b, c")
        assert planner.dispatch_tool("check_list_item", {"items": ["a", "b"]}) == "Ticked: a, b."
        assert [r["done"] for r in rows()] == [True, True, False]

    def test_item_and_items_combine_without_duplicates(self, planner):
        add(planner, "a, b")
        assert planner.dispatch_tool("check_list_item", {"item": "a", "items": ["a", "b"]}) == "Ticked: a, b."

    def test_untick(self, planner):
        add(planner, "a")
        planner.dispatch_tool("check_list_item", {"item": "a"})
        assert planner.dispatch_tool("check_list_item", {"item": "a", "checked": False}) == "Unticked: a."
        assert rows()[0]["done"] is False and rows()[0]["done_date"] is None

    def test_all_or_nothing(self, planner):
        add(planner, "a, b")
        out = planner.dispatch_tool("check_list_item", {"items": ["a", "zzz"]})
        assert out.startswith("Not changed: no item matches 'zzz'")
        assert [r["done"] for r in rows()] == [False, False]

    def test_ambiguous_words_list_candidates(self, planner):
        add(planner, "apple juice, apple pie")
        out = planner.dispatch_tool("check_list_item", {"item": "apple"})
        assert "matches 2 items" in out and "apple pie" in out and "Use the id" in out
        assert not any(r["done"] for r in rows())

    def test_exact_text_beats_a_longer_match(self, planner):
        add(planner, "milk, milk chocolate")
        assert planner.dispatch_tool("check_list_item", {"item": "milk"}) == "Ticked: milk."

    def test_open_item_preferred_over_ticked_duplicate(self, planner):
        add(planner, "milk")
        planner.dispatch_tool("check_list_item", {"item": "milk"})
        add(planner, "milk")
        assert planner.dispatch_tool("check_list_item", {"item": "milk"}) == "Ticked: milk."
        assert all(r["done"] for r in rows())

    def test_restricting_to_a_list(self, planner):
        add(planner, "milk")
        add(planner, "milk", list="party")
        planner.dispatch_tool("check_list_item", {"item": "milk", "list": "party"})
        assert [(r["list"], r["done"]) for r in rows()] == [("shopping", False), ("party", True)]

    def test_same_words_on_two_lists_is_ambiguous_without_a_list(self, planner):
        add(planner, "milk")
        add(planner, "milk", list="party")
        assert "matches 2 items" in planner.dispatch_tool("check_list_item", {"item": "milk"})

    @pytest.mark.parametrize("args", [{}, {"item": ""}, {"items": []}, {"items": "milk"}, {"item": "  "}])
    def test_missing_reference(self, planner, args):
        add(planner, "milk")
        assert planner.dispatch_tool("check_list_item", args).startswith("Not changed: ")

    def test_too_many_references(self, planner):
        assert "at most 50" in planner.dispatch_tool("check_list_item", {"items": ["a"] * 51})


class TestRemoveAndClear:
    def test_remove(self, planner):
        add(planner, "a, b, c")
        assert planner.dispatch_tool("remove_list_items", {"items": ["a", "c"]}) == "Removed: a, c."
        assert texts() == ["b"]

    def test_remove_unknown_changes_nothing(self, planner):
        add(planner, "a")
        assert planner.dispatch_tool("remove_list_items", {"items": ["a", "zzz"]}).startswith("Not removed: ")
        assert texts() == ["a"]

    def test_remove_by_id_in_a_list(self, planner):
        add(planner, "a", list="x")
        rid = rows()[0]["id"]
        assert planner.dispatch_tool("remove_list_items", {"item": rid, "list": "x"}) == "Removed: a."
        assert planner.dispatch_tool("remove_list_items", {"item": rid}).startswith("Not removed: ")

    def test_clear_checked_one_list(self, planner):
        add(planner, "a, b")
        add(planner, "c", list="x")
        planner.dispatch_tool("check_list_item", {"items": ["a"]})
        planner.dispatch_tool("check_list_item", {"item": "c"})
        assert planner.dispatch_tool("clear_checked_items", {"list": "shopping"}) == "Removed 1 ticked item(s)."
        assert [(r["list"], r["text"]) for r in rows()] == [("shopping", "b"), ("x", "c")]

    def test_clear_checked_everywhere(self, planner):
        add(planner, "a")
        add(planner, "c", list="x")
        planner.dispatch_tool("check_list_item", {"item": "a"})
        planner.dispatch_tool("check_list_item", {"item": "c"})
        assert planner.dispatch_tool("clear_checked_items", {}) == "Removed 2 ticked item(s)."
        assert rows() == []

    def test_nothing_ticked(self, planner):
        add(planner, "a")
        assert planner.dispatch_tool("clear_checked_items", {}) == "Nothing was ticked."

    def test_delete_list(self, planner):
        add(planner, "a, b", list="x")
        add(planner, "c")
        assert planner.dispatch_tool("delete_list", {"list": "X"}) == "Deleted the x list (2 item(s)). This can't be undone."
        assert texts() == ["c"]

    def test_delete_unknown_list(self, planner):
        assert planner.dispatch_tool("delete_list", {"list": "nope"}) == "Not deleted: there is no list called 'nope'."

    def test_delete_list_needs_a_name_but_not_the_default(self, planner):
        add(planner, "a")
        assert planner.dispatch_tool("delete_list", {}).startswith("Deleted the shopping list")


class TestRobustness:
    def test_handwritten_rows(self, planner):
        import storage
        storage.save_lists([{"text": "legacy"}, "junk", None, {"id": "k", "list": "", "text": "k"}])
        out = planner.dispatch_tool("get_list", {})
        assert out.startswith("Shopping: 2 to get") and all(r["id"] for r in storage.load_lists() if isinstance(r, dict))
        assert planner.dispatch_tool("get_lists", {}) == "1 list:\n- shopping: 2 open"

    def test_not_a_list_store(self, planner):
        import storage
        storage.save_lists({"x": 1})
        assert planner.dispatch_tool("get_lists", {}).startswith("No lists yet")

    def test_does_not_touch_the_journal(self, planner):
        import storage
        add(planner, "a")
        assert storage.get_all_memory() == []

    def test_backup_restore_round_trip(self, planner):
        import backup, restore, storage
        add(planner, "keep me")
        path = backup.run_backup()
        storage.save_lists([])
        restore.restore_backup(path, only="lists", safety_backup=False)
        assert texts() == ["keep me"]

    def test_schemas(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        for n in ("add_list_items", "get_list", "get_lists", "check_list_item", "remove_list_items",
                  "clear_checked_items", "delete_list"):
            assert n in schemas
        assert schemas["add_list_items"]["parameters"]["required"] == ["items"]
        assert schemas["check_list_item"]["parameters"]["required"] == []
