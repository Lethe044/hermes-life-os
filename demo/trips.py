"""
Hermes Life OS - Trips
========================
Plan a trip from the first idea to the last day: where and when, a budget, a
packing list you tick off and a day-by-day itinerary. Packing lists can start
from ready-made templates (basic, documents, flight, city, beach, hiking,
winter, business) and grow with your own items. Hermes counts down to the
departure, says how much is still unpacked, nudges when you leave soon with
things left to pack, and shows the trip in today's agenda while it lasts.

Stored in trips.json as {"id", "name", "destination", "start", "end", "budget",
"notes", "created", "packing": [{"id", "text", "category", "done"}],
"itinerary": [{"id", "date", "time", "text"}]} dicts; `start` and `end` are
"YYYY-MM-DD" (both days belong to the trip). No network call is made by this
module and nothing about a trip leaves the machine.
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import clock

MAX_TRIPS = 200
MAX_NAME = 60
MAX_DESTINATION = 60
MAX_NOTES = 300
MAX_TRIP_DAYS = 120
DATE_RANGE_DAYS = 730
MAX_PACKING = 150
MAX_PACKING_PER_CALL = 60
MAX_ITEM = 80
MAX_ITINERARY = 200
MAX_BUDGET = 100_000_000
NUDGE_DAYS = 3
AGENDA_DAYS = 7
TEMPLATES: Dict[str, List[str]] = {
    "basic": ["toothbrush", "toothpaste", "deodorant", "underwear", "socks", "phone charger", "medications"],
    "documents": ["passport or ID", "tickets and bookings", "travel insurance", "cash and cards"],
    "flight": ["boarding pass", "headphones", "neck pillow", "travel adapter", "power bank"],
    "city": ["comfortable shoes", "day bag", "umbrella", "power bank"],
    "beach": ["swimsuit", "sunscreen", "sunglasses", "beach towel", "flip-flops", "hat"],
    "hiking": ["hiking boots", "daypack", "water bottle", "rain jacket", "first aid kit", "snacks"],
    "winter": ["warm coat", "gloves", "scarf", "beanie", "thermal underwear", "lip balm"],
    "business": ["laptop", "laptop charger", "business clothes", "notebook", "business cards"],
}


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


# ------------------------------------------------------------------ parsing

def _clean(value: Any, what: str, limit: int, required: bool = True) -> str:
    if value is None or (isinstance(value, str) and not " ".join(value.split())):
        if required:
            raise ValueError(f"the trip needs a {what}.")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"the {what} must be text.")
    text = " ".join(value.split())
    if len(text) > limit:
        raise ValueError(f"the {what} can be at most {limit} characters.")
    return text


def _notes(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("notes must be text.")
    return value.strip()[:MAX_NOTES]


def _day(value: Any, what: str) -> str:
    import tasks
    day = tasks.parse_due(value)
    if not day:
        raise ValueError(f"the trip needs a {what} date.")
    if abs((clock.parse_day(day) - clock.today()).days) > DATE_RANGE_DAYS:
        raise ValueError(f"the {what} date must be within {DATE_RANGE_DAYS} days of today.")
    return day


def _check_span(first: str, last: str) -> None:
    if last < first:
        raise ValueError("the end date cannot be before the start date.")
    if (clock.parse_day(last) - clock.parse_day(first)).days + 1 > MAX_TRIP_DAYS:
        raise ValueError(f"a trip can last at most {MAX_TRIP_DAYS} days.")


def _budget(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("the budget must be a positive number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("the budget must be a positive number.") from None
    if math.isnan(number) or math.isinf(number) or not 0 < number <= MAX_BUDGET:
        raise ValueError("the budget must be a positive number.")
    return round(number, 2)


def _time(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    import timeblocks
    return timeblocks.fmt_time(timeblocks.parse_time(value, "time"))


def _templates(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [p for p in value.replace(";", ",").split(",")]
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise ValueError("template must be a name or a list of names.")
    out: List[str] = []
    for t in value:
        key = t.strip().lower()
        if not key:
            continue
        if key not in TEMPLATES:
            raise ValueError(f"unknown packing template '{t.strip()}'. Templates: {', '.join(TEMPLATES)}.")
        if key not in out:
            out.append(key)
    return out


def _item_texts(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [p for chunk in value.replace("\n", ",").split(",") for p in [chunk.strip()] if p]
    if not isinstance(value, list):
        raise ValueError("say what to pack: one item, several separated by commas, or a list.")
    out: List[str] = []
    for v in value:
        if not isinstance(v, str) or not " ".join(v.split()):
            raise ValueError("an item needs some text.")
        text = " ".join(v.split())
        if len(text) > MAX_ITEM:
            raise ValueError(f"an item can be at most {MAX_ITEM} characters.")
        out.append(text)
    return out


# ------------------------------------------------------------------ storage

def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_trips()
    if not isinstance(rows, list):
        return []
    seen = {r.get("id") for r in rows if isinstance(r, dict) and r.get("id")}
    changed = False
    for r in rows:
        if isinstance(r, dict) and not r.get("id"):
            new = new_id()
            while new in seen:
                new = new_id()
            seen.add(new)
            r["id"] = new
            changed = True
    if changed:
        _storage().save_trips(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def packing_of(trip: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = trip.get("packing")
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("text"), str)] if isinstance(items, list) else []


def _readable(day: Any) -> bool:
    try:
        clock.parse_day(day)
    except (ValueError, TypeError):
        return False
    return True


def itinerary_of(trip: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = trip.get("itinerary")
    out = [i for i in items if isinstance(i, dict) and isinstance(i.get("text"), str) and _readable(i.get("date"))] \
        if isinstance(items, list) else []
    return sorted(out, key=lambda i: (i["date"], str(i.get("time") or "99:99"), i["text"].lower()))


def _resolve(rows: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which trip (its id or some words from its name or destination).")
    key = ref.strip().lower()
    pool = _rows(rows)
    for r in pool:
        if str(r.get("id", "")).lower() == key or str(r.get("name", "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get("name", "")).lower() or key in str(r.get("destination", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no trip matches '{ref.strip()}'. Use get_trips to see them.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} trips ({'; '.join(str(r.get('name')) for r in hits[:5])}). "
                     f"Use the full name or the id.")


def _resolve_item(items: List[Dict[str, Any]], ref: Any, what: str) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"say which {what} (its id or some words from it).")
    key = ref.strip().lower()
    for i in items:
        if str(i.get("id", "")).lower() == key:
            return i
    exact = [i for i in items if str(i.get("text", "")).lower() == key]
    hits = exact or [i for i in items if key in str(i.get("text", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no {what} matches '{ref.strip()}'.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} items ({'; '.join(str(i.get('text')) for i in hits[:5])}). "
                     f"Use the id.")


def phase(trip: Dict[str, Any], today: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """{"state": "upcoming"|"ongoing"|"past", "in_days", "day", "days"} or None
    for unreadable dates. in_days counts to the start (negative once begun)."""
    today = today or clock.today()
    try:
        first, last = clock.parse_day(trip.get("start")), clock.parse_day(trip.get("end"))
    except ValueError:
        return None
    total = (last - first).days + 1
    if today < first:
        return {"state": "upcoming", "in_days": (first - today).days, "day": 0, "days": total}
    if today > last:
        return {"state": "past", "in_days": (first - today).days, "day": total, "days": total, "ended": (today - last).days}
    return {"state": "ongoing", "in_days": (first - today).days, "day": (today - first).days + 1, "days": total}


def packing_stats(trip: Dict[str, Any]) -> Tuple[int, int]:
    items = packing_of(trip)
    return sum(1 for i in items if i.get("done")), len(items)


# ------------------------------------------------------------------ operations

def add_trip(name: Any, start: Any, end: Any = None, destination: Any = None, budget: Any = None,
             notes: Any = None, template: Any = None) -> Dict[str, Any]:
    clean = _clean(name, "name", MAX_NAME)
    first = _day(start, "start")
    last = _day(end, "end") if end not in (None, "") else first
    _check_span(first, last)
    dest = _clean(destination, "destination", MAX_DESTINATION, required=False)
    money = _budget(budget)
    note = _notes(notes)
    templates = _templates(template)
    rows = _load()
    if len(rows) >= MAX_TRIPS:
        raise ValueError(f"you already have {MAX_TRIPS} trips - delete old ones first.")
    if any(str(r.get("name", "")).lower() == clean.lower() and str(r.get("start")) == first for r in _rows(rows)):
        raise ValueError(f"there is already a trip called '{clean}' starting on {first}.")
    trip = {"id": new_id(), "name": clean, "destination": dest, "start": first, "end": last, "budget": money,
            "notes": note, "created": clock.today_str(), "packing": [], "itinerary": []}
    _pack(trip, [], templates)
    rows.append(trip)
    _storage().save_trips(rows)
    return trip


def _pack(trip: Dict[str, Any], texts: List[str], templates: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Adds items (and template items) to a trip's packing list in memory.
    Returns (added rows, skipped texts already on the list)."""
    if not isinstance(trip.get("packing"), list):
        trip["packing"] = []
    have = {str(i.get("text", "")).lower() for i in packing_of(trip)}
    wanted = [(t, "general") for t in texts] + [(t, name) for name in templates for t in TEMPLATES[name]]
    added, skipped = [], []
    for text, cat in wanted:
        if text.lower() in have:
            skipped.append(text)
            continue
        have.add(text.lower())
        added.append({"id": new_id(), "text": text, "category": cat, "done": False})
    if len(trip["packing"]) + len(added) > MAX_PACKING:
        raise ValueError(f"a packing list can have at most {MAX_PACKING} items.")
    trip["packing"].extend(added)
    return added, skipped


