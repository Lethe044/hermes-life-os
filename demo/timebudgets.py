"""
Hermes Life OS - Time Budgets
===============================
Say how many hours a week a category of your time blocks should get: at least
(a minimum, like deep work or exercise) or at most (a limit, like meetings).
Hermes compares each budget with the blocks you marked done since Monday and
the blocks still planned for the rest of the week, then tells you which
budgets are met, on course, short or over. Late in the week a nudge points at
budgets that are still short or already over, and fill_time_budget proposes (or with
apply=true creates) the time blocks that would close a shortfall.

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


CHUNK = 120
MIN_CHUNK = 30
ROUND = 15


def _free_gaps(day: str) -> List[List[int]]:
    import planday
    import timeblocks
    if day == clock.today_str():
        return [list(g) for g in planday._gaps(day)]
    return [list(g) for g in timeblocks.day_plan(day)["gaps"]]


def fill_plan(category: Any = None) -> Dict[str, Any]:
    """Proposed time blocks that would close the shortfall of every minimum
    budget that is short this week (or just `category`): {"proposals":
    [{"category", "date", "start", "end", "minutes"}], "uncovered": {category:
    minutes}}. At most one block of two hours per day and budget; overloaded
    days are skipped."""
    import timeblocks
    import workload
    want = timeblocks._clean_category(category) if category not in (None, "") else None
    prog = progress()
    last = prog["to"]
    days = []
    cursor = clock.today()
    while cursor.isoformat() <= last:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    status = {r["date"]: r["status"] for r in workload.forecast(len(days))["days"]} if days else {}
    gaps = {d: _free_gaps(d) for d in days if status.get(d) != "overloaded"}
    proposals: List[Dict[str, Any]] = []
    uncovered: Dict[str, int] = {}
    for r in prog["rows"]:
        b = r["budget"]
        if b["kind"] != "min" or r["status"] != "short" or (want and b["category"] != want):
            continue
        need = round(b["hours"] * 60) - r["done"] - r["planned"]
        for d in days:
            if need < MIN_CHUNK:
                break
            if d not in gaps:
                continue
            for g in gaps[d]:
                length = g[1] - g[0]
                take = min(CHUNK, length, need)
                take -= take % ROUND
                if take < MIN_CHUNK:
                    continue
                proposals.append({"category": b["category"], "date": d, "start": timeblocks.fmt_time(g[0]),
                                  "end": timeblocks.fmt_time(g[0] + take), "minutes": take})
                g[0] += take + 5
                need -= take
                break
        if need >= MIN_CHUNK:
            uncovered[b["category"]] = need
    return {"proposals": proposals, "uncovered": uncovered}


def apply_fill(plan: Dict[str, Any]) -> int:
    import timeblocks
    made = 0
    for p in plan["proposals"]:
        timeblocks.add_time_block(title=p["category"].capitalize(), start=p["start"], end=p["end"], date=p["date"],
                                  category=p["category"])
        made += 1
    return made


def format_fill(plan: Dict[str, Any], applied: bool) -> str:
    if not plan["proposals"] and not plan["uncovered"]:
        return "No minimum budget is short this week, so there is nothing to fill."
    lines = ["Time blocks created:" if applied else "Proposed time blocks (nothing saved yet):"]
    for p in plan["proposals"]:
        lines.append(f"- {clock.parse_day(p['date']).strftime('%a %d %b')} {p['start']}-{p['end']} {p['category']} "
                     f"({_hm(p['minutes'])})")
    for cat, mins in plan["uncovered"].items():
        lines.append(f"Still {_hm(mins)} short for '{cat}': no more room this week.")
    if not applied and plan["proposals"]:
        lines.append("Run fill_time_budget again with apply=true to save these as time blocks.")
    return "\n".join(lines)


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
        if name == "fill_time_budget":
            apply = inp.get("apply")
            if apply not in (None, True, False):
                raise ValueError("apply must be true or false.")
            plan = fill_plan(inp.get("category"))
            if apply and plan["proposals"]:
                apply_fill(plan)
            return format_fill(plan, bool(apply) and bool(plan["proposals"]))
        if name == "delete_time_budget":
            return f"Deleted the budget for '{delete_budget(inp.get('category'))['category']}'."
    except (ValueError, TypeError) as e:
        verb = {"set_time_budget": "Budget not set", "get_time_budget": "Cannot show budgets",
                "fill_time_budget": "Cannot fill the budget"}.get(name, "Budget not deleted")
        return f"{verb}: {e}"
    return f"Unknown time budget tool: {name}"
