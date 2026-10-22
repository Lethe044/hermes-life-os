"""
Hermes Life OS - Supplies
===========================
Things that run out: pills, contact lenses, pet food, coffee. Say how many you
have and how many you use per day, and Hermes works out how many are left today
and the day you run out, so a refill never catches you by surprise.

Stored in supplies.json as {"id", "name", "quantity", "per_day", "as_of",
"unit", "notes", "created"} dicts: you had `quantity` on the day `as_of` and use
`per_day` a day, so what is left on any later day is quantity - per_day * days
(never below zero). A refill adds to what is left (or sets the count) and moves
`as_of` to today. No network call is made by this module.
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock

MAX_ITEMS = 200
MAX_NAME = 60
MAX_UNIT = 20
MAX_NOTE = 160
MAX_QUANTITY = 10_000_000
LOW_DAYS = 7
AGENDA_DAYS = 3


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def fmt(value: float) -> str:
    return f"{value:g}"


def _number(value: Any, label: str, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.") from None
    if not math.isfinite(number) or number > MAX_QUANTITY:
        raise ValueError(f"{label} is not a sensible number.")
    number = round(number, 3)
    if number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{label} must be above zero." if not allow_zero else f"{label} cannot be negative.")
    return number


def _clean_name(value: Any) -> str:
    if not isinstance(value, str) or not " ".join(value.split()):
        raise ValueError("the supply needs a name.")
    name = " ".join(value.split())
    if len(name) > MAX_NAME:
        raise ValueError(f"the name can be at most {MAX_NAME} characters.")
    return name


def _clean_unit(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("unit must be text, for example pills.")
    unit = value.strip()
    if len(unit) > MAX_UNIT:
        raise ValueError(f"the unit can be at most {MAX_UNIT} characters.")
    return unit


def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_supplies()
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
        _storage().save_supplies(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def _resolve(rows: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which supply (its id or some words from its name).")
    key = ref.strip().lower()
    pool = _rows(rows)
    for r in pool:
        if str(r.get("id", "")).lower() == key or str(r.get("name", "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no supply matches '{ref.strip()}'. Use get_supplies to see them.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} supplies ({'; '.join(r['name'] for r in hits[:5])}). "
                     f"Use the full name or the id.")


# ------------------------------------------------------------------ maths

def status(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """{"left", "days_left", "runs_out"} as of today: `left` is the (rounded
    down to a tenth) amount remaining, `days_left` the whole days it lasts from
    today and `runs_out` the first day with none (None when per_day is 0).
    None when the item's numbers or date cannot be read."""
    try:
        as_of = clock.parse_day(item.get("as_of"))
        qty, per_day = item.get("quantity"), item.get("per_day")
        if not isinstance(qty, (int, float)) or not isinstance(per_day, (int, float)) or per_day < 0 or qty < 0:
            return None
    except ValueError:
        return None
    today = clock.today()
    elapsed = max(0, (today - as_of).days)
    left = max(0.0, qty - per_day * elapsed)
    left = math.floor(round(left, 6) * 10) / 10
    if per_day == 0:
        return {"left": left, "days_left": None, "runs_out": None}
    total_days = math.floor(round(qty / per_day, 6))
    runs_out = as_of + timedelta(days=total_days)
    return {"left": left, "days_left": max(0, (runs_out - today).days), "runs_out": runs_out.isoformat()}


# ------------------------------------------------------------------ operations

def add_supply(name: Any, quantity: Any, per_day: Any, unit: Any = None, as_of: Any = None,
               notes: Any = None) -> Dict[str, Any]:
    clean = _clean_name(name)
    qty = _number(quantity, "quantity", allow_zero=True)
    use = _number(per_day, "per_day")
    day = clock.resolve_entry_date(as_of)
    rows = _load()
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"you already have {MAX_ITEMS} supplies.")
    if any(str(r.get("name", "")).lower() == clean.lower() for r in _rows(rows)):
        raise ValueError(f"there is already a supply called '{clean}'.")
    item = {"id": new_id(), "name": clean, "quantity": qty, "per_day": use, "as_of": day,
            "unit": _clean_unit(unit), "notes": str(notes).strip()[:MAX_NOTE] if isinstance(notes, str) else "",
            "created": clock.today_str()}
    rows.append(item)
    _storage().save_supplies(rows)
    return item


def refill(ref: Any, quantity: Any, mode: Any = "add") -> Dict[str, Any]:
    """`mode` "add" puts `quantity` on top of what is left today; "set" says
    that `quantity` is the count today. Either way `as_of` becomes today."""
    key = str(mode or "add").strip().lower()
    if key not in ("add", "set"):
        raise ValueError("mode must be 'add' (new stock on top of what is left) or 'set' (the count today).")
    qty = _number(quantity, "quantity", allow_zero=(key == "set"))
    rows = _load()
    item = _resolve(rows, ref)
    st = status(item)
    if st is None:
        raise ValueError(f"the numbers or date of {item.get('name')} cannot be read; delete it and add it again.")
    base = st["left"] if key == "add" else 0.0
    item["quantity"] = round(base + qty, 3)
    item["as_of"] = clock.today_str()
    _storage().save_supplies(rows)
    return item


