"""Recently deleted: what the delete and clear tools remove is kept for 30 days."""

from __future__ import annotations

from datetime import datetime

import pytest

# tool, setup calls, the delete call, the store, a word from the removed entry
CASES = [
    ("delete_task", [("add_task", {"text": "Pay rent"})], {"task": "rent"}, "tasks", "Pay rent"),
    ("delete_note", [("add_note", {"text": "Idea about plants"})], {"note": "plants"}, "notes", "Idea about plants"),
    ("delete_person", [("add_person", {"name": "Ayse"})], {"person": "ayse"}, "people", "Ayse"),
    ("delete_subscription", [("add_subscription", {"name": "Netflix", "amount": 15})], {"subscription": "netflix"}, "subscriptions", "Netflix"),
    ("delete_savings_goal", [("add_savings_goal", {"name": "Holiday", "target": 1000})], {"goal": "holiday"}, "savings", "Holiday"),
    ("delete_debt", [("add_debt", {"who": "Ali", "amount": 50, "direction": "owe"})], {"debt": "ali"}, "debts", "Ali"),
    ("delete_countdown", [("add_countdown", {"name": "Exam", "date": "2026-12-01"})], {"countdown": "exam"}, "countdowns", "Exam"),
    ("delete_supply", [("add_supply", {"name": "Vitamin D", "quantity": 30, "per_day": 1})], {"supply": "vitamin"}, "supplies", "Vitamin D"),
    ("delete_time_block", [("add_time_block", {"title": "Deep work", "start": "09:00", "end": "10:00"})], {"block": "deep"}, "timeblocks", "Deep work"),
    ("delete_okr", [("add_objective", {"name": "Get fit"})], {"objective": "fit"}, "okrs", "Get fit"),
    ("delete_recipe", [("add_recipe", {"name": "Soup", "ingredients": ["2 carrots"]})], {"recipe": "soup"}, "recipes", "Soup"),
    ("delete_trip", [("add_trip", {"name": "Rome", "start": "2026-11-01"})], {"trip": "rome"}, "trips", "Rome"),
    ("delete_chore", [("add_chore", {"name": "Water plants", "every": "weekly"})], {"chore": "water"}, "chores", "Water plants"),
    ("delete_expiry", [("add_expiry", {"name": "Passport", "date": "2027-01-01"})], {"item": "passport"}, "expiries", "Passport"),
    ("delete_routine", [("add_routine", {"name": "Morning", "steps": ["a"]})], {"routine": "morning"}, "routines", "Morning"),
    ("delete_gift_idea", [("add_gift_idea", {"person": "Ayse", "idea": "Poetry book"})], {"gift": "poetry"}, "gifts", "Poetry book"),
    ("delete_decision", [("add_decision", {"title": "Standing desk"})], {"decision": "desk"}, "decisions", "Standing desk"),
    ("delete_list", [("add_list_items", {"items": ["milk"], "list": "party"})], {"list": "party"}, "lists", "milk"),
]


def d(p, tool, args=None):
    return p.dispatch_tool(tool, args or {})


def trash_rows():
    import storage
    return storage.load_trash()


