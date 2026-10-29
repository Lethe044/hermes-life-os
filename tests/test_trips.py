"""Trips: dates, packing lists and itineraries."""

from __future__ import annotations

from datetime import datetime

import pytest


def trip(p, name="Lisbon", start="2026-10-20", end="2026-10-24", **kw):
    out = p.dispatch_tool("add_trip", {"name": name, "start": start, "end": end, **kw})
    assert out.startswith("Trip added: "), out
    return out.split("[id=")[1].split("]")[0]


def rows():
    import storage
    return storage.load_trips()


def texts(t=0):
    return [i["text"] for i in rows()[t]["packing"]]


class TestAdd:
    def test_shape_and_output(self, planner):
        out = planner.dispatch_tool("add_trip", {"name": " Lisbon ", "start": "2026-10-20", "end": "2026-10-24",
                                                 "destination": "Portugal", "budget": "800.505", "notes": " n "})
        assert out.startswith("Trip added: Lisbon (Portugal): 2026-10-20 to 2026-10-24 (5 days), in 7 days [id=")
        t = rows()[0]
        assert set(t) == {"id", "name", "destination", "start", "end", "budget", "notes", "created", "packing", "itinerary"}
        assert (t["budget"], t["notes"], t["created"], t["packing"], t["itinerary"]) == (800.5, "n", "2026-10-13", [], [])

    def test_one_day_trip_and_relative_dates(self, planner):
        out = planner.dispatch_tool("add_trip", {"name": "Day out", "start": "tomorrow"})
        assert out.startswith("Trip added: Day out: 2026-10-14 (1 day), starts tomorrow [id=")
        assert rows()[0]["end"] == "2026-10-14"
        planner.dispatch_tool("add_trip", {"name": "Next", "start": "in 2 weeks", "end": "in 3 weeks"})
        assert (rows()[1]["start"], rows()[1]["end"]) == ("2026-10-27", "2026-11-03")

    def test_destination_same_as_name_is_not_repeated(self, planner):
        out = planner.dispatch_tool("add_trip", {"name": "Rome", "destination": "rome", "start": "2026-11-01"})
        assert out.startswith("Trip added: Rome: 2026-11-01 (1 day)")

    @pytest.mark.parametrize("kw,msg", [
        ({"name": ""}, "needs a name"), ({"name": "n" * 61}, "at most 60"), ({"start": None}, "needs a start date"),
        ({"start": "never"}, "couldn't understand"), ({"end": "2026-10-10"}, "end date cannot be before"),
        ({"end": "2027-03-01"}, "at most 120 days"), ({"start": "2029-01-01", "end": "2029-01-02"}, "within 730 days"),
        ({"destination": "d" * 61}, "at most 60"), ({"destination": 5}, "destination must be text"),
        ({"budget": 0}, "positive number"), ({"budget": -5}, "positive number"), ({"budget": "lots"}, "positive number"),
        ({"budget": True}, "positive number"), ({"budget": float("nan")}, "positive number"), ({"budget": 1e12}, "positive number"),
        ({"notes": 5}, "notes must be text"), ({"template": "camping"}, "unknown packing template"),
        ({"template": [1]}, "template must be a name or a list")])
    def test_rejected_and_nothing_stored(self, planner, kw, msg):
        out = planner.dispatch_tool("add_trip", {"name": "x", "start": "2026-10-20", "end": "2026-10-22", **kw})
        assert out.startswith("Trip not added: ") and msg in out, out
        assert rows() == []

    def test_duplicate_name_and_start(self, planner):
        trip(planner)
        assert "already a trip called 'lisbon' starting on 2026-10-20" in planner.dispatch_tool(
            "add_trip", {"name": "lisbon", "start": "2026-10-20"})
        trip(planner, start="2026-12-01", end="2026-12-03")   # same name, another time: fine
        assert len(rows()) == 2

    def test_limit(self, planner, monkeypatch):
        import trips
        monkeypatch.setattr(trips, "MAX_TRIPS", 1)
        trip(planner)
        assert "already have 1 trips" in planner.dispatch_tool("add_trip", {"name": "b", "start": "2026-11-01"})

    def test_templates(self, planner):
        import trips
        trip(planner, template=["basic", "BEACH"])
        assert texts() == trips.TEMPLATES["basic"] + trips.TEMPLATES["beach"]
        assert {i["category"] for i in rows()[0]["packing"]} == {"basic", "beach"}
        assert all(i["done"] is False and len(i["id"]) == 8 for i in rows()[0]["packing"])

    def test_overlapping_templates_do_not_duplicate(self, planner):
        trip(planner, template="city, flight")
        assert len(texts()) == len(set(t.lower() for t in texts())) and texts().count("power bank") == 1

    def test_every_template_is_usable(self, planner):
        import trips
        for name, items in trips.TEMPLATES.items():
            assert items and len(items) == len(set(items)) and all(len(i) <= trips.MAX_ITEM for i in items), name


