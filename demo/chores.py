"""
Hermes Life OS - Chores & Maintenance
=======================================
Things that come back on a schedule: watering the plants every week, changing
the air filter every three months, a car service every year. A chore has a
name and an interval ("every 2 weeks"); marking it done starts the next
interval from the day it was done, so a late chore never piles up several
due dates. Hermes shows what is overdue or due, nudges about the most overdue
one and lists chores due today in the agenda.

Stored in chores.json as {"id", "name", "every", "unit", "start", "last_done",
"notes", "created", "history"} dicts: `every` + `unit` (days, weeks or months)
is the interval, `start` is the first due date of a chore that was never done,
`last_done` is "YYYY-MM-DD" and `history` the last 60 completion days. No
network call is made by this module.
"""

from __future__ import annotations

import re
from datetime import date as _date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import clock
import plannerkit as kit

MAX_CHORES = 200
MAX_NAME = 60
MAX_NOTES = 160
MAX_HISTORY = 60
LIMITS = {"days": 365, "weeks": 52, "months": 24}
BACK_DAYS = 365
LIST_DAYS = 7
_WORDS = {"daily": (1, "days"), "weekly": (1, "weeks"), "biweekly": (2, "weeks"), "fortnightly": (2, "weeks"),
          "monthly": (1, "months"), "quarterly": (3, "months"), "yearly": (12, "months"),
          "annually": (12, "months"), "annual": (12, "months")}
_UNITS = {"d": "days", "day": "days", "days": "days", "w": "weeks", "week": "weeks", "weeks": "weeks",
          "m": "months", "month": "months", "months": "months", "y": "years", "year": "years", "years": "years"}
_PROBLEM = "say how often, for example 'weekly', 'every 2 weeks', 'every 10 days' or 'every 3 months'."


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_chores(), lambda r: _storage().save_chores(r))


def parse_every(value: Any, unit: Any = None) -> Tuple[int, str]:
    """(count, "days"|"weeks"|"months") for 'weekly', 'every 2 weeks', '10 days',
    a whole number of days, or a number plus `unit`. Raises ValueError."""
    if isinstance(value, bool) or value is None:
        raise ValueError(_PROBLEM)
    n: int
    u: str
    if isinstance(value, (int, float)):
        if value != int(value):
            raise ValueError(_PROBLEM)
        n, u = int(value), "days"
        if isinstance(unit, str) and unit.strip():
            u = _UNITS.get(unit.strip().lower(), "")
            if not u:
                raise ValueError(_PROBLEM)
    elif isinstance(value, str):
        text = " ".join(value.strip().lower().split())
        if text in _WORDS:
            n, u = _WORDS[text]
        else:
            m = re.fullmatch(r"(?:every\s+)?(\d{1,4})\s*([a-z]+)", text)
            m2 = re.fullmatch(r"every\s+([a-z]+)", text)
            if m and m.group(2) in _UNITS:
                n, u = int(m.group(1)), _UNITS[m.group(2)]
            elif m2 and m2.group(1) in _UNITS:
                n, u = 1, _UNITS[m2.group(1)]
            else:
                raise ValueError(_PROBLEM)
    else:
        raise ValueError(_PROBLEM)
    if u == "years":
        n, u = n * 12, "months"
    if n < 1 or n > LIMITS[u]:
        raise ValueError(f"the interval can be 1 to {LIMITS[u]} {u}.")
    return n, u


def every_text(item: Dict[str, Any]) -> str:
    n, u = item.get("every"), item.get("unit")
    if u == "months" and isinstance(n, int) and n % 12 == 0:
        n, u = n // 12, "years"
    if n == 1:
        return "every " + str(u)[:-1]
    return f"every {n} {u}"


def _day(value: Any, what: str, allow_future: bool = True) -> str:
    """A date from YYYY-MM-DD, today, tomorrow, yesterday, in N days or a weekday."""
    import tasks
    if isinstance(value, str) and value.strip().lower() == "yesterday":
        return (clock.today() - timedelta(days=1)).isoformat()
    try:
        got = tasks.parse_due(value)
    except ValueError:
        raise ValueError(f"I couldn't understand the {what}. Use YYYY-MM-DD, today, yesterday or in 3 days.") from None
    if got is None:
        got = clock.today_str()
    day = clock.parse_day(got)
    if not allow_future and day > clock.today():
        raise ValueError(f"the {what} cannot be in the future.")
    if day < clock.today() - timedelta(days=BACK_DAYS):
        raise ValueError(f"the {what} cannot be more than {BACK_DAYS} days back.")
    return day.isoformat()


def due_date(item: Dict[str, Any]) -> Optional[_date]:
    """The next due day: the interval after last_done, or `start` for a chore
    never done. None when the dates or interval cannot be read."""
    try:
        n, u = item.get("every"), item.get("unit")
        if isinstance(n, bool) or not isinstance(n, int) or u not in LIMITS or n < 1:
            return None
        if item.get("last_done"):
            last = clock.parse_day(item["last_done"])
            return last + timedelta(days=n * (7 if u == "weeks" else 1)) if u != "months" else clock.add_months(last, n)
        return clock.parse_day(item.get("start"))
    except (ValueError, TypeError):
        return None