def update_supply(ref: Any, fields: Any) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields (name, per_day, unit, notes).")
    unknown = [k for k in fields if k not in ("name", "per_day", "unit", "notes")]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change name, per_day, unit and "
                         f"notes (use refill_supply for the count).")
    rows = _load()
    item = _resolve(rows, ref)
    changes: Dict[str, Any] = {}
    if "name" in fields:
        n = _clean_name(fields["name"])
        if any(r is not item and str(r.get("name", "")).lower() == n.lower() for r in _rows(rows)):
            raise ValueError(f"there is already a supply called '{n}'.")
        changes["name"] = n
    if "per_day" in fields:
        changes["per_day"] = _number(fields["per_day"], "per_day")
    if "unit" in fields:
        changes["unit"] = _clean_unit(fields["unit"])
    if "notes" in fields:
        if not isinstance(fields["notes"], str):
            raise ValueError("notes must be text.")
        changes["notes"] = fields["notes"].strip()[:MAX_NOTE]
    if "per_day" in changes:
        # the new rate applies from today: freeze what is left under the old one first
        st = status(item)
        if st is not None:
            item["quantity"] = st["left"]
            item["as_of"] = clock.today_str()
    item.update(changes)
    _storage().save_supplies(rows)
    return item


def delete_supply(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = _resolve(rows, ref)
    _storage().save_supplies([r for r in rows if r is not item])
    return item


def listing() -> List[Dict[str, Any]]:
    """[{"item", **status}] the ones that run out first at the top."""
    out = []
    for r in _rows(_load()):
        st = status(r)
        if st is not None:
            out.append({"item": r, **st})
    return sorted(out, key=lambda x: (x["days_left"] is None, x["days_left"] if x["days_left"] is not None else 0,
                                      x["item"]["name"].lower()))


def running_low(days: int = LOW_DAYS) -> List[Dict[str, Any]]:
    return [x for x in listing() if x["days_left"] is not None and x["days_left"] <= days]


def nudges(max_items: int = 1) -> List[str]:
    out = []
    for x in running_low(LOW_DAYS)[:max_items]:
        d = x["days_left"]
        name = x["item"]["name"]
        out.append(f"You have run out of {name}." if d == 0 and x["left"] <= 0 else
                   f"{name} runs out {'today' if d == 0 else 'tomorrow' if d == 1 else 'in ' + str(d) + ' days'}"
                   f" ({fmt(x['left'])} left).")
    return out


# ------------------------------------------------------------------ formatting

def format_supply(x: Dict[str, Any]) -> str:
    item = x["item"]
    unit = f" {item['unit']}" if item.get("unit") else ""
    line = f"{item['name']}: {fmt(x['left'])}{unit} left"
    if x["days_left"] is None:
        line += " (not being used)"
    elif x["left"] <= 0:
        line += ", ran out"
    else:
        line += f", {x['days_left']} day{'s' if x['days_left'] != 1 else ''} ({fmt(item['per_day'])}/day, runs out {x['runs_out']})"
    return f"{line} [id={item.get('id', '?')}]"


def format_all(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No supplies tracked yet. Add one with add_supply."
    low = sum(1 for x in rows if x["days_left"] is not None and x["days_left"] <= LOW_DAYS)
    head = f"{len(rows)} suppl{'ies' if len(rows) != 1 else 'y'}" + (f", {low} running low (a week or less)" if low else "")
    return head + ":\n" + "\n".join(f"- {format_supply(x)}" for x in rows)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_supply":
            item = add_supply(inp.get("name"), inp.get("quantity"), inp.get("per_day"), inp.get("unit"),
                              inp.get("as_of"), inp.get("notes"))
            return "Supply added: " + format_supply({"item": item, **status(item)})
        if name == "refill_supply":
            item = refill(inp.get("supply"), inp.get("quantity"), inp.get("mode", "add"))
            return "Refilled: " + format_supply({"item": item, **status(item)})
        if name == "get_supplies":
            return format_all(listing())
        if name == "update_supply":
            item = update_supply(inp.get("supply"), inp.get("fields"))
            st = status(item)
            return "Supply updated: " + (format_supply({"item": item, **st}) if st else item["name"])
        if name == "delete_supply":
            return f"Deleted supply {delete_supply(inp.get('supply'))['name']}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_supply": "Supply not added", "refill_supply": "Not refilled",
                "get_supplies": "Cannot show supplies"}.get(name, "Supply not changed")
        return f"{verb}: {e}"
    return f"Unknown supply tool: {name}"