class TestPacking:
    def test_add_items_and_templates(self, planner):
        trip(planner)
        out = planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": "sunhat, camera\n charger ", "template": "documents"})
        assert out == "Added 7 item(s) to the packing list of Lisbon (0/7 packed)."
        assert texts()[:3] == ["sunhat", "camera", "charger"]

    def test_duplicates_are_skipped_case_insensitively(self, planner):
        trip(planner)
        planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": ["Camera"]})
        out = planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": ["camera", "tripod", "CAMERA"]})
        assert out == "Added 1 item(s) to the packing list of Lisbon (0/2 packed). Already on the list: camera, CAMERA."
        assert texts() == ["Camera", "tripod"]

    @pytest.mark.parametrize("kw,msg", [({}, "say what to pack, or give a template"), ({"items": ""}, "say what to pack"),
                                        ({"items": [""]}, "needs some text"), ({"items": [5]}, "needs some text"),
                                        ({"items": 5}, "say what to pack"), ({"items": ["x" * 81]}, "at most 80"),
                                        ({"items": ["a"] * 61}, "at most 60 items at a time"), ({"template": "nope"}, "unknown packing template")])
    def test_rejected(self, planner, kw, msg):
        trip(planner)
        assert msg in planner.dispatch_tool("add_packing_items", {"trip": "lisbon", **kw}) and texts() == []

    def test_total_limit_adds_nothing(self, planner, monkeypatch):
        import trips
        monkeypatch.setattr(trips, "MAX_PACKING", 3)
        trip(planner)
        planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": ["a", "b"]})
        out = planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": ["c", "d"]})
        assert "at most 3 items" in out and texts() == ["a", "b"]

    def test_pack_and_unpack(self, planner):
        trip(planner)
        planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": "passport, camera, charger"})
        out = planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": ["pass", "camera"]})
        assert out == "Packed 2 item(s): passport, camera. Lisbon: 2/3 packed."
        assert [i["done"] for i in rows()[0]["packing"]] == [True, True, False]
        out = planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": "camera", "packed": False})
        assert out == "Unpacked 1 item(s): camera. Lisbon: 1/3 packed."

    def test_pack_by_id_and_all(self, planner):
        trip(planner)
        planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": "a, b"})
        pid = rows()[0]["packing"][1]["id"]
        planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": [pid.upper()]})
        assert [i["done"] for i in rows()[0]["packing"]] == [False, True]
        assert planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": ["all"]}).endswith("Lisbon: 2/2 packed.")

    def test_pack_is_all_or_nothing(self, planner):
        trip(planner)
        planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": "phone charger, laptop charger, hat"})
        out = planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": ["hat", "charger"]})
        assert out.startswith("Nothing changed: 'charger' matches 2 items") and not any(i["done"] for i in rows()[0]["packing"])
        out = planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": ["hat", "umbrella"]})
        assert "no packing item matches 'umbrella'" in out and not any(i["done"] for i in rows()[0]["packing"])

    def test_exact_text_beats_substring(self, planner):
        trip(planner)
        planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": "shoes, running shoes"})
        planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": ["shoes"]})
        assert [i["done"] for i in rows()[0]["packing"]] == [True, False]

    @pytest.mark.parametrize("kw,msg", [({"items": []}, "say which items"), ({"items": ["x"], "packed": "yes"}, "packed must be true or false"),
                                        ({"items": ["all"]}, "no packing items yet")])
    def test_pack_rejected(self, planner, kw, msg):
        trip(planner)
        assert msg in planner.dispatch_tool("pack_items", {"trip": "lisbon", **kw})

    def test_remove(self, planner):
        trip(planner)
        planner.dispatch_tool("add_packing_items", {"trip": "lisbon", "items": "a, b, c"})
        assert planner.dispatch_tool("remove_packing_items", {"trip": "lisbon", "items": ["a", "c"]}) == "Removed 2 item(s) from the packing list of Lisbon."
        assert texts() == ["b"]
        assert "no packing item matches" in planner.dispatch_tool("remove_packing_items", {"trip": "lisbon", "items": ["b", "z"]}) and texts() == ["b"]
        planner.dispatch_tool("remove_packing_items", {"trip": "lisbon", "items": "all"})
        assert texts() == []
        assert "say which items to remove" in planner.dispatch_tool("remove_packing_items", {"trip": "lisbon", "items": []})


