"""
Hermes Life OS - Routines
===========================
Named checklists you repeat on a rhythm: a morning routine, an evening
shutdown, a weekly review. Tick the steps off as you do them; Hermes keeps one
tick list per day, counts the streak of days you finished the whole routine
(days the routine is not scheduled do not break it, and today only counts once
it is complete) and shows unfinished routines in today's agenda.

Stored in routines.json as {"id", "name", "steps": [{"id", "text"}], "days",
"created", "log": {"YYYY-MM-DD": [step ids]}} dicts; `days` is null for every
day or a list of weekday numbers (Monday is 0). The log keeps the last 120
days. No network call is made by this module.
"""

from __future__ import annotations

import re
from datetime import date as _date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import clock
import plannerkit as kit

MAX_ROUTINES = 20
MAX_NAME = 40
MAX_STEPS = 20
MAX_STEP = 80
LOG_DAYS = 120
BACK_DAYS = 7
_DAYS = {"mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "wednesday": 2, "thu": 3, "thur": 3,
         "thurs": 3, "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5, "sun": 6, "sunday": 6}
_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_routines(), lambda r: _storage().save_routines(r))


def parse_days(value: Any) -> Optional[List[int]]:
    """None for every day; else the sorted weekday numbers for 'weekdays',
    'weekends' or names like 'mon, wed, fri' (a list of names works too)."""
    if value is None or (isinstance(value, str) and not value.strip()) or value == []:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("daily", "every day", "everyday", "all"):
            return None
        if text in ("weekdays", "weekday"):
            return [0, 1, 2, 3, 4]
        if text in ("weekends", "weekend"):
            return [5, 6]
        parts = [p for p in re.split(r"[,;\s]+", text) if p]
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        parts = [v.strip().lower() for v in value if v.strip()]
    else:
        raise ValueError("days must be 'daily', 'weekdays', 'weekends' or weekday names such as mon, wed, fri.")
    out = set()
    for p in parts:
        if p not in _DAYS:
            raise ValueError(f"'{p}' is not a weekday. Use names such as mon, wed, fri, or daily, weekdays or weekends.")
        out.add(_DAYS[p])
    if len(out) == 7:
        return None
    return sorted(out)


def days_text(item: Dict[str, Any]) -> str:
    days = item.get("days")
    if not days:
        return "daily"
    if days == [0, 1, 2, 3, 4]:
        return "weekdays"
    if days == [5, 6]:
        return "weekends"
    return ", ".join(_NAMES[d] for d in days if isinstance(d, int) and 0 <= d <= 6)