def add_packing_items(ref: Any, items: Any = None, template: Any = None) -> Dict[str, Any]:
    texts = _item_texts(items)
    templates = _templates(template)
    if not texts and not templates:
        raise ValueError("say what to pack, or give a template (" + ", ".join(TEMPLATES) + ").")
    if len(texts) > MAX_PACKING_PER_CALL:
        raise ValueError(f"at most {MAX_PACKING_PER_CALL} items at a time.")
    rows = _load()
    trip = _resolve(rows, ref)
    added, skipped = _pack(trip, texts, templates)
    if added:
        _storage().save_trips(rows)
    return {"trip": trip, "added": added, "skipped": skipped}


def pack_items(ref: Any, items: Any, packed: Any = True) -> Dict[str, Any]:
    """Ticks (or unticks) packing items by id or words; "all" means every
    item. All or nothing: one unknown or ambiguous reference changes nothing."""
    if not isinstance(packed, bool):
        raise ValueError("packed must be true or false.")
    refs = _item_texts(items)
    if not refs:
        raise ValueError("say which items (their ids or words), or 'all'.")
    rows = _load()
    trip = _resolve(rows, ref)
    pool = packing_of(trip)
    if len(refs) == 1 and refs[0].lower() == "all":
        hit = list(pool)
        if not hit:
            raise ValueError("this trip has no packing items yet.")
    else:
        hit = []
        for r in refs:
            item = _resolve_item(pool, r, "packing item")
            if item not in hit:
                hit.append(item)
    for i in hit:
        i["done"] = packed
    _storage().save_trips(rows)
    return {"trip": trip, "items": hit, "packed": packed}