class TestItinerary:
    def test_add_sorted_and_remove(self, planner):
        trip(planner)
        planner.dispatch_tool("add_itinerary_item", {"trip": "lisbon", "text": "Dinner", "date": "2026-10-20", "time": "7pm"})
        out = planner.dispatch_tool("add_itinerary_item", {"trip": "lisbon", "text": "Flight TP123", "date": "2026-10-20", "time": "8:15"})
        assert out.startswith("Added to Lisbon: Tue 2026-10-20 08:15 Flight TP123 [id=")
        planner.dispatch_tool("add_itinerary_item", {"trip": "lisbon", "text": "Museum", "date": "2026-10-20"})
        planner.dispatch_tool("add_itinerary_item", {"trip": "lisbon", "text": "Beach", "date": "2026-10-19"[:8] + "21"})
        detail = planner.dispatch_tool("get_trip", {"trip": "lisbon"}).split("Itinerary:\n")[1].split("\n")
        assert [l.strip().split(" [id=")[0] for l in detail] == [
            "Tue 2026-10-20 08:15 Flight TP123", "Tue 2026-10-20 19:00 Dinner", "Tue 2026-10-20 Museum", "Wed 2026-10-21 Beach"]
        assert planner.dispatch_tool("remove_itinerary_item", {"trip": "lisbon", "item": "museum"}) == "Removed from Lisbon: 2026-10-20 Museum."
        assert len(rows()[0]["itinerary"]) == 3

    @pytest.mark.parametrize("kw,msg", [({"date": "2026-10-19"}, "outside the trip (2026-10-20 to 2026-10-24)"),
                                        ({"date": "2026-10-25"}, "outside the trip"), ({"date": None}, "needs a itinerary date"),
                                        ({"text": ""}, "needs a itinerary text"), ({"text": "t" * 121}, "at most 120"),
                                        ({"time": "late"}, "time must be a time"), ({"date": "never"}, "couldn't understand")])
    def test_rejected(self, planner, kw, msg):
        trip(planner)
        out = planner.dispatch_tool("add_itinerary_item", {"trip": "lisbon", "text": "x", "date": "2026-10-21", **kw})
        assert out.startswith("Itinerary item not added: ") and msg in out and rows()[0]["itinerary"] == []

    def test_edge_days_allowed_and_limit(self, planner, monkeypatch):
        import trips
        trip(planner)
        for d in ("2026-10-20", "2026-10-24"):
            assert planner.dispatch_tool("add_itinerary_item", {"trip": "lisbon", "text": "x", "date": d}).startswith("Added")
        monkeypatch.setattr(trips, "MAX_ITINERARY", 2)
        assert "at most 2 itinerary items" in planner.dispatch_tool("add_itinerary_item", {"trip": "lisbon", "text": "y", "date": "2026-10-21"})

    def test_remove_unknown(self, planner):
        trip(planner)
        assert "no itinerary item matches" in planner.dispatch_tool("remove_itinerary_item", {"trip": "lisbon", "item": "zzz"})


