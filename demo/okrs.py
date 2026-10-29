"""
Hermes Life OS - Objectives and Key Results
=============================================
Goals with a deadline and measurable results, for a week, a month, a quarter
or a year. An objective ("Get fit this quarter") has a period and up to eight
key results, each a number to move from a starting value to a target ("run 100
km", "weight 85 -> 80 kg", "read 12 books"). Recording a result stores a
history point; the objective's progress is the average of its results. Hermes
compares that with how much of the period has passed and says whether you are
ahead of pace, on track or behind, and nudges when an objective is about to end
unfinished.

This is separate from `goals` (a metric Hermes already tracks, like "sleep at
least 7 hours") and from savings goals (money): key results are numbers you
report yourself.

Stored in okrs.json as {"id", "name", "start", "end", "notes", "status",
"created", "key_results": [{"id", "name", "start_value", "target", "current",
"unit", "history": [{"date", "value"}]}]} dicts; `status` is active, done or
dropped. No network call is made by this module.
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import clock

MAX_OBJECTIVES = 100
MAX_KEY_RESULTS = 8
MAX_NAME = 80
MAX_UNIT = 15
MAX_NOTES = 200
MAX_HISTORY = 400
MAX_PERIOD_DAYS = 400
MAX_VALUE = 1_000_000_000
STATUSES = ("active", "done", "dropped")
NUDGE_DAYS = 7
NUDGE_BELOW = 0.7
AGENDA_DAYS = 7
BEHIND_BY = 0.2        # this far below the expected pace is "behind"
SLIGHTLY_BEHIND_BY = 0.05
AHEAD_BY = 0.15


def _pct(x: float) -> int:
    """A share as a whole percent, halves rounding up (12.5 -> 13)."""
    return int(math.floor(x * 100 + 0.5))


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


# ------------------------------------------------------------------ parsing

def _clean_name(value: Any, what: str = "objective") -> str:
    if not isinstance(value, str) or not " ".join(value.split()):
        raise ValueError(f"the {what} needs a name.")
    name = " ".join(value.split())
    if len(name) > MAX_NAME:
        raise ValueError(f"the name can be at most {MAX_NAME} characters.")
    return name


def _clean_unit(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("the unit must be text.")
    unit = value.strip()
    if len(unit) > MAX_UNIT:
        raise ValueError(f"the unit can be at most {MAX_UNIT} characters.")
    return unit


def _clean_notes(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("notes must be text.")
    return value.strip()[:MAX_NOTES]


def _num(value: Any, what: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number.") from None
    if math.isnan(number) or math.isinf(number) or abs(number) > MAX_VALUE:
        raise ValueError(f"{what} must be a number between -{MAX_VALUE:,} and {MAX_VALUE:,}.")
    return round(number, 2)


def _quarter(year: int, q: int) -> Tuple[str, str]:
    if not 2000 <= year <= 2100:
        raise ValueError("year out of range")
    first = clock.add_months(clock.parse_day(f"{year}-01-01"), 3 * (q - 1))
    last = clock.add_months(first, 3) - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def parse_period(value: Any) -> Tuple[str, str]:
    """(start, end) for "week", "month", "quarter", "year" (the current one),
    "2026-Q4" / "Q4" / "Q4 2026", "2026-10" or "2026". Raises ValueError."""
    if value is None or (isinstance(value, str) and not value.strip()):
        value = "quarter"
    if not isinstance(value, str):
        raise ValueError("the period must be text such as 'quarter', '2026-Q4', '2026-10' or 'week'.")
    text = value.strip().lower().replace(" ", "-")
    today = clock.today()
    if text == "week":
        monday = today - timedelta(days=today.weekday())
        return monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    if text == "month":
        first = today.replace(day=1)
        return first.isoformat(), (clock.add_months(first, 1) - timedelta(days=1)).isoformat()
    if text == "quarter":
        return _quarter(today.year, (today.month - 1) // 3 + 1)
    if text == "year":
        return f"{today.year}-01-01", f"{today.year}-12-31"
    parts = text.split("-")
    try:
        if len(parts) == 1 and parts[0].isdigit() and len(parts[0]) == 4 and 2000 <= int(parts[0]) <= 2100:
            return f"{parts[0]}-01-01", f"{parts[0]}-12-31"
        if len(parts) == 1 and parts[0] in ("q1", "q2", "q3", "q4"):
            return _quarter(today.year, int(parts[0][1]))
        if len(parts) == 2 and parts[1] in ("q1", "q2", "q3", "q4") and parts[0].isdigit() and len(parts[0]) == 4:
            return _quarter(int(parts[0]), int(parts[1][1]))
        if len(parts) == 2 and parts[0] in ("q1", "q2", "q3", "q4") and parts[1].isdigit() and len(parts[1]) == 4:
            return _quarter(int(parts[1]), int(parts[0][1]))
        if len(parts) == 2 and all(p.isdigit() for p in parts) and len(parts[0]) == 4 and 2000 <= int(parts[0]) <= 2100:
            first = clock.parse_day(f"{parts[0]}-{parts[1]}-01")
            return first.isoformat(), (clock.add_months(first, 1) - timedelta(days=1)).isoformat()
    except (ValueError, OverflowError):
        pass
    raise ValueError(f"I couldn't understand the period '{value.strip()}'. Use week, month, quarter, year, "
                     f"2026-Q4, 2026-10 or 2026 (or give start and end dates).")


def _period(period: Any, start: Any, end: Any) -> Tuple[str, str]:
    if start not in (None, "") or end not in (None, ""):
        if period not in (None, ""):
            raise ValueError("give either a period or start and end dates, not both.")
        first = clock.parse_day(start).isoformat() if start not in (None, "") else clock.today_str()
        if end in (None, ""):
            raise ValueError("give an end date.")
        last = clock.parse_day(end).isoformat()
    else:
        first, last = parse_period(period)
    if last < first:
        raise ValueError("the end date cannot be before the start date.")
    if (clock.parse_day(last) - clock.parse_day(first)).days + 1 > MAX_PERIOD_DAYS:
        raise ValueError(f"an objective can cover at most {MAX_PERIOD_DAYS} days.")
    return first, last


def _build_kr(name: Any, target: Any, start_value: Any = 0, unit: Any = None) -> Dict[str, Any]:
    clean = _clean_name(name, "key result")
    goal = _num(target, "target")
    begin = _num(0 if start_value in (None, "") else start_value, "start_value")
    if goal == begin:
        raise ValueError("the target must differ from the starting value.")
    return {"id": new_id(), "name": clean, "start_value": begin, "target": goal, "current": begin,
            "unit": _clean_unit(unit), "history": []}


# ------------------------------------------------------------------ storage

def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_okrs()
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
        _storage().save_okrs(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def key_results(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    krs = obj.get("key_results")
    return [k for k in krs if isinstance(k, dict)] if isinstance(krs, list) else []


def _resolve(rows: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which objective (its id or some words from its name).")
    key = ref.strip().lower()
    pool = _rows(rows)
    for r in pool:
        if str(r.get("id", "")).lower() == key or str(r.get("name", "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no objective matches '{ref.strip()}'. Use get_okrs to see them.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} objectives ({'; '.join(str(r.get('name')) for r in hits[:5])}). "
                     f"Use the full name or the id.")


def _resolve_kr(obj: Dict[str, Any], ref: Any) -> Dict[str, Any]:
    krs = key_results(obj)
    if not isinstance(ref, str) or not ref.strip():
        if len(krs) == 1:
            return krs[0]
        raise ValueError("say which key result (its id or some words from its name).")
    key = ref.strip().lower()
    for k in krs:
        if str(k.get("id", "")).lower() == key or str(k.get("name", "")).lower() == key:
            return k
    hits = [k for k in krs if key in str(k.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"'{obj.get('name')}' has no key result matching '{ref.strip()}'.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} key results ({'; '.join(str(k.get('name')) for k in hits[:5])}). "
                     f"Use the full name or the id.")


# ------------------------------------------------------------------ progress

def kr_progress(kr: Dict[str, Any]) -> float:
    """0.0-1.0: how far `current` has moved from `start_value` towards `target`
    (a target below the start means "go down"). 0.0 for unreadable numbers."""
    try:
        begin, goal, now = float(kr["start_value"]), float(kr["target"]), float(kr["current"])
    except (KeyError, TypeError, ValueError):
        return 0.0
    if any(isinstance(kr.get(k), bool) for k in ("start_value", "target", "current")):
        return 0.0
    if goal == begin or any(math.isnan(x) or math.isinf(x) for x in (begin, goal, now)):
        return 0.0
    return max(0.0, min(1.0, (now - begin) / (goal - begin)))


def progress(obj: Dict[str, Any]) -> float:
    krs = key_results(obj)
    return sum(kr_progress(k) for k in krs) / len(krs) if krs else 0.0


def expected(obj: Dict[str, Any], today: Optional[Any] = None) -> Optional[float]:
    """Share of the period that has passed (0.0 before it starts, 1.0 after it
    ends); None when the dates cannot be read."""
    today = today or clock.today()
    try:
        first, last = clock.parse_day(obj.get("start")), clock.parse_day(obj.get("end"))
    except ValueError:
        return None
    if today < first:
        return 0.0
    total = (last - first).days + 1
    if total <= 0:
        return None
    return min(1.0, ((today - first).days + 1) / total)


def pace(obj: Dict[str, Any], today: Optional[Any] = None) -> str:
    """achieved, not started, missed, dropped, done, ahead of pace, on track,
    slightly behind, behind (or "no key results yet" / "dates unreadable")."""
    status = obj.get("status") or "active"
    if status == "dropped":
        return "dropped"
    if status == "done":
        return "done"
    today = today or clock.today()
    if not key_results(obj):
        return "no key results yet"
    prog = progress(obj)
    exp = expected(obj, today)
    if exp is None:
        return "dates unreadable"
    if prog >= 1.0:
        return "achieved"
    try:
        if today < clock.parse_day(obj.get("start")):
            return "not started"
        if today > clock.parse_day(obj.get("end")):
            return "missed"
    except ValueError:
        return "dates unreadable"
    gap = prog - exp
    if gap >= AHEAD_BY:
        return "ahead of pace"
    if gap >= -SLIGHTLY_BEHIND_BY:
        return "on track"
    if gap >= -BEHIND_BY:
        return "slightly behind"
    return "behind"


def days_left(obj: Dict[str, Any], today: Optional[Any] = None) -> Optional[int]:
    today = today or clock.today()
    try:
        return (clock.parse_day(obj.get("end")) - today).days
    except ValueError:
        return None


# ------------------------------------------------------------------ operations

def add_objective(name: Any, period: Any = None, start: Any = None, end: Any = None, notes: Any = None,
                  results: Any = None) -> Dict[str, Any]:
    """Creates an objective, optionally with its first key results
    ([{"name", "target", "start_value", "unit"}]). All or nothing."""
    clean = _clean_name(name)
    first, last = _period(period, start, end)
    note = _clean_notes(notes)
    krs: List[Dict[str, Any]] = []
    if results not in (None, []):
        if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
            raise ValueError("key_results must be a list of {name, target, start_value, unit}.")
        if len(results) > MAX_KEY_RESULTS:
            raise ValueError(f"an objective can have at most {MAX_KEY_RESULTS} key results.")
        names = set()
        for r in results:
            kr = _build_kr(r.get("name"), r.get("target"), r.get("start_value"), r.get("unit"))
            if kr["name"].lower() in names:
                raise ValueError(f"there are two key results called '{kr['name']}'.")
            names.add(kr["name"].lower())
            krs.append(kr)
    rows = _load()
    if len(rows) >= MAX_OBJECTIVES:
        raise ValueError(f"you already have {MAX_OBJECTIVES} objectives - delete old ones first.")
    if any(str(r.get("name", "")).lower() == clean.lower() and (r.get("status") or "active") == "active"
           for r in _rows(rows)):
        raise ValueError(f"there is already an active objective called '{clean}'.")
    obj = {"id": new_id(), "name": clean, "start": first, "end": last, "notes": note, "status": "active",
           "created": clock.today_str(), "key_results": krs}
    rows.append(obj)
    _storage().save_okrs(rows)
    return obj


def add_key_result(ref: Any, name: Any, target: Any, start_value: Any = 0, unit: Any = None) -> Dict[str, Any]:
    rows = _load()
    obj = _resolve(rows, ref)
    kr = _build_kr(name, target, start_value, unit)
    if not isinstance(obj.get("key_results"), list):
        obj["key_results"] = []
    if len(key_results(obj)) >= MAX_KEY_RESULTS:
        raise ValueError(f"'{obj.get('name')}' already has {MAX_KEY_RESULTS} key results.")
    if any(str(k.get("name", "")).lower() == kr["name"].lower() for k in key_results(obj)):
        raise ValueError(f"'{obj.get('name')}' already has a key result called '{kr['name']}'.")
    obj["key_results"].append(kr)
    _storage().save_okrs(rows)
    return {"objective": obj, "key_result": kr}


def record_key_result(ref: Any, kr_ref: Any = None, value: Any = None, add: Any = None) -> Dict[str, Any]:
    """Sets a key result's current value (`value`) or moves it by `add` (which
    may be negative) and stores a history point. Exactly one of the two."""
    if (value in (None, "")) == (add in (None, "")):
        raise ValueError("give either value (the new total) or add (the change), not both and not neither.")
    new_value = _num(value, "value") if value not in (None, "") else None
    delta = _num(add, "add") if add not in (None, "") else None
    rows = _load()
    obj = _resolve(rows, ref)
    kr = _resolve_kr(obj, kr_ref)
    before = kr_progress(kr)
    try:
        base = float(kr.get("current"))
        if isinstance(kr.get("current"), bool) or math.isnan(base) or math.isinf(base):
            raise ValueError
    except (TypeError, ValueError):
        base = float(kr.get("start_value")) if isinstance(kr.get("start_value"), (int, float)) else 0.0
    result = new_value if new_value is not None else _num(base + delta, "the new total")
    kr["current"] = result
    hist = kr.get("history") if isinstance(kr.get("history"), list) else []
    today = clock.today_str()
    hist = [h for h in hist if isinstance(h, dict) and h.get("date") != today]
    hist.append({"date": today, "value": result})
    kr["history"] = hist[-MAX_HISTORY:]
    _storage().save_okrs(rows)
    return {"objective": obj, "key_result": kr, "before": before}


def update_okr(ref: Any, fields: Any, kr_ref: Any = None, edit_key_result: bool = False) -> Dict[str, Any]:
    """Changes an objective (name, notes, start, end, status) or, with
    `edit_key_result`, one of its key results (name, target, start_value,
    unit, current)."""
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields.")
    rows = _load()
    obj = _resolve(rows, ref)
    if not edit_key_result:
        unknown = [k for k in fields if k not in ("name", "notes", "start", "end", "status")]
        if unknown:
            raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change name, notes, start, end "
                             f"and status (use key_result to change a key result).")
        changes: Dict[str, Any] = {}
        if "name" in fields:
            n = _clean_name(fields["name"])
            if any(r is not obj and str(r.get("name", "")).lower() == n.lower() and (r.get("status") or "active") == "active"
                   for r in _rows(rows)):
                raise ValueError(f"there is already an active objective called '{n}'.")
            changes["name"] = n
        if "notes" in fields:
            changes["notes"] = _clean_notes(fields["notes"])
        if "status" in fields:
            if fields["status"] not in STATUSES:
                raise ValueError("status must be active, done or dropped.")
            changes["status"] = fields["status"]
        if "start" in fields or "end" in fields:
            first = clock.parse_day(fields["start"]).isoformat() if "start" in fields else obj.get("start")
            last = clock.parse_day(fields["end"]).isoformat() if "end" in fields else obj.get("end")
            if not isinstance(first, str) or not isinstance(last, str):
                raise ValueError("give both start and end.")
            if last < first:
                raise ValueError("the end date cannot be before the start date.")
            if (clock.parse_day(last) - clock.parse_day(first)).days + 1 > MAX_PERIOD_DAYS:
                raise ValueError(f"an objective can cover at most {MAX_PERIOD_DAYS} days.")
            changes["start"], changes["end"] = first, last
        obj.update(changes)
        _storage().save_okrs(rows)
        return {"objective": obj, "key_result": None}
    kr = _resolve_kr(obj, kr_ref)
    unknown = [k for k in fields if k not in ("name", "target", "start_value", "unit", "current")]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))} of a key result. You can change name, target, "
                         f"start_value, unit and current.")
    changes = {}
    if "name" in fields:
        n = _clean_name(fields["name"], "key result")
        if any(k is not kr and str(k.get("name", "")).lower() == n.lower() for k in key_results(obj)):
            raise ValueError(f"'{obj.get('name')}' already has a key result called '{n}'.")
        changes["name"] = n
    if "unit" in fields:
        changes["unit"] = _clean_unit(fields["unit"])
    for key in ("target", "start_value", "current"):
        if key in fields:
            changes[key] = _num(fields[key], key)
    if changes.get("target", kr.get("target")) == changes.get("start_value", kr.get("start_value")):
        raise ValueError("the target must differ from the starting value.")
    kr.update(changes)
    _storage().save_okrs(rows)
    return {"objective": obj, "key_result": kr}


def delete_okr(ref: Any, kr_ref: Any = None, key_result: bool = False) -> Dict[str, Any]:
    rows = _load()
    obj = _resolve(rows, ref)
    if key_result:
        kr = _resolve_kr(obj, kr_ref)
        obj["key_results"] = [k for k in key_results(obj) if k is not kr]
        _storage().save_okrs(rows)
        return {"objective": obj, "key_result": kr}
    _storage().save_okrs([r for r in rows if r is not obj])
    return {"objective": obj, "key_result": None}


def listing(status: str = "active") -> List[Dict[str, Any]]:
    """Objectives of one status ("all" for every one), soonest ending first."""
    out = [r for r in _rows(_load()) if status == "all" or (r.get("status") or "active") == status]
    return sorted(out, key=lambda r: (str(r.get("end")), str(r.get("name", "")).lower()))


# ------------------------------------------------------------------ nudges and agenda

def _near_deadline() -> List[Dict[str, Any]]:
    out = []
    for r in listing("active"):
        left = days_left(r)
        if left is None or not 0 <= left <= NUDGE_DAYS or not key_results(r):
            continue
        if progress(r) < NUDGE_BELOW:
            out.append(r)
    return out


def _ends(left: int) -> str:
    return "ends today" if left == 0 else ("ends tomorrow" if left == 1 else f"ends in {left} days")


def nudges(max_items: int = 1) -> List[str]:
    return [f"Objective '{r['name']}' {_ends(days_left(r))} and is {_pct(progress(r))}% done."
            for r in _near_deadline()[:max_items]]


def agenda_lines() -> List[str]:
    return [f"{r['name']}: {_ends(days_left(r))}, {_pct(progress(r))}% done" for r in _near_deadline()]


# ------------------------------------------------------------------ formatting

def _n(x: Any) -> str:
    try:
        return f"{float(x):g}"
    except (TypeError, ValueError):
        return "?"


def format_kr(kr: Dict[str, Any], history: bool = False) -> str:
    unit = f" {kr['unit']}" if kr.get("unit") else ""
    line = (f"{kr.get('name', '?')}: {_n(kr.get('current'))}/{_n(kr.get('target'))}{unit} "
            f"({_pct(kr_progress(kr))}%, from {_n(kr.get('start_value'))}) [id={kr.get('id', '?')}]")
    pts = [h for h in kr.get("history", []) if isinstance(h, dict)] if isinstance(kr.get("history"), list) else []
    if history and pts:
        line += "\n        history: " + ", ".join(f"{h.get('date')}: {_n(h.get('value'))}" for h in pts[-5:])
    return line


def format_objective(obj: Dict[str, Any], detail: bool = True, history: bool = False) -> str:
    exp = expected(obj)
    head = (f"{obj.get('name', '?')}: {_pct(progress(obj))}% done"
            + (f", {_pct(exp)}% of the time used" if exp is not None else "")
            + f" - {pace(obj)} ({obj.get('start')} to {obj.get('end')}) [id={obj.get('id', '?')}]")
    if not detail:
        return head
    lines = [head]
    if obj.get("notes"):
        lines.append(f"    {obj['notes']}")
    lines += [f"    - {format_kr(k, history)}" for k in key_results(obj)]
    return "\n".join(lines)


def format_listing(rows: List[Dict[str, Any]], status: str, history: bool = False) -> str:
    if not rows:
        return (f"No {status} objectives." if status in ("done", "dropped")
                else "No objectives yet. Add one with add_objective.")
    label = "" if status == "all" else f" ({status})"
    return (f"{len(rows)} objective{'s' if len(rows) != 1 else ''}{label}:\n"
            + "\n".join("- " + format_objective(r, True, history) for r in rows))


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_objective":
            obj = add_objective(inp.get("name"), inp.get("period"), inp.get("start"), inp.get("end"),
                                inp.get("notes"), inp.get("key_results"))
            return "Objective added: " + format_objective(obj)
        if name == "add_key_result":
            res = add_key_result(inp.get("objective"), inp.get("name"), inp.get("target"),
                                 inp.get("start_value", 0), inp.get("unit"))
            return f"Key result added to {res['objective']['name']}: " + format_kr(res["key_result"])
        if name == "record_key_result":
            res = record_key_result(inp.get("objective"), inp.get("key_result"), inp.get("value"), inp.get("add"))
            kr, obj = res["key_result"], res["objective"]
            return (f"Recorded: {format_kr(kr)}\nObjective {obj['name']}: {_pct(progress(obj))}% done, "
                    f"{pace(obj)}.")
        if name == "get_okrs":
            status = (inp.get("status") or "active")
            if status not in ("active", "done", "dropped", "all"):
                raise ValueError("status must be active, done, dropped or all.")
            if inp.get("objective"):
                obj = _resolve(_load(), inp["objective"])
                return format_objective(obj, True, True)
            return format_listing(listing(status), status)
        if name == "update_okr":
            kr_ref = inp.get("key_result")
            res = update_okr(inp.get("objective"), inp.get("fields"), kr_ref, bool(kr_ref))
            if res["key_result"]:
                return "Key result updated: " + format_kr(res["key_result"])
            return "Objective updated: " + format_objective(res["objective"], False)
        if name == "delete_okr":
            kr_ref = inp.get("key_result")
            res = delete_okr(inp.get("objective"), kr_ref, bool(kr_ref))
            if res["key_result"]:
                return f"Deleted key result {res['key_result'].get('name')} from {res['objective'].get('name')}. This can't be undone."
            return f"Deleted objective {res['objective'].get('name')} and its key results. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_objective": "Objective not added", "add_key_result": "Key result not added",
                "record_key_result": "Not recorded", "get_okrs": "Cannot show objectives",
                "delete_okr": "Not deleted"}.get(name, "Not changed")
        return f"{verb}: {e}"
    return f"Unknown objective tool: {name}"