def _parse_steps(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [p for p in re.split(r"[\n;]+", value)]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError("steps must be a list of short texts.")
    steps = [kit.clean_text(v, "step", MAX_STEP) for v in value if v.strip()]
    if not steps:
        raise ValueError("a routine needs at least one step.")
    if len(steps) > MAX_STEPS:
        raise ValueError(f"a routine can have at most {MAX_STEPS} steps.")
    lower = [s.lower() for s in steps]
    if len(set(lower)) != len(lower):
        raise ValueError("two steps have the same text.")
    return steps


def steps_of(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    s = item.get("steps")
    return [x for x in s if isinstance(x, dict) and isinstance(x.get("text"), str) and x.get("id")] if isinstance(s, list) else []


def scheduled(item: Dict[str, Any], day: _date) -> bool:
    days = item.get("days")
    return not days or (isinstance(days, list) and day.weekday() in days)


def done_ids(item: Dict[str, Any], day: _date) -> List[str]:
    log = item.get("log") if isinstance(item.get("log"), dict) else {}
    ids = log.get(day.isoformat())
    valid = {s["id"] for s in steps_of(item)}
    return [i for i in ids if i in valid] if isinstance(ids, list) else []


def progress(item: Dict[str, Any], day: Optional[_date] = None) -> Tuple[int, int]:
    day = day or clock.today()
    return len(set(done_ids(item, day))), len(steps_of(item))


def streak(item: Dict[str, Any]) -> int:
    """Consecutive scheduled days, ending today or yesterday, on which every
    step was done. Today only counts once complete and never breaks it."""
    today = clock.today()
    total = len(steps_of(item))
    if not total:
        return 0
    count = 0
    for back in range(0, LOG_DAYS):
        d = today - timedelta(days=back)
        if not scheduled(item, d):
            continue
        if progress(item, d)[0] >= total:
            count += 1
        elif back == 0:
            continue
        else:
            break
    return count


# ------------------------------------------------------------------ operations

def add_routine(name: Any, steps: Any, days: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(name, "routine name", MAX_NAME)
    texts = _parse_steps(steps)
    parsed = parse_days(days)
    rows = _load()
    if len(rows) >= MAX_ROUTINES:
        raise ValueError(f"you already have {MAX_ROUTINES} routines.")
    if any(str(r.get("name", "")).lower() == clean.lower() for r in kit.only_dicts(rows)):
        raise ValueError(f"there is already a routine called '{clean}'.")
    item = {"id": kit.new_id(), "name": clean, "steps": [{"id": kit.new_id(), "text": t} for t in texts],
            "days": parsed, "created": clock.today_str(), "log": {}}
    rows.append(item)
    _storage().save_routines(rows)
    return item


def _find_step(item: Dict[str, Any], ref: Any) -> Dict[str, Any]:
    return kit.resolve(steps_of(item), ref, "step", "text", "get_routines")


def check_step(ref: Any, step: Any, undo: Any = False, on: Any = None) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "routine", "name", "get_routines")
    today = clock.today()
    if on in (None, ""):
        day = today
    else:
        day = clock.parse_day(on)
        if day > today:
            raise ValueError("you cannot tick steps for a day that has not happened yet.")
        if (today - day).days > BACK_DAYS:
            raise ValueError(f"you can tick steps up to {BACK_DAYS} days back.")
    if not isinstance(step, str) or not step.strip():
        raise ValueError("say which step (its id or some words), or 'all'.")
    log = item.get("log") if isinstance(item.get("log"), dict) else {}
    item["log"] = log
    current = set(done_ids(item, day))
    ids = [s["id"] for s in steps_of(item)]
    if step.strip().lower() == "all":
        target = set() if undo else set(ids)
    else:
        sid = _find_step(item, step)["id"]
        target = (current - {sid}) if undo else (current | {sid})
    if target:
        log[day.isoformat()] = [i for i in ids if i in target]
    else:
        log.pop(day.isoformat(), None)
    cutoff = (today - timedelta(days=LOG_DAYS)).isoformat()
    for k in [k for k in log if not isinstance(k, str) or k < cutoff]:
        log.pop(k, None)
    _storage().save_routines(rows)
    return {"item": item, "day": day}


def update_routine(ref: Any, fields: Any) -> Dict[str, Any]:
    kit.check_fields(fields, ("name", "days", "steps"))
    rows = _load()
    item = kit.resolve(rows, ref, "routine", "name", "get_routines")
    changes: Dict[str, Any] = {}
    if "name" in fields:
        n = kit.clean_text(fields["name"], "routine name", MAX_NAME)
        if any(r is not item and str(r.get("name", "")).lower() == n.lower() for r in kit.only_dicts(rows)):
            raise ValueError(f"there is already a routine called '{n}'.")
        changes["name"] = n
    if "days" in fields:
        changes["days"] = parse_days(fields["days"])
    if "steps" in fields:
        texts = _parse_steps(fields["steps"])
        old = {s["text"].lower(): s["id"] for s in steps_of(item)}
        changes["steps"] = [{"id": old.get(t.lower(), kit.new_id()), "text": t} for t in texts]
    item.update(changes)
    _storage().save_routines(rows)
    return item


def delete_routine(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "routine", "name", "get_routines")
    _storage().save_routines([r for r in rows if r is not item])
    return item


def get(ref: Any) -> Dict[str, Any]:
    return kit.resolve(_load(), ref, "routine", "name", "get_routines")


def unfinished_today() -> List[Dict[str, Any]]:
    today = clock.today()
    return [r for r in kit.only_dicts(_load()) if steps_of(r) and scheduled(r, today) and progress(r)[0] < len(steps_of(r))]


def agenda_lines() -> List[str]:
    out = []
    for r in unfinished_today():
        done, total = progress(r)
        pending = [s["text"] for s in steps_of(r) if s["id"] not in done_ids(r, clock.today())]
        out.append(f"{r['name']}: {done} of {total} steps done (next: {pending[0]})")
    return out


# ------------------------------------------------------------------ formatting

def format_routine(item: Dict[str, Any], detail: bool = False) -> str:
    done, total = progress(item)
    s = streak(item)
    today_note = "" if scheduled(item, clock.today()) else ", not scheduled today"
    line = f"{item['name']} ({days_text(item)}): {done}/{total} today{today_note}"
    if s:
        line += f", streak {kit.plural(s, 'day')}"
    line += f" [id={item.get('id', '?')}]"
    if not detail:
        return line
    ticked = set(done_ids(item, clock.today()))
    return line + "\n" + "\n".join(f"  [{'x' if st['id'] in ticked else ' '}] {st['text']}" for st in steps_of(item))


def format_all(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No routines yet. Add one with add_routine, for example a morning routine with its steps."
    return f"{kit.plural(len(rows), 'routine')}:\n" + "\n".join(f"- {format_routine(r)}" for r in rows)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_routine":
            return "Routine added: " + format_routine(add_routine(inp.get("name"), inp.get("steps"), inp.get("days")), True)
        if name == "get_routines":
            if inp.get("routine"):
                return format_routine(get(inp["routine"]), True)
            return format_all(kit.only_dicts(_load()))
        if name == "check_routine_step":
            undo = inp.get("undo") is True
            res = check_step(inp.get("routine"), inp.get("step"), undo, inp.get("date"))
            item = res["item"]
            done, total = progress(item, res["day"])
            head = f"{'Unticked' if undo else 'Ticked'} on {res['day'].isoformat()}: {done}/{total} steps done."
            if not undo and done == total and res["day"] == clock.today():
                head += f" '{item['name']}' is complete" + (f" - streak {kit.plural(streak(item), 'day')}." if streak(item) else ".")
            return head + "\n" + format_routine(item, True) if res["day"] == clock.today() else head
        if name == "update_routine":
            return "Routine updated: " + format_routine(update_routine(inp.get("routine"), inp.get("fields")), True)
        if name == "delete_routine":
            return f"Deleted routine {delete_routine(inp.get('routine'))['name']}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_routine": "Routine not added", "get_routines": "Cannot show routines",
                "check_routine_step": "Step not changed"}.get(name, "Routine not changed")
        return f"{verb}: {e}"
    return f"Unknown routine tool: {name}"