class TestUpdateDelete:
    def test_update_fields(self, planner):
        trip(planner)
        out = planner.dispatch_tool("update_trip", {"trip": "lisbon", "fields": {"name": "Lisboa", "destination": "PT", "budget": 900, "notes": "n",
                                                                                 "start": "2026-10-21", "end": "2026-10-25"}})
        assert out.startswith("Trip updated: Lisboa (PT): 2026-10-21 to 2026-10-25 (5 days)")
        assert rows()[0]["budget"] == 900.0
        planner.dispatch_tool("update_trip", {"trip": "lisboa", "fields": {"budget": ""}})
        assert rows()[0]["budget"] is None

    def test_update_is_all_or_nothing(self, planner):
        trip(planner)
        out = planner.dispatch_tool("update_trip", {"trip": "lisbon", "fields": {"name": "New", "budget": -1}})
        assert "positive number" in out and rows()[0]["name"] == "Lisbon"

    @pytest.mark.parametrize("fields,msg", [({}, "nothing to change"), ({"color": "x"}, "cannot change color"),
                                            ({"start": "2026-10-30"}, "end date cannot be before"), ({"end": "2027-06-01"}, "at most 120 days")])
    def test_update_rejected(self, planner, fields, msg):
        trip(planner)
        assert msg in planner.dispatch_tool("update_trip", {"trip": "lisbon", "fields": fields})

    def test_dates_cannot_leave_itinerary_items_outside(self, planner):
        trip(planner)
        planner.dispatch_tool("add_itinerary_item", {"trip": "lisbon", "text": "x", "date": "2026-10-24"})
        out = planner.dispatch_tool("update_trip", {"trip": "lisbon", "fields": {"end": "2026-10-22"}})
        assert "1 itinerary item(s) would fall outside 2026-10-20 to 2026-10-22" in out and rows()[0]["end"] == "2026-10-24"

    def test_rename_collision(self, planner):
        trip(planner); trip(planner, "Rome")
        assert "already a trip called 'ROME' starting on 2026-10-20" in planner.dispatch_tool("update_trip", {"trip": "lisbon", "fields": {"name": "ROME"}})

    def test_delete(self, planner):
        trip(planner, template="basic")
        assert planner.dispatch_tool("delete_trip", {"trip": "lisbon"}) == (
            "Deleted trip Lisbon with its packing list and itinerary. This can't be undone.")
        assert rows() == []

    def test_resolve_by_destination_and_ambiguity(self, planner):
        trip(planner, "City break", destination="Porto"); trip(planner, "City trip", start="2026-12-01", end="2026-12-02")
        assert planner.dispatch_tool("get_trip", {"trip": "porto"}).startswith("City break (Porto)")
        assert "matches 2 trips" in planner.dispatch_tool("get_trip", {"trip": "city"})
        assert "no trip matches 'zzz'" in planner.dispatch_tool("get_trip", {"trip": "zzz"})
        assert "say which trip" in planner.dispatch_tool("get_trip", {"trip": " "})