class TestCapture:
    @pytest.mark.parametrize("tool,setup,call,store,word", CASES, ids=[c[0] for c in CASES])
    def test_every_watched_tool_files_what_it_removed_and_restore_brings_it_back(self, planner, tool, setup, call, store, word):
        import storage
        for name, args in setup:
            out = d(planner, name, args)
            assert "not added" not in out and "Cannot" not in out, out
        before = storage.load_store(store)
        assert before
        out = d(planner, tool, call)
        assert "Deleted" in out or "Removed" in out or "Cleared" in out, out
        assert storage.load_store(store) == []
        t = trash_rows()
        assert len(t) == 1 and t[0]["store"] == store and t[0]["tool"] == tool and t[0]["rows"] == before
        assert d(planner, "get_trash").count(word) >= 1
        assert d(planner, "restore_deleted", {"item": word.split()[0]}).startswith("Restored ")
        assert storage.load_store(store) == before and trash_rows() == []

    def test_every_watched_tool_is_in_the_schemas(self, planner):
        import trash
        names = {t["function"]["name"] for t in planner.TOOLS}
        assert set(trash.WATCHED) <= names and {c[0] for c in CASES} <= set(trash.WATCHED)

    def test_the_tool_result_is_unchanged(self, planner):
        d(planner, "add_task", {"text": "Pay rent"})
        assert d(planner, "delete_task", {"task": "rent"}) == "Deleted task: Pay rent. This can't be undone."

    def test_a_failed_delete_files_nothing(self, planner):
        d(planner, "add_task", {"text": "Pay rent"})
        assert d(planner, "delete_task", {"task": "zzz"}) == "Task not changed: no task matches 'zzz'. Use list_tasks to see ids."
        assert trash_rows() == []
        import storage
        assert len(storage.load_tasks()) == 1

    def test_clear_done_tasks_is_one_entry_with_all_rows(self, planner):
        for t in ("a", "b", "c", "d"):
            d(planner, "add_task", {"text": f"task {t}"})
            d(planner, "complete_task", {"task": f"task {t}"})
        d(planner, "add_task", {"text": "open one"})
        d(planner, "clear_done_tasks")
        t = trash_rows()
        assert len(t) == 1 and t[0]["count"] == 4 and t[0]["label"] == "task a, task b and 2 more"
        assert d(planner, "restore_deleted", {"item": t[0]["id"]}) == "Restored 4 tasks ('task a, task b and 2 more') to your tasks."
        import storage
        assert len(storage.load_tasks()) == 5

    def test_checked_list_items_and_removed_items(self, planner):
        d(planner, "add_list_items", {"items": ["milk", "eggs", "bread"]})
        d(planner, "check_list_item", {"items": ["milk", "eggs"]})
        d(planner, "clear_checked_items")
        assert trash_rows()[0]["label"] == "milk, eggs"
        d(planner, "remove_list_items", {"item": "bread"})
        assert [e["label"] for e in trash_rows()] == ["milk, eggs", "bread"]

    def test_clear_meals_and_the_meal_plan(self, planner):
        d(planner, "add_recipe", {"name": "Soup", "ingredients": ["2 carrots"]})
        d(planner, "plan_meal", {"slot": "dinner", "recipe": "soup", "date": "2026-10-13", "repeat_days": 2})
        d(planner, "clear_meals", {"date": "2026-10-13"})
        d(planner, "clear_meals", {"date": "2026-10-14"})
        t = trash_rows()
        assert len(t) == 2 and all(e["store"] == "mealplan" for e in t)
        d(planner, "restore_deleted", {"item": t[0]["id"]})
        d(planner, "restore_deleted", {"item": t[1]["id"]})
        import storage
        assert len(storage.load_mealplan()) == 2

    def test_deleting_a_part_of_an_entry_is_not_filed(self, planner):
        d(planner, "add_objective", {"name": "Fit", "key_results": [{"name": "Run", "target": 10}]})
        d(planner, "delete_okr", {"objective": "fit", "key_result": "run"})
        assert trash_rows() == []

    def test_rows_without_an_id_are_ignored(self, planner):
        import storage
        storage.save_tasks([{"text": "no id", "done": False}])
        d(planner, "clear_done_tasks")
        assert trash_rows() == []

    def test_an_unreadable_store_never_breaks_the_delete(self, planner, monkeypatch):
        import storage
        d(planner, "add_task", {"text": "Pay rent"})
        monkeypatch.setattr(storage, "load_trash", lambda: 1 / 0)
        assert d(planner, "delete_task", {"task": "rent"}) == "Deleted task: Pay rent. This can't be undone."
        assert storage.load_tasks() == []

    def test_a_recipe_note_after_restoring(self, planner):
        d(planner, "add_recipe", {"name": "Soup", "ingredients": ["2 carrots"]})
        d(planner, "delete_recipe", {"recipe": "soup"})
        assert d(planner, "restore_deleted", {"item": "soup"}).endswith("Planned meals that used it stay as text.")


class TestRetention:
    def test_entries_expire_after_30_days(self, planner):
        d(planner, "add_task", {"text": "Pay rent"})
        d(planner, "delete_task", {"task": "rent"})
        planner.set_now(datetime(2026, 11, 11, 9))   # 29 days later
        assert "1 day left" in d(planner, "get_trash")
        planner.set_now(datetime(2026, 11, 12, 9))   # 30 days later
        assert d(planner, "get_trash").startswith("The trash is empty.")
        assert "no deleted item matches" in d(planner, "restore_deleted", {"item": "rent"})

    def test_expired_entries_are_purged_when_something_new_is_filed(self, planner):
        d(planner, "add_task", {"text": "Old"})
        d(planner, "delete_task", {"task": "old"})
        planner.set_now(datetime(2026, 12, 25, 9))
        d(planner, "add_task", {"text": "New"})
        d(planner, "delete_task", {"task": "new"})
        assert [e["label"] for e in trash_rows()] == ["New"]

    def test_at_most_100_entries(self, planner):
        for n in range(105):
            d(planner, "add_task", {"text": f"t{n}"})
            d(planner, "delete_task", {"task": f"t{n}"})
        t = trash_rows()
        assert len(t) == 100 and t[0]["label"] == "t5" and t[-1]["label"] == "t104"


