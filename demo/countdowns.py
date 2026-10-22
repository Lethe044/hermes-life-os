"""
Hermes Life OS - Countdowns
=============================
Days until something ("holiday", "exam", "wedding") and days since something
("quit smoking"). A countdown is a name and a date; a yearly one (an
anniversary) always points at its next occurrence and counts the years.

Stored in countdowns.json as {"id", "name", "date", "repeat", "notes",
"created"} dicts; `date` is "YYYY-MM-DD" (past dates are fine) and `repeat` is
None or "yearly" (Feb 29 falls on Mar 1 in other years). No network call is
made by this module.
"""

from __future__ import annotations

import uuid
from datetime import date as _date
from typing import Any, Dict, List, Optional

import clock

MAX_ITEMS = 300
MAX_NAME = 60
MAX_NOTE = 160
NUDGE_DAYS = 2
AGENDA_DAYS = 7


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def _clean_name(value: Any) -> str:
    if not isinstance(value, str) or not " ".join(value.split()):
        raise ValueError("the countdown needs a name.")
    name = " ".join(value.split())
    if len(name) > MAX_NAME:
        raise ValueError(f"the name can be at most {MAX_NAME} characters.")
    return name


def _parse_repeat(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    key = str(value).strip().lower()
    if key in ("yearly", "annual", "annually", "every year", "year"):
        return "yearly"
    if key in ("none", "no", "never", "once"):
        return None
    raise ValueError("repeat must be 'yearly' or empty.")


def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_countdowns()
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
        _storage().save_countdowns(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def _resolve(rows: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which countdown (its id or some words from its name).")
    key = ref.strip().lower()
    pool = _rows(rows)
    for r in pool:
        if str(r.get("id", "")).lower() == key or str(r.get("name", "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no countdown matches '{ref.strip()}'. Use get_countdowns to see them.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} countdowns ({'; '.join(r['name'] for r in hits[:5])}). "
                     f"Use the full name or the id.")


def occurrence(item: Dict[str, Any], today: Optional[_date] = None) -> Optional[Dict[str, Any]]:
    """{"date", "in_days", "years"}: the date to count to or from. A one-off is
    its own date (in_days negative when past); a yearly one is its next
    occurrence on or after today, with `years` since the original date.
    None when the date cannot be read."""
    today = today or clock.today()
    try:
        original = clock.parse_day(item.get("date"))
    except ValueError:
        return None
    if item.get("repeat") != "yearly":
        return {"date": original.isoformat(), "in_days": (original - today).days, "years": None}
    for y in (today.year, today.year + 1):
        try:
            when = _date(y, original.month, original.day)
        except ValueError:
            when = _date(y, 3, 1)
        if when >= today:
            return {"date": when.isoformat(), "in_days": (when - today).days, "years": y - original.year}
    return None


# ------------------------------------------------------------------ operations

def add_countdown(name: Any, date: Any, repeat: Any = None, notes: Any = None) -> Dict[str, Any]:
    clean = _clean_name(name)
    day = clock.parse_day(date).isoformat()
    rep = _parse_repeat(repeat)
    rows = _load()
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"you already have {MAX_ITEMS} countdowns.")
    if any(str(r.get("name", "")).lower() == clean.lower() for r in _rows(rows)):
        raise ValueError(f"there is already a countdown called '{clean}'.")
    item = {"id": new_id(), "name": clean, "date": day, "repeat": rep,
            "notes": str(notes).strip()[:MAX_NOTE] if isinstance(notes, str) else "", "created": clock.today_str()}
    rows.append(item)
    _storage().save_countdowns(rows)
    return item


def update_countdown(ref: Any, fields: Any) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields (name, date, repeat, notes).")
    unknown = [k for k in fields if k not in ("name", "date", "repeat", "notes")]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change name, date, repeat and notes.")
    rows = _load()
    item = _resolve(rows, ref)
    changes: Dict[str, Any] = {}
    if "name" in fields:
        n = _clean_name(fields["name"])
        if any(r is not item and str(r.get("name", "")).lower() == n.lower() for r in _rows(rows)):
            raise ValueError(f"there is already a countdown called '{n}'.")
        changes["name"] = n
    if "date" in fields:
        changes["date"] = clock.parse_day(fields["date"]).isoformat()
    if "repeat" in fields:
        changes["repeat"] = _parse_repeat(fields["repeat"])
    if "notes" in fields:
        if not isinstance(fields["notes"], str):
            raise ValueError("notes must be text.")
        changes["notes"] = fields["notes"].strip()[:MAX_NOTE]
    item.update(changes)
    _storage().save_countdowns(rows)
    return item


def delete_countdown(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = _resolve(rows, ref)
    _storage().save_countdowns([r for r in rows if r is not item])
    return item


def listing(include_past: bool = True) -> List[Dict[str, Any]]:
    """[{"item", **occurrence}] upcoming first (soonest first), then past ones
    (most recent first)."""
    out = []
    for r in _rows(_load()):
        occ = occurrence(r)
        if occ is None:
            continue
        if occ["in_days"] < 0 and not include_past:
            continue
        out.append({"item": r, **occ})
    upcoming = sorted((x for x in out if x["in_days"] >= 0), key=lambda x: (x["in_days"], x["item"]["name"].lower()))
    past = sorted((x for x in out if x["in_days"] < 0), key=lambda x: (-x["in_days"], x["item"]["name"].lower()))
    return upcoming + past


def within(days: int) -> List[Dict[str, Any]]:
    return [x for x in listing(False) if x["in_days"] <= days]


def nudges(max_items: int = 1) -> List[str]:
    return [f"{x['item']['name']} is {_when(x)}." for x in within(NUDGE_DAYS)[:max_items]]


# ------------------------------------------------------------------ formatting

def _when(x: Dict[str, Any]) -> str:
    d = x["in_days"]
    if d == 0:
        return "today"
    if d == 1:
        return "tomorrow"
    if d > 1:
        return f"in {d} days"
    return "yesterday" if d == -1 else f"{-d} days ago"


def format_countdown(x: Dict[str, Any]) -> str:
    item = x["item"]
    day = clock.parse_day(x["date"]).strftime("%a")
    line = f"{item['name']}: {_when(x)} ({day} {x['date']})"
    if x["years"] is not None and x["years"] > 0:
        line += f", year {x['years']}"
    elif x["in_days"] < 0:
        line = f"{item['name']}: {-x['in_days']} day{'s' if x['in_days'] != -1 else ''} since {x['date']}"
    if item.get("repeat") == "yearly":
        line += ", yearly"
    return f"{line} [id={item.get('id', '?')}]"


def format_all(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No countdowns yet. Add one with add_countdown."
    return f"{len(rows)} countdown{'s' if len(rows) != 1 else ''}:\n" + "\n".join(f"- {format_countdown(x)}" for x in rows)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_countdown":
            item = add_countdown(inp.get("name"), inp.get("date"), inp.get("repeat"), inp.get("notes"))
            return "Countdown added: " + format_countdown({"item": item, **occurrence(item)})
        if name == "get_countdowns":
            return format_all(listing(inp.get("include_past", True) is not False))
        if name == "update_countdown":
            item = update_countdown(inp.get("countdown"), inp.get("fields"))
            return "Countdown updated: " + format_countdown({"item": item, **occurrence(item)})
        if name == "delete_countdown":
            return f"Deleted countdown {delete_countdown(inp.get('countdown'))['name']}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_countdown": "Countdown not added", "get_countdowns": "Cannot show countdowns"}.get(
            name, "Countdown not changed")
        return f"{verb}: {e}"
    return f"Unknown countdown tool: {name}"