class TestViews:
    def test_list_order_and_phases(self, planner):
        trip(planner, "Past", "2026-10-01", "2026-10-05"); trip(planner, "Soon", "2026-10-20", "2026-10-22")
        trip(planner, "Now", "2026-10-12", "2026-10-15"); trip(planner, "Later", "2026-12-01", "2026-12-03")
        out = planner.dispatch_tool("get_trips", {}).split("\n")
        assert out[0] == "3 trips:"
        assert [l.split(":")[0].lstrip("- ") for l in out[1:]] == ["Now", "Soon", "Later"]
        assert "day 2 of 4" in out[1] and "in 7 days" in out[2]
        out = planner.dispatch_tool("get_trips", {"include_past": True}).split("\n")
        assert out[0] == "4 trips:" and "ended 8 days ago" in out[-1] and "Past" in out[-1]

    def test_include_past_must_be_true(self, planner):
        trip(planner, "Past", "2026-10-01", "2026-10-05")
        assert planner.dispatch_tool("get_trips", {"include_past": "yes"}) == "No trips yet. Add one with add_trip."
        assert planner.dispatch_tool("get_trips", {"include_past": True}).startswith("1 trip:")

    @pytest.mark.parametrize("today,text", [(datetime(2026, 10, 19, 9), "starts tomorrow"), (datetime(2026, 10, 20, 9), "day 1 of 5"),
                                            (datetime(2026, 10, 24, 9), "day 5 of 5"), (datetime(2026, 10, 25, 9), "ended yesterday"),
                                            (datetime(2026, 10, 26, 9), "ended 2 days ago")])
    def test_phase_wording(self, planner, today, text):
        import trips
        trip(planner)
        planner.set_now(today)
        line = trips.format_trip_line(rows()[0])
        assert text in line

    def test_detail(self, planner):
        trip(planner, budget=500, notes="Bring cash", template="documents")
        planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": ["passport"]})
        out = planner.dispatch_tool("get_trip", {"trip": "lisbon"}).split("\n")
        assert out[1] == "Budget: 500.00 (100.00 per day)" and out[2] == "Notes: Bring cash" and out[3] == "Packing: 1 of 4 packed"
        assert out[4].startswith("  to pack: tickets and bookings [id=") and out[5] == "  packed: passport or ID"

    def test_detail_without_packing(self, planner):
        trip(planner)
        assert "Packing: nothing yet" in planner.dispatch_tool("get_trip", {"trip": "lisbon"})

    def test_empty(self, planner):
        assert planner.dispatch_tool("get_trips", {}) == "No trips yet. Add one with add_trip."

    def test_damaged_rows(self, planner):
        import storage
        storage.save_trips(["x", None, {"id": "a", "name": "odd", "start": "bad", "end": "bad"},
                            {"id": "b", "name": "odd2", "start": "2026-10-20", "end": "2026-10-21", "packing": "nope",
                             "itinerary": [None, {"date": "x", "text": "t"}, {"date": "2026-10-20", "text": "ok"}]}])
        assert planner.dispatch_tool("get_trips", {"include_past": True}).startswith("1 trip:")
        assert "ok" in planner.dispatch_tool("get_trip", {"trip": "odd2"}) and "dates unreadable" in planner.dispatch_tool("get_trip", {"trip": "odd"})
        import trips
        assert trips.nudges() == [] and trips.agenda_lines() == ["odd2 starts in 7 days"]


class TestNudgesAndAgenda:
    def test_nudge_when_leaving_soon_with_things_left(self, planner):
        import trips
        trip(planner, start="2026-10-15", end="2026-10-17", template="basic")
        assert trips.nudges() == ["Lisbon starts in 2 days and 7 of 7 packing items are not packed yet."]
        planner.dispatch_tool("pack_items", {"trip": "lisbon", "items": ["all"]})
        assert trips.nudges() == []

    @pytest.mark.parametrize("start,expected", [("2026-10-13", "today"), ("2026-10-14", "tomorrow"), ("2026-10-16", "in 3 days")])
    def test_nudge_wording(self, planner, start, expected):
        import trips
        trip(planner, start=start, end="2026-10-20", template="city")
        assert f"starts {expected} and" in trips.nudges()[0]

    def test_no_nudge_for_far_away_empty_or_ongoing_trips(self, planner):
        import trips
        trip(planner, "Far", "2026-10-20", "2026-10-21", template="city")
        trip(planner, "Empty", "2026-10-14", "2026-10-15")
        trip(planner, "Ongoing", "2026-10-12", "2026-10-15", template="city")
        assert trips.nudges() == []

    def test_agenda_for_upcoming_and_ongoing(self, planner):
        trip(planner, "Soon", "2026-10-15", "2026-10-17", template="documents")
        trip(planner, "Now", "2026-10-12", "2026-10-15")
        planner.dispatch_tool("add_itinerary_item", {"trip": "now", "text": "Museum", "date": "2026-10-13", "time": "10:00"})
        planner.dispatch_tool("add_itinerary_item", {"trip": "now", "text": "Dinner", "date": "2026-10-13"})
        planner.dispatch_tool("add_itinerary_item", {"trip": "now", "text": "Tomorrow", "date": "2026-10-14"})
        out = planner.dispatch_tool("get_today_agenda", {})
        assert "Trips:\n  Now: day 2 of 4 - 10:00 Museum; Dinner\n  Soon starts in 2 days, 4 of 4 items still to pack" in out

    def test_far_trips_are_not_in_the_agenda(self, planner):
        import trips
        trip(planner, "Far", "2026-10-30", "2026-11-02")
        assert trips.agenda_lines() == []