def remove_packing_items(ref: Any, items: Any) -> Dict[str, Any]:
    refs = _item_texts(items)
    if not refs:
        raise ValueError("say which items to remove (ids or words), or 'all'.")
    rows = _load()
    trip = _resolve(rows, ref)
    pool = packing_of(trip)
    if len(refs) == 1 and refs[0].lower() == "all":
        gone = list(pool)
    else:
        gone = []
        for r in refs:
            item = _resolve_item(pool, r, "packing item")
            if item not in gone:
                gone.append(item)
    ids = {id(i) for i in gone}
    trip["packing"] = [i for i in trip.get("packing", []) if id(i) not in ids]
    _storage().save_trips(rows)
    return {"trip": trip, "items": gone}


def add_itinerary_item(ref: Any, text: Any, date: Any, time: Any = None) -> Dict[str, Any]:
    clean = _clean(text, "itinerary text", 120)
    day = _day(date, "itinerary")
    when = _time(time)
    rows = _load()
    trip = _resolve(rows, ref)
    if not str(trip.get("start")) <= day <= str(trip.get("end")):
        raise ValueError(f"{day} is outside the trip ({trip.get('start')} to {trip.get('end')}).")
    if not isinstance(trip.get("itinerary"), list):
        trip["itinerary"] = []
    if len(trip["itinerary"]) >= MAX_ITINERARY:
        raise ValueError(f"a trip can have at most {MAX_ITINERARY} itinerary items.")
    item = {"id": new_id(), "date": day, "time": when, "text": clean}
    trip["itinerary"].append(item)
    _storage().save_trips(rows)
    return {"trip": trip, "item": item}


def remove_itinerary_item(ref: Any, item_ref: Any) -> Dict[str, Any]:
    rows = _load()
    trip = _resolve(rows, ref)
    item = _resolve_item(itinerary_of(trip), item_ref, "itinerary item")
    trip["itinerary"] = [i for i in trip.get("itinerary", []) if i is not item]
    _storage().save_trips(rows)
    return {"trip": trip, "item": item}


