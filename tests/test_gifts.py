"""Gift ideas per person, linked to birthdays in the people list."""

from __future__ import annotations

import pytest


def gift(p, person="Ayse", idea="Poetry book", **kw):
    out = p.dispatch_tool("add_gift_idea", {"person": person, "idea": idea, **kw})
    assert out.startswith("Gift idea added for "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_gifts()


def person(p, name="Ayse", birthday="10-18"):
    p.dispatch_tool("add_person", {"name": name, "birthday": birthday})


class TestAdd:
    def test_shape_and_output(self, planner):
        out = planner.dispatch_tool("add_gift_idea", {"person": " Ayse ", "idea": " Poetry  book ", "price": 25.456,
                                                      "occasion": "birthday", "notes": " n "})
        assert out.startswith("Gift idea added for Ayse: [idea] Poetry book - 25.46 for birthday [id=")
        g = rows()[0]
        assert set(g) == {"id", "person", "idea", "price", "occasion", "status", "notes", "created"}
        assert (g["price"], g["status"], g["notes"], g["created"]) == (25.46, "idea", "n", "2026-10-13")

    def test_person_takes_the_spelling_from_the_people_list(self, planner):
        person(planner, "Ayşe Yılmaz")
        gift(planner, person="ayşe yılmaz")
        assert rows()[0]["person"] == "Ayşe Yılmaz"

    def test_status_aliases_and_no_price(self, planner):
        gift(planner, idea="A", status="purchased")
        gift(planner, idea="B", status="gifted")
        assert [g["status"] for g in rows()] == ["bought", "given"]
        assert rows()[0]["price"] is None and "- " not in planner.dispatch_tool("get_gift_ideas", {}).splitlines()[2].split("] ")[1].split("[id")[0]

    @pytest.mark.parametrize("kw,msg", [
        ({"person": ""}, "person cannot be empty"), ({"person": "p" * 61}, "at most 60"), ({"idea": ""}, "gift idea cannot be empty"),
        ({"idea": "i" * 101}, "at most 100"), ({"price": -1}, "price must be a number"), ({"price": "x"}, "price must be a number"),
        ({"price": True}, "price must be a number"), ({"price": float("inf")}, "price must be a number"),
        ({"price": 10_000_001}, "price must be a number"), ({"status": "lost"}, "status must be one of"),
        ({"occasion": "o" * 41}, "at most 40"), ({"notes": "n" * 161}, "at most 160")])
    def test_rejected(self, planner, kw, msg):
        out = planner.dispatch_tool("add_gift_idea", {"person": "Ayse", "idea": "x", **kw})
        assert out.startswith("Gift idea not added: ") and msg in out
        assert rows() == []

    def test_duplicate_and_limit(self, planner):
        gift(planner)
        assert "already on Ayse's list" in planner.dispatch_tool("add_gift_idea", {"person": "ayse", "idea": "poetry BOOK"})
        gift(planner, person="Mehmet")   # same idea for another person is fine
        import storage
        storage.save_gifts([{"id": f"i{n}", "person": "p", "idea": f"i{n}", "status": "idea"} for n in range(500)])
        assert "already have 500" in planner.dispatch_tool("add_gift_idea", {"person": "x", "idea": "y"})


class TestListing:
    def test_grouped_by_person_with_spent_total(self, planner):
        gift(planner, "Mehmet", "Watch", price=100, status="bought")
        gift(planner, "Ayse", "Scarf", price=40, status="given")
        gift(planner, "Ayse", "Book", price=25)
        gift(planner, "Ayse", "Tea", price=10, status="bought")
        out = planner.dispatch_tool("get_gift_ideas", {}).splitlines()
        assert out[0] == "4 gift entries:"
        assert out[1] == "Ayse (bought or given: 50):"
        assert [l.split("] ")[0].strip("- [ ") for l in out[2:5]] == ["idea", "bought", "given"]
        assert out[5] == "Mehmet (bought or given: 100):"

    def test_filters(self, planner):
        gift(planner, "Ayse", "Scarf", status="bought")
        gift(planner, "Mehmet", "Watch")
        assert planner.dispatch_tool("get_gift_ideas", {"person": "mehm"}).count("Watch") == 1
        assert "Scarf" not in planner.dispatch_tool("get_gift_ideas", {"person": "mehm"})
        assert planner.dispatch_tool("get_gift_ideas", {"status": "bought"}).count("Scarf") == 1
        assert planner.dispatch_tool("get_gift_ideas", {"person": "ayse", "status": "idea"}) == "No gift ideas match."
        assert planner.dispatch_tool("get_gift_ideas", {"status": "lost"}).startswith("Cannot show gift ideas: status must be one of")

    def test_empty(self, planner):
        assert planner.dispatch_tool("get_gift_ideas", {}).startswith("No gift ideas yet.")

    def test_upcoming_birthdays_without_a_bought_gift(self, planner):
        person(planner, "Ayse", "10-18")
        person(planner, "Can", "10-20")
        person(planner, "Far", "03-01")
        gift(planner, "Ayse", "Book")
        gift(planner, "Can", "Game", status="bought")
        assert planner.dispatch_tool("get_gift_ideas", {}).splitlines()[-1] == \
               "Birthdays in the next 30 days with no gift bought: Ayse (in 5 days)"


class TestNudges:
    def test_nudge_needs_an_idea_and_no_bought_gift(self, planner):
        import gifts
        person(planner, "Ayse", "10-18")
        person(planner, "NoIdeas", "10-17")
        person(planner, "Done", "10-16")
        person(planner, "Later", "11-30")
        gift(planner, "Ayse", "Book")
        gift(planner, "Ayse", "Tea")
        gift(planner, "Done", "Game", status="bought")
        gift(planner, "Later", "Pen")
        assert gifts.nudges() == ["Ayse's birthday is in 5 days and no gift is bought yet (2 ideas saved)."]
        assert gifts.agenda_lines() == ["Ayse (in 5 days): 2 ideas saved, none bought"]

    def test_marking_it_bought_silences_the_nudge(self, planner):
        import gifts
        person(planner)
        gid = gift(planner)
        assert gifts.nudges()
        planner.dispatch_tool("update_gift_idea", {"gift": gid, "fields": {"status": "bought"}})
        assert gifts.nudges() == []

    def test_a_broken_people_list_never_raises(self, planner):
        import gifts, storage
        storage.save_people([{"name": "x", "birthday": "zz"}, "junk"])
        assert gifts.nudges() == [] and gifts.agenda_lines() == []


class TestUpdateDelete:
    def test_update(self, planner):
        gid = gift(planner)
        out = planner.dispatch_tool("update_gift_idea", {"gift": gid, "fields": {"idea": "Novel", "price": 30, "occasion": "x",
                                                                                 "status": "given", "notes": "y", "person": "Can"}})
        assert out.startswith("Gift idea updated for Can: [given] Novel - 30 for x")
        assert rows()[0]["price"] == 30

    def test_price_can_be_cleared(self, planner):
        gid = gift(planner, price=5)
        planner.dispatch_tool("update_gift_idea", {"gift": gid, "fields": {"price": ""}})
        assert rows()[0]["price"] is None

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"id": "x"}, "cannot change id"), ({"status": "x"}, "status must be"),
                                            ({"price": -3}, "price must be"), ({"idea": ""}, "cannot be empty")])
    def test_bad_updates(self, planner, fields, msg):
        gift(planner)
        before = rows()
        assert msg in planner.dispatch_tool("update_gift_idea", {"gift": "poetry", "fields": fields})
        assert rows() == before

    def test_delete(self, planner):
        gift(planner)
        assert planner.dispatch_tool("delete_gift_idea", {"gift": "poetry"}) == \
               "Deleted the gift idea 'Poetry book' for Ayse. This can't be undone."
        assert rows() == []
