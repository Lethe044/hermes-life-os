"""
Hermes Life OS - Waiting For
==============================
Things you handed to someone else and need back: "quote from the plumber",
"signed contract from Sam", "refund from the airline". Each item has a
follow-up date (a week from now by default). Items due for a follow-up show in
the agenda and the nudges; chasing one pushes the date out, and resolving it
closes the item.

Stored in waiting.json as {"id", "what", "who", "asked", "chase", "done",
"done_on", "chased", "notes"} dicts. No network call is made by this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import clock
import plannerkit as kit

MAX_ITEMS = 300
MAX_WHAT = 120
MAX_WHO = 60
DEFAULT_DAYS = 7
MAX_DAYS = 365


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_waiting(), lambda r: _storage().save_waiting(r))


def _chase_date(value: Any) -> str:
    if value in (None, ""):
        return (clock.today() + timedelta(days=DEFAULT_DAYS)).isoformat()
    import tasks
    day = tasks.parse_due(value)
    if str(day) < clock.today_str():
        raise ValueError("the follow-up date cannot be in the past.")
    return day


def add_item(what: Any, who: Any = None, chase: Any = None, notes: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(what, "what", MAX_WHAT)
    rows = _load()
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"you already have {MAX_ITEMS} items.")
    pool = kit.only_dicts(rows)
    person = kit.clean_text(who, "who", MAX_WHO, required=False)
    if any(not r.get("done") and str(r.get("what", "")).lower() == clean.lower() and str(r.get("who") or "").lower() == person.lower() for r in pool):
        raise ValueError(f"you are already waiting for '{clean}'.")
    item = {"id": kit.new_id(), "what": clean, "who": person, "asked": clock.today_str(), "chase": _chase_date(chase),
            "done": False, "done_on": None, "chased": 0, "notes": kit.clean_text(notes, "notes", 300, required=False)}
    rows.append(item)
    _storage().save_waiting(rows)
    return item


def _find(rows: List[Any], ref: Any) -> Dict[str, Any]:
    return kit.resolve([r for r in kit.only_dicts(rows) if not r.get("done")], ref, "waiting item", "what", "get_waiting")


def resolve_item(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = _find(rows, ref)
    item["done"], item["done_on"] = True, clock.today_str()
    _storage().save_waiting(rows)
    return item


def chase_item(ref: Any, days: Any = None) -> Dict[str, Any]:
    """Records a follow-up and pushes the next one `days` ahead (7 default)."""
    n = DEFAULT_DAYS if days in (None, "") else days
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {MAX_DAYS}.")
    rows = _load()
    item = _find(rows, ref)
    item["chased"] = int(item.get("chased") or 0) + 1
    item["chase"] = (clock.today() + timedelta(days=n)).isoformat()
    _storage().save_waiting(rows)
    return item


def delete_item(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = _find(rows, ref)
    _storage().save_waiting([r for r in rows if r is not item])
    return item


def open_items() -> List[Dict[str, Any]]:
    rows = [r for r in kit.only_dicts(_load()) if not r.get("done") and isinstance(r.get("what"), str)]
    return sorted(rows, key=lambda r: (str(r.get("chase") or "9999"), r["what"].lower()))


def due_items() -> List[Dict[str, Any]]:
    return [r for r in open_items() if str(r.get("chase") or "9999") <= clock.today_str()]


def _who(r: Dict[str, Any]) -> str:
    return f" from {r['who']}" if r.get("who") else ""


def nudges(max_items: int = 1) -> List[str]:
    due = due_items()
    if not due:
        return []
    r = due[0]
    more = f" (and {len(due) - 1} more)" if len(due) > 1 else ""
    return [f"Time to follow up on '{r['what']}'{_who(r)}{more}."][:max_items]


def agenda_lines() -> List[str]:
    return [f"{r['what']}{_who(r)} (follow-up {r['chase']})" for r in due_items()]


def format_item(r: Dict[str, Any]) -> str:
    asked = (clock.today() - clock.parse_day(r["asked"])).days if r.get("asked") else 0
    chased = f", chased {kit.plural(r['chased'], 'time')}" if r.get("chased") else ""
    when = "asked today" if asked <= 0 else f"asked {kit.plural(asked, 'day')} ago"
    return f"{r['what']}{_who(r)} - {when}{chased}, follow up {r.get('chase')} [id={r.get('id', '?')}]"


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_waiting":
            return "Waiting for: " + format_item(add_item(inp.get("what"), inp.get("who"), inp.get("follow_up"), inp.get("notes")))
        if name == "get_waiting":
            rows = open_items()
            if not rows:
                return "You are not waiting for anything. Add something with add_waiting."
            lines = [f"Waiting for {kit.plural(len(rows), 'thing')} ({len(due_items())} due for a follow-up):"]
            lines += [f"- {format_item(r)}" for r in rows[:40]]
            return "\n".join(lines)
        if name == "chase_waiting":
            r = chase_item(inp.get("item"), inp.get("days"))
            return f"Noted the follow-up on '{r['what']}'. Next one on {r['chase']}."
        if name == "resolve_waiting":
            return f"Got it: '{resolve_item(inp.get('item'))['what']}' is no longer pending."
        if name == "delete_waiting":
            return f"Deleted '{delete_item(inp.get('item'))['what']}' from the waiting list."
    except (ValueError, TypeError) as e:
        verb = {"add_waiting": "Not added", "get_waiting": "Cannot show the list", "chase_waiting": "Follow-up not recorded",
                "resolve_waiting": "Not resolved"}.get(name, "Not deleted")
        return f"{verb}: {e}"
    return f"Unknown waiting tool: {name}"