def update_trip(ref: Any, fields: Any) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields (name, destination, start, end, budget, notes).")
    unknown = [k for k in fields if k not in ("name", "destination", "start", "end", "budget", "notes")]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change name, destination, start, "
                         f"end, budget and notes.")
    rows = _load()
    trip = _resolve(rows, ref)
    changes: Dict[str, Any] = {}
    if "name" in fields:
        changes["name"] = _clean(fields["name"], "name", MAX_NAME)
    if "destination" in fields:
        changes["destination"] = _clean(fields["destination"], "destination", MAX_DESTINATION, required=False)
    if "budget" in fields:
        changes["budget"] = _budget(fields["budget"])
    if "notes" in fields:
        changes["notes"] = _notes(fields["notes"])
    if "start" in fields or "end" in fields:
        first = _day(fields["start"], "start") if "start" in fields else trip.get("start")
        last = _day(fields["end"], "end") if "end" in fields else trip.get("end")
        if not isinstance(first, str) or not isinstance(last, str):
            raise ValueError("give both start and end.")
        _check_span(first, last)
        outside = [i for i in itinerary_of(trip) if not first <= i["date"] <= last]
        if outside:
            raise ValueError(f"{len(outside)} itinerary item(s) would fall outside {first} to {last} - move or "
                             f"remove them first.")
        changes["start"], changes["end"] = first, last
    new_name = changes.get("name", trip.get("name"))
    new_start = changes.get("start", trip.get("start"))
    if any(r is not trip and str(r.get("name", "")).lower() == str(new_name).lower() and r.get("start") == new_start
           for r in _rows(rows)):
        raise ValueError(f"there is already a trip called '{new_name}' starting on {new_start}.")
    trip.update(changes)
    _storage().save_trips(rows)
    return trip


def delete_trip(ref: Any) -> Dict[str, Any]:
    rows = _load()
    trip = _resolve(rows, ref)
    _storage().save_trips([r for r in rows if r is not trip])
    return trip


def listing(include_past: bool = False) -> List[Dict[str, Any]]:
    """Trips with a readable date: ongoing and upcoming ones (soonest first),
    then, if asked, past ones (most recent first)."""
    ups, past = [], []
    for t in _rows(_load()):
        p = phase(t)
        if p is None:
            continue
        (past if p["state"] == "past" else ups).append((t, p))
    ups.sort(key=lambda tp: (tp[0].get("start"), str(tp[0].get("name", "")).lower()))
    past.sort(key=lambda tp: (str(tp[0].get("end")), str(tp[0].get("name", "")).lower()), reverse=True)
    return [t for t, _ in ups + (past if include_past else [])]


# ------------------------------------------------------------------ nudges and agenda

def nudges(max_items: int = 1) -> List[str]:
    out = []
    for t in listing(False):
        p = phase(t)
        done, total = packing_stats(t)
        if p["state"] != "past" and 0 <= p["in_days"] <= NUDGE_DAYS and done < total:
            when = "today" if p["in_days"] == 0 else ("tomorrow" if p["in_days"] == 1 else f"in {p['in_days']} days")
            out.append(f"{t['name']} starts {when} and {total - done} of {total} packing items are not packed yet.")
    return out[:max_items]


def agenda_lines() -> List[str]:
    out = []
    for t in listing(False):
        p = phase(t)
        done, total = packing_stats(t)
        if p["state"] == "ongoing":
            today = clock.today_str()
            plans = [i for i in itinerary_of(t) if i["date"] == today]
            line = f"{t['name']}: day {p['day']} of {p['days']}"
            if plans:
                line += " - " + "; ".join(f"{(i.get('time') or '').strip()} {i['text']}".strip() for i in plans[:3])
            out.append(line)
        elif p["in_days"] <= AGENDA_DAYS:
            when = "today" if p["in_days"] == 0 else ("tomorrow" if p["in_days"] == 1 else f"in {p['in_days']} days")
            line = f"{t['name']} starts {when}"
            if total:
                line += f", {total - done} of {total} items still to pack"
            out.append(line)
    return out


# ------------------------------------------------------------------ formatting

def _when(p: Dict[str, Any]) -> str:
    if p["state"] == "ongoing":
        return f"day {p['day']} of {p['days']}"
    if p["state"] == "upcoming":
        return "starts today" if p["in_days"] == 0 else ("starts tomorrow" if p["in_days"] == 1
                                                          else f"in {p['in_days']} days")
    ended = p.get("ended", 0)
    return "ended today" if ended == 0 else ("ended yesterday" if ended == 1 else f"ended {ended} days ago")


def format_trip_line(t: Dict[str, Any]) -> str:
    p = phase(t)
    dest = (f" ({t['destination']})" if t.get("destination")
            and str(t["destination"]).lower() != str(t.get("name", "")).lower() else "")
    done, total = packing_stats(t)
    pack = f", packed {done}/{total}" if total else ""
    span = f"{t.get('start')} to {t.get('end')}" if t.get("end") != t.get("start") else str(t.get("start"))
    days = f" ({p['days']} day{'s' if p['days'] != 1 else ''})" if p else ""
    return f"{t.get('name', '?')}{dest}: {span}{days}, {_when(p) if p else 'dates unreadable'}{pack} [id={t.get('id', '?')}]"


