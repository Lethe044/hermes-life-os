"""Tasks: add / list / complete / update / delete / summary, due-date parsing, repeats."""

from __future__ import annotations

from datetime import datetime

import pytest


def add(p, text="buy milk", **kw):
    out = p.dispatch_tool("add_task", {"text": text, **kw})
    assert out.startswith("Task added: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_tasks()


class TestParseDue:
    @pytest.mark.parametrize("text,expected", [
        ("today", "2026-10-13"), ("Tomorrow", "2026-10-14"), ("in 3 days", "2026-10-16"),
        ("in 1 day", "2026-10-14"), ("in 2 weeks", "2026-10-27"), ("  IN   2  WEEKS ", "2026-10-27"),
        ("friday", "2026-10-16"), ("fri", "2026-10-16"), ("next friday", "2026-10-16"),
        ("tuesday", "2026-10-20"), ("monday", "2026-10-19"), ("sunday", "2026-10-18"),
        ("2026-12-01", "2026-12-01"), ("2026-1-5", "2026-01-05"), ("2025-01-01", "2025-01-01"),
    ])
    def test_understood(self, planner, text, expected):
        import tasks
        assert tasks.parse_due(text) == expected

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_blank_means_none(self, planner, blank):
        import tasks
        assert tasks.parse_due(blank) is None

    @pytest.mark.parametrize("bad", ["soon", "2026-13-01", "13/10/2026", "in 3 months", "someday", "in -2 days", 5, ["x"]])
    def test_not_understood(self, planner, bad):
        import tasks
        with pytest.raises(ValueError, match="due date"):
            tasks.parse_due(bad)

    def test_weekday_follows_the_day_start_hour(self, planner, monkeypatch):
        import tasks
        monkeypatch.setenv("LIFE_OS_DAY_START_HOUR", "10")  # 09:00 Tuesday is still Monday
        assert tasks.parse_due("today") == "2026-10-12"
        assert tasks.parse_due("tuesday") == "2026-10-13"


class TestAdd:
    def test_minimal(self, planner):
        tid = add(planner)
        row = rows()[0]
        assert row["id"] == tid and row["text"] == "buy milk" and row["due"] is None
        assert row["priority"] == "normal" and row["tags"] == [] and row["repeat"] is None
        assert row["created"] == "2026-10-13" and row["done"] is False

    def test_full(self, planner):
        out = planner.dispatch_tool("add_task", {"text": "  call   dentist ", "due": "friday", "priority": "urgent",
                                                 "tags": ["#Health", "calls", "health"], "notes": " ask about X "})
        row = rows()[0]
        assert row["text"] == "call dentist" and row["due"] == "2026-10-16" and row["priority"] == "high"
        assert row["tags"] == ["health", "calls"] and row["notes"] == "ask about X"
        assert "!high call dentist" in out and "due 2026-10-16 (in 3 days)" in out and "#health #calls" in out

    def test_tags_from_a_string(self, planner):
        add(planner, tags="#home, errands  chores")
        assert rows()[0]["tags"] == ["home", "errands", "chores"]

    def test_repeat_gets_a_due_date_anchor(self, planner):
        add(planner, repeat="weekly")
        assert rows()[0]["due"] == "2026-10-13" and rows()[0]["repeat"] == "weekly"

    @pytest.mark.parametrize("kw,msg", [
        ({"text": ""}, "needs some text"), ({"text": "   "}, "needs some text"), ({"text": None}, "needs some text"),
        ({"text": "x" * 201}, "at most 200"), ({"text": "x", "due": "soon"}, "due date"),
        ({"text": "x", "priority": "huge"}, "priority must be"), ({"text": "x", "repeat": "hourly"}, "repeat must be"),
        ({"text": "x", "tags": ["a" * 31]}, "at most 30"), ({"text": "x", "tags": list("abcdefghijk")}, "at most 10"),
        ({"text": "x", "tags": [1]}, "list of words"),
    ])
    def test_invalid_adds_nothing(self, planner, kw, msg):
        out = planner.dispatch_tool("add_task", kw)
        assert out.startswith("Task not added: ") and msg in out and rows() == []

    def test_priority_and_repeat_aliases(self, planner):
        add(planner, priority="Medium", repeat="every day")
        add(planner, "b", priority="3", repeat="weekday")
        assert [(r["priority"], r["repeat"]) for r in rows()] == [("normal", "daily"), ("low", "weekdays")]

    def test_open_task_cap(self, planner):
        import storage
        storage.save_tasks([{"id": f"t{i}", "text": "x", "done": False} for i in range(1000)])
        assert "1000 open tasks" in planner.dispatch_tool("add_task", {"text": "one more"})

    def test_done_tasks_do_not_count_towards_the_cap(self, planner):
        import storage
        storage.save_tasks([{"id": f"t{i}", "text": "x", "done": True} for i in range(1000)])
        assert planner.dispatch_tool("add_task", {"text": "fine"}).startswith("Task added")


class TestList:
    def test_empty(self, planner):
        assert planner.dispatch_tool("list_tasks", {}) == "No open tasks."
        assert planner.dispatch_tool("list_tasks", {"status": "done"}) == "No finished tasks."
        assert planner.dispatch_tool("list_tasks", {"status": "all"}) == "No tasks yet."

    def test_order_is_overdue_then_due_then_priority_then_undated(self, planner):
        add(planner, "undated")
        add(planner, "later", due="2026-11-01")
        add(planner, "overdue", due="2026-10-10")
        add(planner, "today low", due="today", priority="low")
        add(planner, "today high", due="today", priority="high")
        import tasks
        assert [r["text"] for r in tasks.list_tasks()] == ["overdue", "today high", "today low", "later", "undated"]
        out = planner.dispatch_tool("list_tasks", {})
        assert out.index("overdue") < out.index("today high") < out.index("today low") < out.index("later") < out.index("undated")

    def test_due_labels(self, planner):
        add(planner, "a", due="2026-10-10")
        add(planner, "b", due="2026-10-12")
        add(planner, "c", due="today")
        add(planner, "d", due="tomorrow")
        add(planner, "e", due="in 4 days")
        add(planner, "f", due="2026-12-24")
        out = planner.dispatch_tool("list_tasks", {})
        assert "overdue by 3 days" in out and "overdue by 1 day" in out and "overdue by 1 days" not in out
        assert "(today)" in out and "(tomorrow)" in out and "(in 4 days)" in out and "due 2026-12-24\n" in out + "\n"

    def test_tag_and_due_within_filters(self, planner):
        add(planner, "a", tags="home", due="today")
        add(planner, "b", tags="work", due="in 10 days")
        add(planner, "c", tags="home")
        assert planner.dispatch_tool("list_tasks", {"tag": "#HOME"}).startswith("2 open tasks")
        out = planner.dispatch_tool("list_tasks", {"due_within": 3})
        assert out.startswith("1 open task:") and "a" in out and "work" not in out

    def test_done_filter_is_newest_first(self, planner):
        a, b = add(planner, "first"), add(planner, "second")
        planner.dispatch_tool("complete_task", {"task": a})
        planner.set_now(datetime(2026, 10, 14, 9, 0))
        planner.dispatch_tool("complete_task", {"task": b})
        out = planner.dispatch_tool("list_tasks", {"status": "done"})
        assert out.index("second") < out.index("first") and "done 2026-10-14" in out

    def test_limit(self, planner):
        for i in range(5):
            add(planner, f"t{i}")
        assert planner.dispatch_tool("list_tasks", {"limit": 2}).startswith("2 open tasks")

    def test_bad_arguments(self, planner):
        assert "status must be" in planner.dispatch_tool("list_tasks", {"status": "maybe"})
        assert "Cannot list tasks" in planner.dispatch_tool("list_tasks", {"limit": "many"})


class TestComplete:
    def test_by_id_and_by_words(self, planner):
        a = add(planner, "buy milk")
        add(planner, "call mom")
        assert planner.dispatch_tool("complete_task", {"task": a}) == "Done: buy milk"
        assert planner.dispatch_tool("complete_task", {"task": "MOM"}) == "Done: call mom"
        assert all(r["done"] and r["done_date"] == "2026-10-13" for r in rows())

    def test_already_done(self, planner):
        a = add(planner)
        planner.dispatch_tool("complete_task", {"task": a})
        out = planner.dispatch_tool("complete_task", {"task": a})
        assert out.startswith("Already done: ") and len(rows()) == 1

    def test_unknown_and_ambiguous_and_blank(self, planner):
        add(planner, "call mom")
        add(planner, "call dad")
        assert "no task matches 'zzz'" in planner.dispatch_tool("complete_task", {"task": "zzz"})
        out = planner.dispatch_tool("complete_task", {"task": "call"})
        assert "matches 2 tasks" in out and "Use the id" in out
        assert "say which task" in planner.dispatch_tool("complete_task", {})
        assert not any(r["done"] for r in rows())

    def test_exact_id_beats_text_match(self, planner):
        import storage
        storage.save_tasks([{"id": "abc", "text": "x", "done": False}, {"id": "zzz", "text": "abc thing", "done": False}])
        planner.dispatch_tool("complete_task", {"task": "abc"})
        assert [r["done"] for r in rows()] == [True, False]

    @pytest.mark.parametrize("repeat,due,expected", [
        ("daily", "2026-10-13", "2026-10-14"), ("weekly", "2026-10-13", "2026-10-20"),
        ("monthly", "2026-10-13", "2026-11-13"), ("monthly", "2026-01-31", "2026-10-31"),
        ("weekdays", "2026-10-13", "2026-10-14"), ("weekdays", "2026-10-16", "2026-10-19"),
        ("daily", "2026-10-01", "2026-10-14"), ("weekly", "2026-09-01", "2026-10-20"),
        ("weekdays", "2026-10-10", "2026-10-14"), ("daily", "2026-10-20", "2026-10-21"),
    ])
    def test_repeat_next_due(self, planner, repeat, due, expected):
        tid = add(planner, "water plants", repeat=repeat, due=due)
        out = planner.dispatch_tool("complete_task", {"task": tid})
        assert f"Next {repeat} occurrence" in out
        nxt = [r for r in rows() if not r["done"]][0]
        assert nxt["due"] == expected and nxt["id"] != tid and nxt["repeat"] == repeat
        assert nxt["text"] == "water plants" and nxt["done_date"] is None

    def test_repeating_keeps_tags_priority_notes(self, planner):
        tid = add(planner, "x", repeat="daily", tags="a", priority="high", notes="n")
        planner.dispatch_tool("complete_task", {"task": tid})
        nxt = [r for r in rows() if not r["done"]][0]
        assert (nxt["tags"], nxt["priority"], nxt["notes"]) == (["a"], "high", "n")

    def test_completing_the_copy_chains(self, planner):
        tid = add(planner, "x", repeat="daily")
        planner.dispatch_tool("complete_task", {"task": tid})
        planner.set_now(datetime(2026, 10, 14, 9, 0))
        planner.dispatch_tool("complete_task", {"task": "x"})
        assert [r["due"] for r in rows() if not r["done"]] == ["2026-10-15"]

    def test_non_repeating_creates_nothing(self, planner):
        add(planner)
        planner.dispatch_tool("complete_task", {"task": "milk"})
        assert len(rows()) == 1


class TestUpdate:
    def test_changes_fields(self, planner):
        tid = add(planner, "a", due="today", tags="x")
        out = planner.dispatch_tool("update_task", {"task": tid, "fields": {
            "text": "b", "due": "friday", "priority": "low", "tags": "y z", "notes": "n"}})
        r = rows()[0]
        assert (r["text"], r["due"], r["priority"], r["tags"], r["notes"]) == ("b", "2026-10-16", "low", ["y", "z"], "n")
        assert out.startswith("Task updated: ")

    def test_clearing_due_and_repeat(self, planner):
        tid = add(planner, "a", repeat="weekly")
        planner.dispatch_tool("update_task", {"task": tid, "fields": {"due": "", "repeat": ""}})
        assert rows()[0]["due"] is None and rows()[0]["repeat"] is None

    def test_adding_a_repeat_anchors_the_due_date(self, planner):
        tid = add(planner, "a")
        planner.dispatch_tool("update_task", {"task": tid, "fields": {"repeat": "daily"}})
        assert rows()[0]["due"] == "2026-10-13"

    def test_reopen(self, planner):
        tid = add(planner)
        planner.dispatch_tool("complete_task", {"task": tid})
        planner.dispatch_tool("update_task", {"task": tid, "fields": {"done": False}})
        assert rows()[0]["done"] is False and rows()[0]["done_date"] is None

    @pytest.mark.parametrize("fields,msg", [
        ({}, "nothing to change"), (None, "nothing to change"), ({"bogus": 1}, "cannot change bogus"),
        ({"text": " "}, "needs some text"), ({"due": "soon"}, "due date"), ({"priority": "x"}, "priority must"),
        ({"done": True}, "only be set to false"), ({"notes": 5}, "notes must be text"),
        ({"tags": "a", "repeat": "yearly"}, "repeat must be"),
    ])
    def test_invalid_changes_nothing(self, planner, fields, msg):
        tid = add(planner, "a", tags="keep")
        before = rows()
        out = planner.dispatch_tool("update_task", {"task": tid, "fields": fields})
        assert out.startswith("Task not changed: ") and msg in out and rows() == before

    def test_unknown_task(self, planner):
        assert "no task matches" in planner.dispatch_tool("update_task", {"task": "zz", "fields": {"text": "x"}})


class TestDeleteAndClear:
    def test_delete(self, planner):
        a = add(planner, "a")
        add(planner, "b")
        out = planner.dispatch_tool("delete_task", {"task": a})
        assert out == "Deleted task: a. This can't be undone." and [r["text"] for r in rows()] == ["b"]

    def test_delete_unknown(self, planner):
        assert "no task matches" in planner.dispatch_tool("delete_task", {"task": "q"})

    def test_clear_done(self, planner):
        a, b = add(planner, "a"), add(planner, "b")
        planner.dispatch_tool("complete_task", {"task": a})
        assert planner.dispatch_tool("clear_done_tasks", {}) == "Removed 1 finished task(s)."
        assert [r["id"] for r in rows()] == [b]
        assert planner.dispatch_tool("clear_done_tasks", {}) == "No finished tasks to remove."

    def test_clear_done_older_than(self, planner):
        a, b = add(planner, "a"), add(planner, "b")
        planner.dispatch_tool("complete_task", {"task": a})
        planner.set_now(datetime(2026, 10, 20, 9, 0))
        planner.dispatch_tool("complete_task", {"task": b})
        assert planner.dispatch_tool("clear_done_tasks", {"older_than_days": 5}) == "Removed 1 finished task(s)."
        assert [r["text"] for r in rows()] == ["b"]


class TestSummary:
    def test_empty(self, planner):
        assert planner.dispatch_tool("get_task_summary", {}) == "No tasks yet. Add one with add_task."

    def test_counts(self, planner):
        add(planner, "over", due="2026-10-10")
        add(planner, "today", due="today")
        add(planner, "week", due="in 5 days")
        add(planner, "far", due="in 30 days")
        add(planner, "none")
        done = add(planner, "done")
        planner.dispatch_tool("complete_task", {"task": done})
        out = planner.dispatch_tool("get_task_summary", {})
        assert "5 open task(s): 1 overdue, 1 due today, 1 due in the next 7 days, 1 without a due date." in out
        assert "Finished: 1 today, 1 in the last 7 days." in out and "Overdue: [id=" in out

    def test_finished_window_is_seven_days(self, planner):
        a = add(planner, "a")
        planner.dispatch_tool("complete_task", {"task": a})
        planner.set_now(datetime(2026, 10, 20, 9, 0))  # 7 days later: outside the window
        assert "No tasks yet" in planner.dispatch_tool("get_task_summary", {})


class TestRobustness:
    def test_handwritten_rows_get_ids_and_bad_rows_are_ignored(self, planner):
        import storage
        storage.save_tasks([{"text": "legacy", "done": False}, "junk", None, {"id": "keep", "text": "k", "done": False}])
        out = planner.dispatch_tool("list_tasks", {})
        assert out.startswith("2 open tasks") and "[id=keep]" in out
        assert all(r["id"] for r in storage.load_tasks() if isinstance(r, dict))

    def test_unreadable_due_date_does_not_crash(self, planner):
        import storage
        storage.save_tasks([{"id": "a", "text": "odd", "due": "banana", "done": False}])
        assert "odd" in planner.dispatch_tool("list_tasks", {})
        assert planner.dispatch_tool("get_task_summary", {}).startswith("1 open task(s)")

    def test_not_a_list_store(self, planner):
        import storage
        storage.save_tasks({"oops": 1})
        assert planner.dispatch_tool("list_tasks", {}) == "No open tasks."

    def test_survives_backup_and_restore(self, planner, tmp_path):
        import backup, restore, storage
        add(planner, "keep me", due="friday")
        path = backup.run_backup()
        storage.save_tasks([])
        restore.restore_backup(path, only="tasks", safety_backup=False)
        assert storage.load_tasks()[0]["text"] == "keep me"

    def test_schema_registered(self, planner):
        schemas = {t["function"]["name"]: t["function"] for t in planner.TOOLS}
        for n in ("add_task", "list_tasks", "complete_task", "update_task", "delete_task", "get_task_summary",
                  "clear_done_tasks"):
            assert n in schemas
        assert schemas["add_task"]["parameters"]["required"] == ["text"]
