"""
Hermes Life OS - Time Budgets
===============================
Say how many hours a week a category of your time blocks should get: at least
(a minimum, like deep work or exercise) or at most (a limit, like meetings).
Hermes compares each budget with the blocks you marked done since Monday and
the blocks still planned for the rest of the week, then tells you which
budgets are met, on course, short or over. Late in the week a nudge points at
budgets that are still short or already over.

Stored in timebudgets.json as {"id", "category", "hours", "kind"} dicts, one
per category. No network call is made by this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import clock
import plannerkit as kit

KINDS = ("min", "max")
MAX_ITEMS = 30
MAX_HOURS = 80.0
MIN_HOURS = 0.5
NUDGE_FROM_WEEKDAY = 3  # Thursday
CLOSE_AT = 0.8


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_timebudgets(), lambda r: _storage().save_timebudgets(r))


def _valid(r: Any) -> bool:
    return (isinstance(r, dict) and isinstance(r.get("category"), str) and bool(r["category"].strip())
            and isinstance(r.get("hours"), (int, float)) and not isinstance(r.get("hours"), bool)
            and r["hours"] > 0 and r.get("kind") in KINDS)


def budgets() -> List[Dict[str, Any]]:
    return sorted((r for r in _load() if _valid(r)), key=lambda r: r["category"].lower())


def set_budget(category: Any, hours: Any, kind: Any = None) -> Dict[str, Any]:
    import timeblocks
    cat = timeblocks._clean_category(category)
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not MIN_HOURS <= hours <= MAX_HOURS:
        raise ValueError(f"hours must be a number from {MIN_HOURS:g} to {MAX_HOURS:g} per week.")
    word = "min" if kind in (None, "") else (kind.strip().lower() if isinstance(kind, str) else "")
    if word not in KINDS:
        raise ValueError("the kind must be 'min' (at least) or 'max' (at most).")
    rows = _load()
    same = next((r for r in kit.only_dicts(rows) if str(r.get("category", "")).lower() == cat), None)
    if same is not None:
        same.update({"hours": hours, "kind": word})
        item = same
    else:
        if len(rows) >= MAX_ITEMS:
            raise ValueError(f"you already have {MAX_ITEMS} budgets.")
        item = {"id": kit.new_id(), "category": cat, "hours": hours, "kind": word}
        rows.append(item)
    _storage().save_timebudgets(rows)
    return item


def delete_budget(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "time budget", "category", "get_time_budget")
    _storage().save_timebudgets([r for r in rows if r is not item])
    return item


def week_start() -> str:
    today = clock.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def _status(b: Dict[str, Any], done: int, planned: int) -> str:
    cap = b["hours"] * 60
    if b["kind"] == "min":
        if done >= cap:
            return "met"
        return "on course" if done + planned >= cap else "short"
    if done > cap:
        return "over"
    return "close" if done >= cap * CLOSE_AT else "ok"


def progress() -> Dict[str, Any]:
    """{"from", "to", "rows": [{"budget", "done", "planned", "status"}]} for the
    week from Monday to Sunday; `planned` is the not yet done time still ahead
    (today and later)."""
    import timeblocks
    first = week_start()
    last = (clock.parse_day(first) + timedelta(days=6)).isoformat()
    today = clock.today_str()
    done: Dict[str, int] = {}
    planned: Dict[str, int] = {}
    for r in timeblocks._rows(timeblocks._load()):
        s = timeblocks.span(r)
        if not s or not first <= r["date"] <= last:
            continue
        cat = str(r.get("category") or timeblocks.DEFAULT_CATEGORY)
        if r.get("done"):
            done[cat] = done.get(cat, 0) + s[1] - s[0]
        elif r["date"] >= today:
            planned[cat] = planned.get(cat, 0) + s[1] - s[0]
    rows = [{"budget": b, "done": done.get(b["category"], 0), "planned": planned.get(b["category"], 0),
             "status": _status(b, done.get(b["category"], 0), planned.get(b["category"], 0))} for b in budgets()]
    return {"from": first, "to": last, "rows": rows}


def _hm(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if h and m else f"{h}h" if h else f"{m}m"


def _concerns() -> List[str]:
    if clock.today().weekday() < NUDGE_FROM_WEEKDAY:
        return []
    out = []
    for r in progress()["rows"]:
        b = r["budget"]
        cap = round(b["hours"] * 60)
        if r["status"] == "short":
            out.append(f"'{b['category']}' is short for the week: {_hm(r['done'])} done of at least {_hm(cap)} and only "
                       f"{_hm(r['planned'])} planned. Block time for it.")
        elif r["status"] == "over":
            out.append(f"'{b['category']}' is over its limit: {_hm(r['done'])} against at most {_hm(cap)}.")
    return out


def nudges(max_items: int = 1) -> List[str]:
    return _concerns()[:max_items]


def agenda_lines() -> List[str]:
    return _concerns()


def format_progress(p: Dict[str, Any]) -> str:
    if not p["rows"]:
        return "No time budgets yet. Set one with set_time_budget, for example category 'deep work', 10 hours, kind 'min'."
    lines = [f"Time budgets for the week {p['from']} to {p['to']}:"]
    for r in p["rows"]:
        b = r["budget"]
        cap = round(b["hours"] * 60)
        word = "at least" if b["kind"] == "min" else "at most"
        extra = f", {_hm(r['planned'])} still planned" if r["planned"] else ""
        lines.append(f"- {b['category']}: {_hm(r['done'])} done of {word} {_hm(cap)}{extra} -> {r['status']}")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "set_time_budget":
            b = set_budget(inp.get("category"), inp.get("hours"), inp.get("kind"))
            word = "at least" if b["kind"] == "min" else "at most"
            return f"Budget set: '{b['category']}' {word} {b['hours']:g} hours a week."
        if name == "get_time_budget":
            return format_progress(progress())
        if name == "delete_time_budget":
            return f"Deleted the budget for '{delete_budget(inp.get('category'))['category']}'."
    except (ValueError, TypeError) as e:
        verb = {"set_time_budget": "Budget not set", "get_time_budget": "Cannot show budgets"}.get(name, "Budget not deleted")
        return f"{verb}: {e}"
    return f"Unknown time budget tool: {name}"