def format_trips(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No trips yet. Add one with add_trip."
    return f"{len(rows)} trip{'s' if len(rows) != 1 else ''}:\n" + "\n".join(f"- {format_trip_line(t)}" for t in rows)


def _itinerary_line(i: Dict[str, Any]) -> str:
    when = f" {i['time']}" if i.get("time") else ""
    return f"{clock.parse_day(i['date']).strftime('%a')} {i['date']}{when} {i['text']} [id={i.get('id', '?')}]"


def format_trip(t: Dict[str, Any]) -> str:
    lines = [format_trip_line(t)]
    p = phase(t)
    if isinstance(t.get("budget"), (int, float)) and p:
        lines.append(f"Budget: {t['budget']:.2f} ({t['budget'] / p['days']:.2f} per day)")
    if t.get("notes"):
        lines.append(f"Notes: {t['notes']}")
    items = packing_of(t)
    done, total = packing_stats(t)
    if items:
        lines.append(f"Packing: {done} of {total} packed")
        todo = [i for i in items if not i.get("done")]
        if todo:
            lines.append("  to pack: " + ", ".join(
                f"{i['text']} [id={i.get('id', '?')}]" for i in todo))
        if done:
            lines.append("  packed: " + ", ".join(i["text"] for i in items if i.get("done")))
    else:
        lines.append("Packing: nothing yet (add_packing_items, or a template such as beach or city).")
    plan = itinerary_of(t)
    if plan:
        lines.append("Itinerary:")
        lines += [f"  {_itinerary_line(i)}" for i in plan]
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_trip":
            t = add_trip(inp.get("name"), inp.get("start"), inp.get("end"), inp.get("destination"),
                         inp.get("budget"), inp.get("notes"), inp.get("template"))
            return "Trip added: " + format_trip_line(t)
        if name == "get_trips":
            return format_trips(listing(inp.get("include_past", False) is True))
        if name == "get_trip":
            return format_trip(_resolve(_load(), inp.get("trip")))
        if name == "update_trip":
            return "Trip updated: " + format_trip_line(update_trip(inp.get("trip"), inp.get("fields")))
        if name == "delete_trip":
            return f"Deleted trip {delete_trip(inp.get('trip')).get('name')} with its packing list and itinerary. This can't be undone."
        if name == "add_packing_items":
            res = add_packing_items(inp.get("trip"), inp.get("items"), inp.get("template"))
            done, total = packing_stats(res["trip"])
            msg = f"Added {len(res['added'])} item(s) to the packing list of {res['trip']['name']} ({done}/{total} packed)."
            if res["skipped"]:
                msg += " Already on the list: " + ", ".join(res["skipped"][:8]) + "."
            return msg
        if name == "pack_items":
            res = pack_items(inp.get("trip"), inp.get("items"), inp.get("packed", True))
            done, total = packing_stats(res["trip"])
            word = "Packed" if res["packed"] else "Unpacked"
            return (f"{word} {len(res['items'])} item(s): " + ", ".join(i["text"] for i in res["items"][:8])
                    + f". {res['trip']['name']}: {done}/{total} packed.")
        if name == "remove_packing_items":
            res = remove_packing_items(inp.get("trip"), inp.get("items"))
            return f"Removed {len(res['items'])} item(s) from the packing list of {res['trip']['name']}."
        if name == "add_itinerary_item":
            res = add_itinerary_item(inp.get("trip"), inp.get("text"), inp.get("date"), inp.get("time"))
            i = res["item"]
            return f"Added to {res['trip']['name']}: {_itinerary_line(i)}"
        if name == "remove_itinerary_item":
            res = remove_itinerary_item(inp.get("trip"), inp.get("item"))
            return f"Removed from {res['trip']['name']}: {res['item']['date']} {res['item']['text']}."
    except (ValueError, TypeError) as e:
        verb = {"add_trip": "Trip not added", "get_trips": "Cannot show trips", "get_trip": "Cannot show the trip",
                "delete_trip": "Trip not deleted", "add_packing_items": "Nothing added",
                "pack_items": "Nothing changed", "remove_packing_items": "Nothing removed",
                "add_itinerary_item": "Itinerary item not added",
                "remove_itinerary_item": "Itinerary item not removed"}.get(name, "Trip not changed")
        return f"{verb}: {e}"
    return f"Unknown trip tool: {name}"
