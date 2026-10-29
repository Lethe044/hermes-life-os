"""search_everything: one search over all planner data."""

from __future__ import annotations

import pytest


def search(p, **kw):
    return p.dispatch_tool("search_everything", kw)


@pytest.fixture()
def data(planner):
    d = planner.dispatch_tool
    d("add_task", {"text": "Book Lisbon hotel", "due": "tomorrow", "tags": ["travel"], "notes": "near the river"})
    d("add_note", {"text": "Lisbon packing ideas", "tags": ["trip"]})
    d("add_list_items", {"items": "lisbon postcards, milk"})
    d("add_person", {"name": "Ana from Lisbon", "notes": "met at the conference"})
    d("add_countdown", {"name": "Lisbon flight", "date": "2026-10-20"})
    d("add_trip", {"name": "Lisbon", "start": "2026-10-20", "end": "2026-10-22", "destination": "Portugal"})
    d("add_recipe", {"name": "Pasta", "ingredients": ["200 g pasta", "1 tin sardines from Lisbon"], "tags": ["quick"]})
    d("log_symptom", {"symptom": "headache", "severity": 4, "triggers": ["noise"], "notes": "after the Lisbon flight"})
    d("add_objective", {"name": "Ship v2", "key_results": [{"name": "Lisbon demo", "target": 1}]})
    d("add_time_block", {"title": "Plan Lisbon", "start": "09:00", "end": "10:00"})
    return planner


class TestSearch:
    def test_grouped_by_area_with_ids(self, data):
        out = search(data, query="lisbon").split("\n")
        assert out[0] == "10 matches for 'lisbon' in 10 areas:"
        areas = [l.split(" (")[0] for l in out[1:] if not l.startswith(" ")]
        assert areas == ["tasks", "notes", "lists", "people", "countdowns", "symptoms", "recipes", "trips", "okrs", "timeblocks"]
        assert all("[id=" in l for l in out if l.startswith("  - "))

    def test_every_word_must_match_in_any_order(self, data):
        assert "tasks (1):" in search(data, query="river lisbon")
        assert search(data, query="river zzz").startswith("Nothing in your planner data matches 'river zzz'.")
        assert "tasks (1):" in search(data, query="HOTEL book")

    def test_matches_look_at_notes_tags_children(self, data):
        assert "recipes (1):" in search(data, query="sardines")           # an ingredient
        assert "symptoms (1):" in search(data, query="noise")             # a trigger
        assert "tasks (1):" in search(data, query="travel")               # a tag
        assert "okrs (1):" in search(data, query="demo")                  # a key result
        assert "trips (1):" in search(data, query="portugal")             # a destination
        assert "people (1):" in search(data, query="conference")          # notes

    def test_name_matches_come_first(self, planner):
        planner.dispatch_tool("add_task", {"text": "Call Sam", "notes": "about the budget"})
        planner.dispatch_tool("add_task", {"text": "Budget review"})
        out = search(planner, query="budget").split("\n")
        assert "Budget review" in out[2] and "Call Sam" in out[3]

    def test_area_filter_and_limit(self, data):
        out = search(data, query="lisbon", areas=["notes", "TRIPS"])
        assert out.startswith("2 matches for 'lisbon' in 2 areas:") and "tasks" not in out
        data.dispatch_tool("add_note", {"text": "Lisbon again"})
        data.dispatch_tool("add_note", {"text": "Lisbon third"})
        out = search(data, query="lisbon", areas="notes", limit=1)
        assert "notes (3):" in out and out.count("\n  - ") == 1 and out.endswith("... and 2 more")

    def test_lines(self, data):
        out = search(data, query="lisbon")
        assert "  - [ ] Book Lisbon hotel (due 2026-10-14) [id=" in out
        assert "  - lisbon postcards (shopping) [id=" in out
        assert "  - Lisbon (2026-10-20 to 2026-10-22) [id=" in out
        assert "  - headache 4/10 on 2026-10-13 [id=" in out

    def test_long_lines_are_shortened(self, planner):
        planner.dispatch_tool("add_note", {"text": "word " * 100})
        line = [l for l in search(planner, query="word").split("\n") if l.startswith("  - ")][0]
        assert "..." in line and len(line) < 130

    @pytest.mark.parametrize("kw,msg", [({"query": ""}, "at least 2 characters"), ({"query": "x"}, "at least 2 characters"),
                                        ({"query": 5}, "at least 2 characters"), ({"query": "a" * 101}, "at most 100"),
                                        ({"query": "a b c d e f g h i"}, "at most 8 words"),
                                        ({"query": "ab", "areas": ["nope"]}, "unknown area 'nope'"), ({"query": "ab", "areas": [3]}, "areas must be"),
                                        ({"query": "ab", "limit": 0}, "limit must be"), ({"query": "ab", "limit": 21}, "limit must be"),
                                        ({"query": "ab", "limit": True}, "limit must be"), ({"query": "ab", "limit": 1.5}, "limit must be")])
    def test_bad_input(self, planner, kw, msg):
        out = search(planner, **kw)
        assert out.startswith("Cannot search: ") and msg in out

    def test_empty_areas_mean_all(self, data):
        assert search(data, query="lisbon", areas=[]).startswith("10 matches")

    def test_nothing_found_points_to_search_logs(self, planner):
        assert "search_logs" in search(planner, query="anything")

    def test_one_broken_store_is_skipped(self, data):
        import storage
        storage.save_notes("garbage")
        storage.save_tasks(["junk", None, 5, {"text": 7}, {"text": "Lisbon ok"}])
        out = search(data, query="lisbon")
        assert "notes" not in out and "tasks (1):" in out and "Lisbon ok" in out

    def test_every_area_has_a_loader(self, planner):
        import finder, storage
        for area, (loader, *_rest) in finder.SOURCES.items():
            assert callable(getattr(storage, loader)), area
        assert set(finder.area_names()) >= {"tasks", "notes", "recipes", "trips", "okrs", "timeblocks", "mealplan"}

    def test_reminders_habits_goals_and_mealplan(self, planner):
        d = planner.dispatch_tool
        d("add_recipe", {"name": "Zesty", "ingredients": ["lemon"]})
        d("plan_meal", {"slot": "dinner", "recipe": "zesty"})
        import storage
        storage.save_habits([{"name": "zen walk", "streak": 3}]); storage.save_goals([{"name": "zen sleep", "metric": "hours"}])
        storage.save_reminders([{"id": "r1", "text": "zen break", "time": "10:00"}])
        out = search(planner, query="zen")
        assert "habits (1):\n  - zen walk (streak 3)" in out and "goals (1):" in out and "reminders (1):\n  - zen break (10:00) [id=r1]" in out
        assert "mealplan (1):\n  - 2026-10-13 dinner: Zesty [id=" in search(planner, query="zesty")
