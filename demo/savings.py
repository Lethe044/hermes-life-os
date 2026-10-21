"""
Hermes Life OS - Savings goals
================================
Money you are putting aside for something: "emergency fund 5000", "holiday
2400 by 2027-06-01". Add money (or take some out), see the percentage, what is
left, how fast you have really been saving and, with a deadline, whether that
pace gets you there and what you would need to put aside per month.

Stored in savings.json as a list of {"id", "name", "target", "saved",
"deadline", "created", "completed", "notes", "history"} dicts; `history` is a
list of {"date", "amount", "note"} and `saved` is always its sum (a starting
balance is recorded as its first entry). Amounts have no currency; they are
whatever you use. No network call is made by this module.

Pace is the net amount saved (a starting balance does not count) over the last
90 days (or since the first entry, if that is more recent) per day; the estimate of the finishing day is
remaining / pace and needs at least two entries on different days.
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock

MAX_GOALS = 100
MAX_HISTORY = 1000
MAX_NAME = 60
MAX_NOTE = 120
MAX_AMOUNT = 1_000_000_000_000
PACE_WINDOW_DAYS = 90
NUDGE_DAYS = 14


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def money(value: Any, label: str = "amount", allow_zero: bool = False) -> float:
    """A money amount rounded to cents. Raises ValueError for a non-number,
    NaN/infinity or a value that is too big."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.") from None
    if not math.isfinite(number) or abs(number) > MAX_AMOUNT:
        raise ValueError(f"{label} is not a sensible amount.")
    number = round(number, 2)
    if number == 0 and not allow_zero:
        raise ValueError(f"{label} cannot be zero.")
    return number


def fmt(amount: float) -> str:
    """12 -> '12', 12.5 -> '12.50'."""
    return f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"


