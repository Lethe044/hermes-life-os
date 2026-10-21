"""
Hermes Life OS - People
=========================
The relationships side of a life OS: the people you want to stay in touch
with, how often, when you last did, and whose birthday is coming up. The
social tracker records how time with people *felt*; this records who you have
not called in a while.

Stored in people.json as a list of {"id", "name", "birthday", "keep_in_touch_days",
"notes", "created", "last_contact", "history"} dicts. `birthday` is "MM-DD" or
"YYYY-MM-DD" (the year, when known, gives an age) or None. `keep_in_touch_days`
is how often you want to be in touch (None = no goal). `history` holds the last
50 {"date", "note"} contacts, newest last. Someone with a goal who has never
been contacted counts from the day they were added.

Contacts are logged here, not in the social tracker, so nothing is counted
twice; log time with someone *and* how it felt with log_social_interaction if
you want both. No network call is made by this module.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import clock


def _storage():
    """The storage module as it is right now (looked up on every call, so a
    reloaded storage - another profile, a test's temp HOME - is never missed)."""
    import storage
    return storage


MAX_NAME = 80
MAX_PEOPLE = 1000
MAX_HISTORY = 50
MAX_INTERVAL = 3650
MAX_NOTE = 300


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def _clean_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("the person needs a name.")
    name = " ".join(value.split())
    if len(name) > MAX_NAME:
        raise ValueError(f"the name can be at most {MAX_NAME} characters.")
    return name


def parse_birthday(value: Any) -> Optional[str]:
    """A birthday as "MM-DD" or "YYYY-MM-DD" (None / blank = none). 02-29 is
    allowed. Raises ValueError for anything else, including a future year."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError("birthday must be written as MM-DD or YYYY-MM-DD.")
    text = value.strip()
    try:
        if len(text.split("-")) == 3:
            d = datetime.strptime(text, "%Y-%m-%d").date()
            if d > clock.today():
                raise ValueError("future")
            return d.isoformat()
        datetime.strptime(f"2024-{text}", "%Y-%m-%d")  # 2024 is a leap year: 02-29 passes
        month, day = (int(x) for x in text.split("-"))
        return f"{month:02d}-{day:02d}"
    except ValueError:
        raise ValueError(f"'{text}' is not a valid birthday - write it as MM-DD or YYYY-MM-DD "
                         f"(not in the future).") from None


def parse_interval(value: Any) -> Optional[int]:
    """How often to be in touch, in days (None / blank / 0 = no goal)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("keep_in_touch_days must be a whole number of days.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"keep_in_touch_days must be a whole number of days, got {value!r}.") from None
    if number != int(number) or not 0 <= number <= MAX_INTERVAL:
        raise ValueError(f"keep_in_touch_days must be a whole number from 0 to {MAX_INTERVAL}.")
    return int(number) or None


# ------------------------------------------------------------------ storage

def _load() -> List[Dict[str, Any]]:
    people = _storage().load_people()
    if not isinstance(people, list):
        return []
    seen = {p.get("id") for p in people if isinstance(p, dict) and p.get("id")}
    changed = False
    for p in people:
        if isinstance(p, dict) and not p.get("id"):
            new = new_id()
            while new in seen:
                new = new_id()
            seen.add(new)
            p["id"] = new
            changed = True
    if changed:
        _storage().save_people(people)
    return people


def _rows(people: List[Any]) -> List[Dict[str, Any]]:
    return [p for p in people if isinstance(p, dict)]


def _resolve(people: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say who (their name or id).")
    key = ref.strip().lower()
    pool = _rows(people)
    exact = [p for p in pool if str(p.get("id", "")).lower() == key or str(p.get("name", "")).lower() == key]
    if len(exact) == 1:
        return exact[0]
    hits = [p for p in pool if key in str(p.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"nobody matches '{ref.strip()}'. Use list_people to see who is saved.")
    options = "; ".join(f"[id={p['id']}] {p.get('name', '')}" for p in hits[:5])
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} people ({options}). Use the id.")


# ------------------------------------------------------------------ operations

def add_person(name: Any, birthday: Any = None, keep_in_touch_days: Any = None, notes: Any = None) -> Dict[str, Any]:
    clean = _clean_name(name)
    bday = parse_birthday(birthday)
    interval = parse_interval(keep_in_touch_days)
    people = _load()
    if len(people) >= MAX_PEOPLE:
        raise ValueError(f"you already have {MAX_PEOPLE} people saved.")
    if any(str(p.get("name", "")).lower() == clean.lower() for p in _rows(people)):
        raise ValueError(f"'{clean}' is already saved. Use update_person to change them.")
    person = {"id": new_id(), "name": clean, "birthday": bday, "keep_in_touch_days": interval,
              "notes": notes.strip()[:MAX_NOTE] if isinstance(notes, str) else "",
              "created": clock.today_str(), "last_contact": None, "history": []}
    people.append(person)
    _storage().save_people(people)
    return person


def update_person(ref: Any, fields: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change - give at least one of name, birthday, keep_in_touch_days or notes.")
    allowed = {"name", "birthday", "keep_in_touch_days", "notes"}
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError(f"cannot change {', '.join(unknown)}. Editable: {', '.join(sorted(allowed))}.")
    changes: Dict[str, Any] = {}
    if "name" in fields:
        changes["name"] = _clean_name(fields["name"])
    if "birthday" in fields:
        changes["birthday"] = parse_birthday(fields["birthday"])
    if "keep_in_touch_days" in fields:
        changes["keep_in_touch_days"] = parse_interval(fields["keep_in_touch_days"])
    if "notes" in fields:
        if not isinstance(fields["notes"], str):
            raise ValueError("notes must be text.")
        changes["notes"] = fields["notes"].strip()[:MAX_NOTE]
    people = _load()
    person = _resolve(people, ref)
    new_name = changes.get("name")
    if new_name and any(p is not person and str(p.get("name", "")).lower() == new_name.lower() for p in _rows(people)):
        raise ValueError(f"'{new_name}' is already saved.")
    person.update(changes)
    _storage().save_people(people)
    return person


def delete_person(ref: Any) -> Dict[str, Any]:
    people = _load()
    person = _resolve(people, ref)
    people.remove(person)
    _storage().save_people(people)
    return person


def log_contact(ref: Any, on: Optional[str] = None, note: Any = None) -> Dict[str, Any]:
    """Records that you were in touch. `on` is a YYYY-MM-DD date (default
    today, never in the future; any past date is fine). `last_contact` only
    ever moves forward, so logging an old catch-up afterwards does not make
    someone look neglected again."""
    day = clock.today() if on in (None, "") else clock.parse_day(on)
    if day > clock.today():
        raise ValueError(f"that date is in the future (today is {clock.today_str()}).")
    people = _load()
    person = _resolve(people, ref)
    entry = {"date": day.isoformat(), "note": note.strip()[:MAX_NOTE] if isinstance(note, str) else ""}
    history = [h for h in (person.get("history") or []) if isinstance(h, dict)]
    history.append(entry)
    history.sort(key=lambda h: str(h.get("date", "")))
    person["history"] = history[-MAX_HISTORY:]
    last = person.get("last_contact")
    if not last or entry["date"] > last:
        person["last_contact"] = entry["date"]
    _storage().save_people(people)
    return person


# ------------------------------------------------------------------ reporting

def days_since_contact(person: Dict[str, Any], today: Optional[date] = None) -> Optional[int]:
    """Days since the last contact, or since the person was added if there has
    been none; None if neither date is readable."""
    today = today or clock.today()
    for key in ("last_contact", "created"):
        raw = person.get(key)
        if raw:
            try:
                return (today - clock.parse_day(raw)).days
            except ValueError:
                continue
    return None


def overdue(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """People whose goal interval has passed, most overdue first, each as
    {"person", "days_since", "interval", "over_by"}."""
    out = []
    for p in _rows(_load()):
        interval = p.get("keep_in_touch_days")
        if not isinstance(interval, int) or interval <= 0:
            continue
        since = days_since_contact(p)
        if since is not None and since > interval:
            out.append({"person": p, "days_since": since, "interval": interval, "over_by": since - interval})
    out.sort(key=lambda r: (-r["over_by"], str(r["person"].get("name", "")).lower()))
    return out[:limit] if limit else out


def next_birthday(person: Dict[str, Any], today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """The next birthday on or after today as {"date", "in_days", "turning"}
    (turning is None when the birth year is unknown); Feb 29 falls on Mar 1 in
    non-leap years. None without a readable birthday."""
    today = today or clock.today()
    raw = person.get("birthday")
    if not raw:
        return None
    try:
        parts = raw.split("-")
        if len(parts) == 3:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            year, month, day = None, int(parts[0]), int(parts[1])
        for y in (today.year, today.year + 1):
            try:
                when = date(y, month, day)
            except ValueError:
                if (month, day) != (2, 29):
                    return None
                when = date(y, 3, 1)  # Feb 29 in a non-leap year
            if when >= today:
                return {"date": when.isoformat(), "in_days": (when - today).days,
                        "turning": (y - year) if year else None}
    except (ValueError, IndexError, AttributeError):
        return None
    return None


def upcoming_birthdays(days: int = 30) -> List[Dict[str, Any]]:
    out = []
    for p in _rows(_load()):
        nb = next_birthday(p)
        if nb and nb["in_days"] <= max(0, int(days)):
            out.append({"person": p, **nb})
    out.sort(key=lambda r: (r["in_days"], str(r["person"].get("name", "")).lower()))
    return out


def nudges(max_items: int = 2) -> List[str]:
    """Short messages for proactive nudges: a birthday within 3 days first,
    then the most overdue contact."""
    out: List[str] = []
    for b in upcoming_birthdays(3)[:1]:
        when = "today" if b["in_days"] == 0 else "tomorrow" if b["in_days"] == 1 else f"in {b['in_days']} days"
        turning = f" (turning {b['turning']})" if b["turning"] else ""
        out.append(f"{b['person']['name']}'s birthday is {when}{turning}.")
    for o in overdue(1):
        out.append(f"You haven't been in touch with {o['person']['name']} for {o['days_since']} days "
                   f"(goal: every {o['interval']}).")
    return out[:max_items]


def format_person(p: Dict[str, Any], detail: bool = False) -> str:
    bits = [f"[id={p['id']}] {p.get('name', '?')}"]
    since = days_since_contact(p)
    if p.get("last_contact"):
        bits.append(f"last contact {p['last_contact']} ({since} days ago)" if since else f"last contact {p['last_contact']} (today)")
    elif since is not None:
        bits.append(f"not contacted yet (saved {since} days ago)" if since else "not contacted yet")
    if p.get("keep_in_touch_days"):
        due = since is not None and since > p["keep_in_touch_days"]
        bits.append(f"goal every {p['keep_in_touch_days']} days" + (" - OVERDUE" if due else ""))
    nb = next_birthday(p)
    if nb:
        bits.append(f"birthday {nb['date']} (in {nb['in_days']} days)" if nb["in_days"] else "birthday TODAY")
    line = " - ".join(bits)
    if detail:
        if p.get("notes"):
            line += f"\nNotes: {p['notes']}"
        hist = [h for h in (p.get("history") or []) if isinstance(h, dict)][-5:]
        if hist:
            line += "\nRecent contacts:\n" + "\n".join(
                f"  {h.get('date')}{': ' + h['note'] if h.get('note') else ''}" for h in reversed(hist))
    return line


def format_list() -> str:
    people = _rows(_load())
    if not people:
        return "Nobody saved yet. Add someone with add_person."
    people.sort(key=lambda p: str(p.get("name", "")).lower())
    return f"{len(people)} people:\n" + "\n".join(format_person(p) for p in people)


def format_due(days: int = 30) -> str:
    lines = []
    od = overdue()
    if od:
        lines.append(f"{len(od)} overdue for a catch-up:")
        for o in od[:10]:
            lines.append(f"  {o['person']['name']}: {o['days_since']} days since contact "
                         f"(goal every {o['interval']}, {o['over_by']} over)")
    bd = upcoming_birthdays(days)
    if bd:
        lines.append(f"Birthdays in the next {days} days:")
        for b in bd:
            t = f", turning {b['turning']}" if b["turning"] else ""
            lines.append(f"  {b['date']} ({'today' if b['in_days'] == 0 else 'in ' + str(b['in_days']) + ' days'}): "
                         f"{b['person']['name']}{t}")
    return "\n".join(lines) if lines else "Nobody is overdue and no birthdays are coming up."


# ------------------------------------------------------------------ tool entry point

def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_person":
            return "Saved: " + format_person(add_person(inp.get("name"), inp.get("birthday"),
                                                        inp.get("keep_in_touch_days"), inp.get("notes")))
        if name == "list_people":
            return format_list()
        if name == "get_person":
            return format_person(_resolve(_load(), inp.get("person")), detail=True)
        if name == "update_person":
            return "Updated: " + format_person(update_person(inp.get("person"), inp.get("fields")))
        if name == "delete_person":
            return f"Deleted {delete_person(inp.get('person'))['name']} (and their contact history). This can't be undone."
        if name == "log_contact":
            p = log_contact(inp.get("person"), inp.get("date"), inp.get("note"))
            when = inp.get("date") if inp.get("date") else clock.today_str()
            when = clock.parse_day(when).isoformat()
            return f"Logged contact with {p['name']} on {when}. Last contact: {p['last_contact']}."
        if name == "get_people_due":
            return format_due(int(inp.get("days", 30)))
    except (ValueError, TypeError) as e:
        verb = {"add_person": "Not saved", "get_person": "Cannot show", "list_people": "Cannot list",
                "get_people_due": "Cannot check", "log_contact": "Contact not logged"}.get(name, "Not changed")
        return f"{verb}: {e}"
    return f"Unknown people tool: {name}"