def status(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    d = due_date(item)
    if d is None:
        return None
    return {"due": d.isoformat(), "in_days": (d - clock.today()).days}


# ------------------------------------------------------------------ operations

def add_chore(name: Any, every: Any, start: Any = None, notes: Any = None, unit: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(name, "chore name", MAX_NAME)
    n, u = parse_every(every, unit)
    rows = _load()
    if len(rows) >= MAX_CHORES:
        raise ValueError(f"you already have {MAX_CHORES} chores.")
    if any(str(r.get("name", "")).lower() == clean.lower() for r in kit.only_dicts(rows)):
        raise ValueError(f"there is already a chore called '{clean}'.")
    item = {"id": kit.new_id(), "name": clean, "every": n, "unit": u,
            "start": _day(start, "start date") if start not in (None, "") else clock.today_str(),
            "last_done": None, "notes": kit.clean_text(notes, "notes", MAX_NOTES, required=False),
            "created": clock.today_str(), "history": []}
    rows.append(item)
    _storage().save_chores(rows)
    return item


def complete_chore(ref: Any, on: Any = None) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "chore", "name", "get_chores")
    day = _day(on, "date", allow_future=False)
    last = item.get("last_done")
    if last and day == last:
        raise ValueError(f"'{item['name']}' is already marked done on {day}.")
    if last and day < last:
        raise ValueError(f"'{item['name']}' was already done later, on {last}. Use update_chore to correct last_done.")
    item["last_done"] = day
    hist = [h for h in item.get("history", []) if isinstance(h, str)] if isinstance(item.get("history"), list) else []
    item["history"] = (hist + [day])[-MAX_HISTORY:]
    _storage().save_chores(rows)
    return item


def update_chore(ref: Any, fields: Any) -> Dict[str, Any]:
    kit.check_fields(fields, ("name", "every", "start", "last_done", "notes"))
    rows = _load()
    item = kit.resolve(rows, ref, "chore", "name", "get_chores")
    changes: Dict[str, Any] = {}
    if "name" in fields:
        n = kit.clean_text(fields["name"], "chore name", MAX_NAME)
        if any(r is not item and str(r.get("name", "")).lower() == n.lower() for r in kit.only_dicts(rows)):
            raise ValueError(f"there is already a chore called '{n}'.")
        changes["name"] = n
    if "every" in fields:
        changes["every"], changes["unit"] = parse_every(fields["every"])
    if "start" in fields:
        changes["start"] = _day(fields["start"], "start date")
    if "last_done" in fields:
        raw = fields["last_done"]
        changes["last_done"] = None if raw in (None, "") else _day(raw, "last done date", allow_future=False)
    if "notes" in fields:
        changes["notes"] = kit.clean_text(fields["notes"], "notes", MAX_NOTES, required=False)
    item.update(changes)
    _storage().save_chores(rows)
    return item


def delete_chore(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "chore", "name", "get_chores")
    _storage().save_chores([r for r in rows if r is not item])
    return item


def listing(due_within: Optional[int] = None) -> List[Dict[str, Any]]:
    """[{"item", "due", "in_days"}] soonest due first (overdue first). With
    `due_within`, only the chores due in that many days or earlier."""
    out = []
    for r in kit.only_dicts(_load()):
        st = status(r)
        if st is None or (due_within is not None and st["in_days"] > due_within):
            continue
        out.append({"item": r, **st})
    out.sort(key=lambda x: (x["in_days"], str(x["item"].get("name", "")).lower()))
    return out


def due_now() -> List[Dict[str, Any]]:
    return listing(0)


def nudges(max_items: int = 1) -> List[str]:
    out = []
    for x in due_now()[:max_items]:
        d = x["in_days"]
        out.append(f"Chore '{x['item']['name']}' is " + ("due today." if d == 0 else f"overdue by {kit.plural(-d, 'day')}."))
    return out


def agenda_lines() -> List[str]:
    return [f"{x['item']['name']} ({'due today' if x['in_days'] == 0 else 'overdue by ' + kit.plural(-x['in_days'], 'day')})"
            for x in due_now()]


# ------------------------------------------------------------------ formatting

def format_chore(x: Dict[str, Any]) -> str:
    item, d = x["item"], x["in_days"]
    if d < 0:
        due = f"overdue by {kit.plural(-d, 'day')}"
    else:
        due = "due " + kit.when_text(d)
    if item.get("last_done"):
        tail = f"last done {item['last_done']}"
    else:
        tail = "never done"
    return f"{item['name']} ({every_text(item)}): {due} ({x['due']}), {tail} [id={item.get('id', '?')}]"


def format_all(rows: List[Dict[str, Any]], only_due: bool = False) -> str:
    if not rows:
        return (f"Nothing is due in the next {LIST_DAYS} days." if only_due
                else "No chores yet. Add one with add_chore, for example 'water the plants every week'.")
    head = f"{kit.plural(len(rows), 'chore')}" + (f" due within {LIST_DAYS} days or overdue" if only_due else "")
    return head + ":\n" + "\n".join(f"- {format_chore(x)}" for x in rows)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_chore":
            item = add_chore(inp.get("name"), inp.get("every"), inp.get("start"), inp.get("notes"), inp.get("unit"))
            return "Chore added: " + format_chore({"item": item, **status(item)})
        if name == "complete_chore":
            item = complete_chore(inp.get("chore"), inp.get("date"))
            return f"Marked '{item['name']}' done on {item['last_done']}. Next: " + format_chore({"item": item, **status(item)})
        if name == "get_chores":
            only_due = str(inp.get("filter") or "all").strip().lower() == "due"
            if str(inp.get("filter") or "all").strip().lower() not in ("all", "due"):
                raise ValueError("filter must be all or due.")
            return format_all(listing(LIST_DAYS if only_due else None), only_due)
        if name == "update_chore":
            item = update_chore(inp.get("chore"), inp.get("fields"))
            return "Chore updated: " + format_chore({"item": item, **(status(item) or {"due": "?", "in_days": 0})})
        if name == "delete_chore":
            return f"Deleted chore {delete_chore(inp.get('chore'))['name']}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_chore": "Chore not added", "get_chores": "Cannot show chores",
                "complete_chore": "Chore not completed"}.get(name, "Chore not changed")
        return f"{verb}: {e}"
    return f"Unknown chore tool: {name}"