def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_savings()
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
        _storage().save_savings(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def _resolve(rows: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which savings goal (its id or some words from its name).")
    key = ref.strip().lower()
    pool = _rows(rows)
    for r in pool:
        if str(r.get("id", "")).lower() == key or str(r.get("name", "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no savings goal matches '{ref.strip()}'. Use get_savings to see them.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} goals ({'; '.join(r['name'] for r in hits[:5])}). "
                     f"Use the full name or the id.")


def _parse_deadline(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return clock.parse_day(value).isoformat()


def _saved(goal: Dict[str, Any]) -> float:
    total = sum(h.get("amount", 0) for h in goal.get("history") or []
                if isinstance(h, dict) and isinstance(h.get("amount"), (int, float)))
    return round(total, 2)


def _sync(goal: Dict[str, Any]) -> None:
    goal["saved"] = _saved(goal)
    reached = goal["saved"] >= goal["target"]
    if reached and not goal.get("completed"):
        goal["completed"] = clock.today_str()
    elif not reached:
        goal["completed"] = None


# ------------------------------------------------------------------ operations

def add_goal(name: Any, target: Any, deadline: Any = None, saved: Any = None, notes: Any = None) -> Dict[str, Any]:
    if not isinstance(name, str) or not " ".join(name.split()):
        raise ValueError("the goal needs a name.")
    clean = " ".join(name.split())
    if len(clean) > MAX_NAME:
        raise ValueError(f"the name can be at most {MAX_NAME} characters.")
    tgt = money(target, "target")
    if tgt <= 0:
        raise ValueError("target must be more than zero.")
    due = _parse_deadline(deadline)
    start = money(saved, "starting amount", allow_zero=True) if saved is not None else 0.0
    if start < 0:
        raise ValueError("the starting amount cannot be negative.")
    rows = _load()
    if any(str(r.get("name", "")).lower() == clean.lower() for r in _rows(rows)):
        raise ValueError(f"there is already a goal called '{clean}'.")
    if len(rows) >= MAX_GOALS:
        raise ValueError(f"you already have {MAX_GOALS} savings goals.")
    today = clock.today_str()
    goal = {"id": new_id(), "name": clean, "target": tgt, "saved": 0.0, "deadline": due, "created": today,
            "completed": None, "notes": str(notes).strip()[:MAX_NOTE] if isinstance(notes, str) else "",
            "history": [{"date": today, "amount": start, "note": "starting balance", "start": True}]
            if start else []}
    _sync(goal)
    rows.append(goal)
    _storage().save_savings(rows)
    return goal


def contribute(ref: Any, amount: Any, note: Any = None, date: Optional[str] = None) -> Dict[str, Any]:
    """Adds (or, if negative, takes out) money. Returns {"goal", "delta", "newly_reached"}.
    Raises ValueError, changing nothing, for an unknown goal, zero, a
    withdrawal bigger than what is saved, or a bad date."""
    value = money(amount)
    day = clock.resolve_entry_date(date)
    rows = _load()
    goal = _resolve(rows, ref)
    if len(goal.get("history") or []) >= MAX_HISTORY:
        raise ValueError(f"this goal already has {MAX_HISTORY} entries.")
    if _saved(goal) + value < 0:
        raise ValueError(f"you only have {fmt(_saved(goal))} saved for {goal['name']}, "
                         f"so {fmt(-value)} cannot be taken out.")
    was_done = bool(goal.get("completed"))
    entry = {"date": day, "amount": value}
    if isinstance(note, str) and note.strip():
        entry["note"] = note.strip()[:MAX_NOTE]
    goal.setdefault("history", []).append(entry)
    goal["history"].sort(key=lambda h: str(h.get("date", "")))
    _sync(goal)
    _storage().save_savings(rows)
    return {"goal": goal, "delta": value, "newly_reached": bool(goal.get("completed")) and not was_done}


def update_goal(ref: Any, fields: Any) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields (name, target, deadline, notes).")
    unknown = [k for k in fields if k not in ("name", "target", "deadline", "notes")]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change name, target, deadline "
                         f"and notes (add money with contribute_to_savings).")
    rows = _load()
    goal = _resolve(rows, ref)
    changes: Dict[str, Any] = {}
    if "name" in fields:
        n = fields["name"]
        if not isinstance(n, str) or not " ".join(n.split()):
            raise ValueError("the goal needs a name.")
        n = " ".join(n.split())
        if len(n) > MAX_NAME:
            raise ValueError(f"the name can be at most {MAX_NAME} characters.")
        if any(r is not goal and str(r.get("name", "")).lower() == n.lower() for r in _rows(rows)):
            raise ValueError(f"there is already a goal called '{n}'.")
        changes["name"] = n
    if "target" in fields:
        t = money(fields["target"], "target")
        if t <= 0:
            raise ValueError("target must be more than zero.")
        changes["target"] = t
    if "deadline" in fields:
        changes["deadline"] = _parse_deadline(fields["deadline"])
    if "notes" in fields:
        if not isinstance(fields["notes"], str):
            raise ValueError("notes must be text.")
        changes["notes"] = fields["notes"].strip()[:MAX_NOTE]
    goal.update(changes)
    _sync(goal)
    _storage().save_savings(rows)
    return goal


def delete_goal(ref: Any) -> Dict[str, Any]:
    rows = _load()
    goal = _resolve(rows, ref)
    _storage().save_savings([r for r in rows if r is not goal])
    return goal


def goals() -> List[Dict[str, Any]]:
    return _rows(_load())


# ------------------------------------------------------------------ analysis

def progress(goal: Dict[str, Any]) -> Dict[str, Any]:
    """{"saved", "target", "percent", "remaining", "reached", "pace_per_day",
    "eta" (date or None), "days_left" (or None), "needed_per_month" (or None),
    "status"}; status is reached | overdue | on_track | behind | no_deadline |
    no_pace."""
    today = clock.today()
    saved = _saved(goal)
    target = float(goal.get("target") or 0)
    remaining = round(max(0.0, target - saved), 2)
    out: Dict[str, Any] = {"saved": saved, "target": target, "remaining": remaining,
                           "percent": round(100 * saved / target, 1) if target > 0 else 0.0,
                           "reached": target > 0 and saved >= target, "pace_per_day": None, "eta": None,
                           "days_left": None, "needed_per_month": None, "status": "no_pace"}
    hist = [h for h in goal.get("history") or [] if isinstance(h, dict) and not h.get("start")
            and isinstance(h.get("amount"), (int, float)) and isinstance(h.get("date"), str)]
    days = sorted({h["date"] for h in hist})
    if len(days) >= 2:
        window_start = max(clock.parse_day(days[0]), today - timedelta(days=PACE_WINDOW_DAYS))
        span = max(1, (today - window_start).days)
        net = sum(h["amount"] for h in hist if h["date"] >= window_start.isoformat())
        raw_pace = net / span
        out["pace_per_day"] = round(raw_pace, 4)
        if not out["reached"] and raw_pace > 0:  # the unrounded pace, so 150.0 days is not 151
            out["eta"] = (today + timedelta(days=math.ceil(round(remaining / raw_pace, 6)))).isoformat()
    due = goal.get("deadline")
    if due:
        try:
            left = (clock.parse_day(due) - today).days
            out["days_left"] = left
            if left > 0 and not out["reached"]:
                out["needed_per_month"] = round(remaining / (left / 30.4375), 2)
        except ValueError:
            due = None
    if out["reached"]:
        out["status"] = "reached"
    elif due and out["days_left"] is not None and out["days_left"] < 0:
        out["status"] = "overdue"
    elif due and out["eta"] and out["eta"] <= due:
        out["status"] = "on_track"
    elif due and out["days_left"] is not None:
        out["status"] = "behind"
    elif out["eta"]:
        out["status"] = "no_deadline"
    return out


def nudges(max_items: int = 1) -> List[str]:
    """Unreached goals whose deadline is within two weeks (or has passed
    within the last week), the closest deadline first."""
    out = []
    for g in goals():
        if g.get("completed") or not g.get("deadline"):
            continue
        p = progress(g)
        left = p["days_left"]
        if left is None or left > NUDGE_DAYS or left < -7:
            continue
        when = f"{left} day{'s' if left != 1 else ''} left" if left >= 0 else f"{-left} day(s) past its deadline"
        out.append((left, f"Savings goal '{g['name']}' is {p['percent']:g}% there with {when}: "
                          f"{fmt(p['remaining'])} to go."))
    out.sort()
    return [m for _, m in out[:max_items]]


# ------------------------------------------------------------------ formatting

_STATUS_TEXT = {"reached": "goal reached", "overdue": "deadline passed", "on_track": "on track for the deadline",
                "behind": "behind the pace needed for the deadline", "no_deadline": "no deadline set",
                "no_pace": "not enough savings history for a pace yet"}


def format_goal(goal: Dict[str, Any], detail: bool = False) -> str:
    p = progress(goal)
    line = (f"{goal['name']}: {fmt(p['saved'])} of {fmt(p['target'])} ({p['percent']:g}%)"
            f"{'' if p['reached'] else ', ' + fmt(p['remaining']) + ' to go'} [id={goal.get('id', '?')}]")
    if goal.get("deadline"):
        line += f", deadline {goal['deadline']}"
        if p["days_left"] is not None and p["days_left"] >= 0 and not p["reached"]:
            line += f" ({p['days_left']} days)"
    if not detail:
        return line
    lines = [line, f"Status: {_STATUS_TEXT[p['status']]}."]
    if p["pace_per_day"] is not None:
        lines.append(f"Pace: {fmt(round(p['pace_per_day'] * 30.4375, 2))} per month"
                     f"{' (not moving forward)' if p['pace_per_day'] <= 0 else ''}.")
    if p["eta"]:
        lines.append(f"At this pace you reach it on {p['eta']}.")
    if p["needed_per_month"] is not None:
        lines.append(f"To make the deadline put aside {fmt(p['needed_per_month'])} per month.")
    if goal.get("completed"):
        lines.append(f"Reached on {goal['completed']}.")
    recent = list(reversed((goal.get("history") or [])[-5:]))
    if recent:
        lines.append("Recent: " + "; ".join(f"{h['date']} {'+' if h['amount'] > 0 else ''}{fmt(h['amount'])}"
                                            + (f" ({h['note']})" if h.get("note") else "") for h in recent))
    return "\n".join(lines)


def format_all(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No savings goals yet. Start one with add_savings_goal."
    total_saved = sum(_saved(g) for g in rows)
    total_target = sum(float(g.get("target") or 0) for g in rows)
    ordered = sorted(rows, key=lambda g: (bool(g.get("completed")), g.get("deadline") or "9999", g.get("name", "")))
    return (f"{len(rows)} savings goal{'s' if len(rows) != 1 else ''} - {fmt(total_saved)} saved of "
            f"{fmt(total_target)}:\n" + "\n".join(f"- {format_goal(g)}" for g in ordered))


def run_tool(name: str, inp: Dict[str, Any], log_date: Optional[str] = None, **_ctx: Any) -> str:
    try:
        if name == "add_savings_goal":
            g = add_goal(inp.get("name"), inp.get("target"), inp.get("deadline"), inp.get("saved"), inp.get("notes"))
            return "Savings goal added: " + format_goal(g)
        if name == "contribute_to_savings":
            r = contribute(inp.get("goal"), inp.get("amount"), inp.get("note"), inp.get("date"))
            verb = f"Added {fmt(r['delta'])} to savings." if r["delta"] > 0 else f"Took {fmt(-r['delta'])} out of savings."
            msg = f"{verb} " + format_goal(r["goal"])
            if r["newly_reached"]:
                msg += "\nGoal reached - well done!"
            return msg
        if name == "get_savings":
            if inp.get("goal"):
                return format_goal(_resolve(_load(), inp.get("goal")), detail=True)
            return format_all(goals())
        if name == "update_savings_goal":
            return "Savings goal updated: " + format_goal(update_goal(inp.get("goal"), inp.get("fields")))
        if name == "delete_savings_goal":
            return f"Deleted savings goal {delete_goal(inp.get('goal'))['name']}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_savings_goal": "Goal not added", "contribute_to_savings": "Not recorded",
                "get_savings": "Cannot show savings"}.get(name, "Goal not changed")
        return f"{verb}: {e}"
    return f"Unknown savings tool: {name}"
