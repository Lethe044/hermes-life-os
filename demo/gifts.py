"""
Hermes Life OS - Gift Ideas
=============================
Ideas for presents, kept per person: write them down when you think of them,
mark one bought and later given. If the person is in your people list, Hermes
knows their birthday: the gift list shows the birthdays coming up with no gift
bought yet, and a birthday within a week with saved ideas but nothing bought
is nudged and shown in the agenda.

Stored in gifts.json as {"id", "person", "idea", "price", "occasion",
"status", "notes", "created"} dicts; `status` is idea, bought or given and
`price` a number or null. No network call is made by this module.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

MAX_GIFTS = 500
MAX_PERSON = 60
MAX_IDEA = 100
MAX_OCCASION = 40
MAX_NOTES = 160
MAX_PRICE = 10_000_000
STATUSES = ("idea", "bought", "given")
BIRTHDAY_DAYS = 7
LOOKAHEAD_DAYS = 30


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_gifts(), lambda r: _storage().save_gifts(r))


def _status(value: Any, default: str = "idea") -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    key = str(value).strip().lower()
    key = {"ideas": "idea", "purchased": "bought", "buy": "bought", "gave": "given", "gifted": "given"}.get(key, key)
    if key not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}.")
    return key


def _price(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > MAX_PRICE:
        raise ValueError(f"the price must be a number from 0 to {MAX_PRICE:,}.")
    return round(float(value), 2)


def _person(value: Any) -> str:
    """The name as written, or as spelled in your people list when it matches one."""
    name = kit.clean_text(value, "person", MAX_PERSON)
    try:
        for p in kit.only_dicts(_storage().load_people()):
            if str(p.get("name", "")).strip().lower() == name.lower():
                return str(p["name"]).strip()
    except Exception:  # noqa: BLE001 - an unreadable people list never blocks a gift idea
        pass
    return name


def _money(x: float) -> str:
    return f"{x:,.0f}" if x == int(x) else f"{x:,.2f}"


# ------------------------------------------------------------------ operations

def add_gift(person: Any, idea: Any, price: Any = None, occasion: Any = None, notes: Any = None,
             status: Any = None) -> Dict[str, Any]:
    name = _person(person)
    text = kit.clean_text(idea, "gift idea", MAX_IDEA)
    rows = _load()
    if len(rows) >= MAX_GIFTS:
        raise ValueError(f"you already have {MAX_GIFTS} gift entries.")
    same = [r for r in kit.only_dicts(rows)
            if str(r.get("person", "")).lower() == name.lower() and str(r.get("idea", "")).lower() == text.lower()]
    if same:
        raise ValueError(f"'{same[0].get('idea')}' is already on {same[0].get('person')}'s list.")
    item = {"id": kit.new_id(), "person": name, "idea": text, "price": _price(price),
            "occasion": kit.clean_text(occasion, "occasion", MAX_OCCASION, required=False),
            "status": _status(status), "notes": kit.clean_text(notes, "notes", MAX_NOTES, required=False),
            "created": clock.today_str()}
    rows.append(item)
    _storage().save_gifts(rows)
    return item


def update_gift(ref: Any, fields: Any) -> Dict[str, Any]:
    kit.check_fields(fields, ("person", "idea", "price", "occasion", "status", "notes"))
    rows = _load()
    item = kit.resolve(rows, ref, "gift idea", "idea", "get_gift_ideas")
    changes: Dict[str, Any] = {}
    if "person" in fields:
        changes["person"] = _person(fields["person"])
    if "idea" in fields:
        changes["idea"] = kit.clean_text(fields["idea"], "gift idea", MAX_IDEA)
    if "price" in fields:
        changes["price"] = _price(fields["price"])
    if "occasion" in fields:
        changes["occasion"] = kit.clean_text(fields["occasion"], "occasion", MAX_OCCASION, required=False)
    if "status" in fields:
        changes["status"] = _status(fields["status"])
    if "notes" in fields:
        changes["notes"] = kit.clean_text(fields["notes"], "notes", MAX_NOTES, required=False)
    item.update(changes)
    _storage().save_gifts(rows)
    return item


def delete_gift(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "gift idea", "idea", "get_gift_ideas")
    _storage().save_gifts([r for r in rows if r is not item])
    return item


def listing(person: Any = None, status: Any = None) -> List[Dict[str, Any]]:
    rows = kit.only_dicts(_load())
    if person not in (None, ""):
        key = kit.clean_text(person, "person", MAX_PERSON).lower()
        rows = [r for r in rows if key in str(r.get("person", "")).lower()]
    if status not in (None, ""):
        want = _status(status)
        rows = [r for r in rows if r.get("status") == want]
    return sorted(rows, key=lambda r: (str(r.get("person", "")).lower(), STATUSES.index(r["status"]) if r.get("status") in STATUSES else 9,
                                       str(r.get("idea", "")).lower()))


def birthdays_without_gift(days: int = LOOKAHEAD_DAYS, only_with_ideas: bool = False) -> List[Dict[str, Any]]:
    """[{"person", "in_days", "ideas"}] for birthdays within `days` where no
    gift is bought or given yet. `only_with_ideas` keeps those with saved ideas."""
    import people
    gifts = kit.only_dicts(_load())
    out = []
    for b in people.upcoming_birthdays(days):
        name = str(b["person"].get("name", "")).strip()
        mine = [g for g in gifts if str(g.get("person", "")).lower() == name.lower()]
        if any(g.get("status") in ("bought", "given") for g in mine):
            continue
        if only_with_ideas and not mine:
            continue
        out.append({"person": name, "in_days": b["in_days"], "ideas": len(mine)})
    return out


def _safe_birthdays(days: int, only_with_ideas: bool) -> List[Dict[str, Any]]:
    try:
        return birthdays_without_gift(days, only_with_ideas)
    except Exception:  # noqa: BLE001
        return []


def nudges(max_items: int = 1) -> List[str]:
    return [f"{b['person']}'s birthday is {kit.when_text(b['in_days'])} and no gift is bought yet "
            f"({kit.plural(b['ideas'], 'idea')} saved)." for b in _safe_birthdays(BIRTHDAY_DAYS, True)[:max_items]]


def agenda_lines() -> List[str]:
    return [f"{b['person']} ({kit.when_text(b['in_days'])}): {kit.plural(b['ideas'], 'idea')} saved, none bought"
            for b in _safe_birthdays(BIRTHDAY_DAYS, True)]


# ------------------------------------------------------------------ formatting

def format_gift(g: Dict[str, Any]) -> str:
    price = f" - {_money(g['price'])}" if isinstance(g.get("price"), (int, float)) and not isinstance(g.get("price"), bool) else ""
    occ = f" for {g['occasion']}" if g.get("occasion") else ""
    return f"[{g.get('status', 'idea')}] {g.get('idea', '?')}{price}{occ} [id={g.get('id', '?')}]"


def format_all(rows: List[Dict[str, Any]], filtered: bool = False) -> str:
    soon = [] if filtered else _safe_birthdays(LOOKAHEAD_DAYS, False)
    if not rows:
        return "No gift ideas yet. Add one with add_gift_idea, for example 'a book for Ayse'." if not filtered \
            else "No gift ideas match."
    lines = [f"{len(rows)} gift {'entry' if len(rows) == 1 else 'entries'}:"]
    current = None
    for g in rows:
        if g.get("person") != current:
            current = g.get("person")
            mine = [x for x in rows if x.get("person") == current]
            spent = sum(x["price"] for x in mine if x.get("status") in ("bought", "given")
                        and isinstance(x.get("price"), (int, float)) and not isinstance(x.get("price"), bool))
            lines.append(f"{current}" + (f" (bought or given: {_money(spent)})" if spent else "") + ":")
        lines.append(f"  - {format_gift(g)}")
    if soon:
        lines.append("Birthdays in the next 30 days with no gift bought: "
                     + "; ".join(f"{b['person']} ({kit.when_text(b['in_days'])})" for b in soon[:5]))
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_gift_idea":
            g = add_gift(inp.get("person"), inp.get("idea"), inp.get("price"), inp.get("occasion"), inp.get("notes"),
                         inp.get("status"))
            return f"Gift idea added for {g['person']}: {format_gift(g)}"
        if name == "get_gift_ideas":
            rows = listing(inp.get("person"), inp.get("status"))
            return format_all(rows, bool(inp.get("person") or inp.get("status")))
        if name == "update_gift_idea":
            g = update_gift(inp.get("gift"), inp.get("fields"))
            return f"Gift idea updated for {g['person']}: {format_gift(g)}"
        if name == "delete_gift_idea":
            g = delete_gift(inp.get("gift"))
            return f"Deleted the gift idea '{g['idea']}' for {g['person']}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_gift_idea": "Gift idea not added", "get_gift_ideas": "Cannot show gift ideas"}.get(
            name, "Gift idea not changed")
        return f"{verb}: {e}"
    return f"Unknown gift tool: {name}"