class TestRestore:
    def test_by_id_and_by_words(self, planner):
        d(planner, "add_task", {"text": "Pay rent"})
        d(planner, "delete_task", {"task": "rent"})
        tid = trash_rows()[0]["id"]
        assert d(planner, "restore_deleted", {"item": tid}) == "Restored 'Pay rent' to your tasks."
        assert "Pay rent" in d(planner, "list_tasks")

    def test_a_second_restore_finds_nothing(self, planner):
        d(planner, "add_task", {"text": "Pay rent"})
        d(planner, "delete_task", {"task": "rent"})
        d(planner, "restore_deleted", {"item": "rent"})
        assert "no deleted item matches" in d(planner, "restore_deleted", {"item": "rent"})

    def test_ambiguous_words(self, planner):
        for t in ("Pay rent", "Pay tax"):
            d(planner, "add_task", {"text": t})
            d(planner, "delete_task", {"task": t})
        out = d(planner, "restore_deleted", {"item": "pay"})
        assert out.startswith("Not restored: 'pay' matches 2 deleted items")

    def test_missing_reference(self, planner):
        assert d(planner, "restore_deleted", {}).startswith("Not restored: say which deleted item")

    def test_rows_that_are_already_back_are_skipped(self, planner):
        import storage
        d(planner, "add_task", {"text": "Pay rent"})
        row = storage.load_tasks()[0]
        d(planner, "delete_task", {"task": "rent"})
        storage.save_tasks([row])                                     # the same task was put back by other means
        out = d(planner, "restore_deleted", {"item": "rent"})
        assert out.startswith("Not restored: everything in 'Pay rent' is already back")
        assert trash_rows() == [] and len(storage.load_tasks()) == 1

    def test_partial_overlap(self, planner):
        import storage
        d(planner, "add_list_items", {"items": ["milk", "eggs"]})
        rows = storage.load_lists()
        d(planner, "remove_list_items", {"items": ["milk", "eggs"]})
        storage.save_lists([rows[0]])
        out = d(planner, "restore_deleted", {"item": "eggs"})
        assert out == "Restored 1 list item ('milk, eggs') to your lists (1 already existed)."

    def test_an_entry_for_an_unknown_store(self, planner):
        import storage
        storage.save_trash([{"id": "t1", "store": "nope", "tool": "x", "deleted": "2026-10-13", "label": "odd", "rows": [{"id": "a"}]}])
        assert "cannot be restored" in d(planner, "restore_deleted", {"item": "odd"})

    def test_restoring_does_not_touch_other_rows(self, planner):
        import storage
        d(planner, "add_task", {"text": "Pay rent"})
        d(planner, "add_task", {"text": "Call mum"})
        d(planner, "delete_task", {"task": "rent"})
        d(planner, "restore_deleted", {"item": "rent"})
        assert sorted(t["text"] for t in storage.load_tasks()) == ["Call mum", "Pay rent"]


class TestListing:
    def test_newest_first_and_kind_filter(self, planner):
        d(planner, "add_task", {"text": "Pay rent"})
        d(planner, "delete_task", {"task": "rent"})
        planner.set_now(datetime(2026, 10, 14, 9))
        d(planner, "add_person", {"name": "Ayse"})
        d(planner, "delete_person", {"person": "ayse"})
        lines = d(planner, "get_trash").splitlines()
        assert lines[0] == "2 deleted items (kept 30 days, restore with restore_deleted):"
        assert lines[1].startswith("- 2026-10-14 person 'Ayse' (by delete_person, 30 days left)")
        assert lines[2].startswith("- 2026-10-13 task 'Pay rent' (by delete_task, 29 days left)")
        assert d(planner, "get_trash", {"kind": "tasks"}).count("task 'Pay rent'") == 1
        assert d(planner, "get_trash", {"kind": "person"}).count("Ayse") == 1
        assert d(planner, "get_trash", {"kind": "recipe"}) == "Nothing matching in the trash."
        assert d(planner, "get_trash", {"kind": "toaster"}).startswith("Cannot show the trash: unknown kind 'toaster'")

    def test_empty(self, planner):
        assert d(planner, "get_trash").startswith("The trash is empty.")


class TestEmpty:
    def make(self, planner):
        for day, text in ((13, "Old one"), (20, "Mid one"), (25, "New one")):
            planner.set_now(datetime(2026, 10, day, 9))
            d(planner, "add_task", {"text": text})
            d(planner, "delete_task", {"task": text})
        planner.set_now(datetime(2026, 10, 26, 9))

    def test_one_item(self, planner):
        self.make(planner)
        assert d(planner, "empty_trash", {"item": "mid"}) == "Permanently removed 1 deleted item from the trash. This can't be undone."
        assert [e["label"] for e in trash_rows()] == ["Old one", "New one"]

    def test_older_than_days(self, planner):
        self.make(planner)
        assert d(planner, "empty_trash", {"older_than_days": 5}).startswith("Permanently removed 2 deleted items")
        assert [e["label"] for e in trash_rows()] == ["New one"]

    def test_everything(self, planner):
        self.make(planner)
        assert d(planner, "empty_trash").startswith("Permanently removed 3 deleted items")
        assert trash_rows() == []

    def test_zero_days_means_everything(self, planner):
        self.make(planner)
        assert d(planner, "empty_trash", {"older_than_days": 0}).startswith("Permanently removed 3 deleted items")

    @pytest.mark.parametrize("days", [-1, 31, 2.5, True, "x"])
    def test_bad_days(self, planner, days):
        self.make(planner)
        assert d(planner, "empty_trash", {"older_than_days": days}).startswith("Trash not emptied: older_than_days must be")
        assert len(trash_rows()) == 3

    def test_unknown_item(self, planner):
        assert d(planner, "empty_trash", {"item": "zzz"}).startswith("Trash not emptied: no deleted item matches")
