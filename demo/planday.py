"""
Hermes Life OS - Plan My Day
==============================
Turns the day's open work into a schedule. Hermes takes the day's priorities
first, then overdue and due tasks (high priority first), and fits each one into
a free gap of the day plan using the task's `minutes` estimate (30 by default).
By default it only shows the proposal; with apply=true the proposed slots are
saved as time blocks linked to the tasks. Nothing is stored by this module
itself and no network call is made.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import clock

DEFAULT_MINUTES = 30
BREAK = 5
MAX_TASKS = 10
DEFAULT_TASKS = 5
_RANK = {"high": 0, "normal": 1, "low": 2}


def _candidates(day: str) -> List[Dict[str, Any]]:
    """Open tasks to place on `day`: priorities first, then overdue or due that
    day, then undated high priority ones. Each as {"task", "why"}."""
    import priorities
    import tasks
    import timeblocks
    rows = [t for t in tasks._rows(tasks._load()) if not t.get("done")]
    by_id = {t.get("id"): t for t in rows}
    blocks = timeblocks.day_plan(day)["blocks"]
    planned = {b.get("task_id") for b in blocks if b.get("task_id")}
    titles = {str(b.get("title", "")).lower() for b in blocks}
    out: List[Dict[str, Any]] = []
    seen = set()

    def take(t: Dict[str, Any], why: str) -> None:
        if (t.get("id") is not None and (t.get("id") in seen or t.get("id") in planned)) \
                or str(t.get("text", "")).lower() in titles:
            return
        seen.add(t.get("id"))
        titles.add(str(t.get("text", "")).lower())
        out.append({"task": t, "why": why})

    for p in priorities.day_rows(day):
        if p.get("done"):
            continue
        t = by_id.get(p.get("task_id"))
        if t is not None:
            take(t, "priority")
        else:
            take({"id": None, "text": p.get("text", "?"), "priority": "high", "minutes": None}, "priority")
    rest = [t for t in rows if t.get("due") and str(t["due"]) <= day]
    rest.sort(key=lambda t: (str(t["due"]) == day, _RANK.get(t.get("priority"), 1), str(t["due"])))
    for t in rest:
        take(t, "overdue" if str(t["due"]) < day else "due")
    for t in sorted((t for t in rows if not t.get("due") and t.get("priority") == "high"), key=lambda t: str(t.get("created"))):
        take(t, "high priority")
    return out


def _gaps(day: str) -> List[List[int]]:
    import timeblocks
    gaps = [[a, b] for a, b in timeblocks.day_plan(day)["gaps"]]
    if day == clock.today_str():
        now = -(-timeblocks._clock_minutes() // 5) * 5
        gaps = [[max(a, now), b] for a, b in gaps if b - max(a, now) >= timeblocks.MIN_GAP]
    return gaps


def plan(date: Any = None, max_tasks: Any = None, default_minutes: Any = None) -> Dict[str, Any]:
    """The proposal for `date`: {"date", "placed", "unplaced", "free_after"}.
    `placed` items are {"text", "task_id", "start", "end", "minutes", "why"}."""
    import timeblocks
    day = timeblocks.parse_date(date)
    limit = DEFAULT_TASKS if max_tasks in (None, "") else max_tasks
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_TASKS:
        raise ValueError(f"max_tasks must be a whole number from 1 to {MAX_TASKS}.")
    base = DEFAULT_MINUTES if default_minutes in (None, "") else default_minutes
    if isinstance(base, bool) or not isinstance(base, int) or not timeblocks.MIN_DURATION <= base <= 240:
        raise ValueError(f"default_minutes must be a whole number from {timeblocks.MIN_DURATION} to 240.")
    gaps = _gaps(day)
    placed: List[Dict[str, Any]] = []
    unplaced: List[Dict[str, Any]] = []
    for c in _candidates(day)[:limit]:
        t = c["task"]
        need = t.get("minutes") if isinstance(t.get("minutes"), int) and not isinstance(t.get("minutes"), bool) else base
        spot: Tuple[int, int] = (-1, -1)
        for g in gaps:
            if g[1] - g[0] >= need:
                spot = (g[0], g[0] + need)
                g[0] = spot[1] + BREAK
                break
        if spot[0] < 0:
            unplaced.append({"text": t.get("text", "?"), "minutes": need, "why": c["why"]})
            continue
        placed.append({"text": t.get("text", "?"), "task_id": t.get("id"), "start": timeblocks.fmt_time(spot[0]),
                       "end": timeblocks.fmt_time(spot[1]), "minutes": need, "why": c["why"]})
    free = sum(max(0, b - a) for a, b in gaps)
    return {"date": day, "placed": placed, "unplaced": unplaced, "free_after": free}


def apply_plan(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Saves the placed items as time blocks; returns the blocks created."""
    import timeblocks
    made = []
    for p in result["placed"]:
        made.append(timeblocks.add_time_block(p["text"][:timeblocks.MAX_TITLE], p["start"], p["end"], None,
                                              result["date"], "task", p.get("task_id")))
    return made


def format_plan(result: Dict[str, Any], applied: bool) -> str:
    import timeblocks
    day = result["date"]
    if not result["placed"] and not result["unplaced"]:
        return (f"Nothing to schedule for {day}: no open priorities, no overdue or due tasks and no high priority "
                f"tasks without a date. Add tasks with add_task.")
    head = f"Plan for {day}" + (" (saved as time blocks)" if applied else " (proposal, nothing saved yet)") + ":"
    lines = [head]
    for p in result["placed"]:
        lines.append(f"- {p['start']}-{p['end']} {p['text']} ({p['why']}, {p['minutes']} min)")
    if result["unplaced"]:
        lines.append("Did not fit:")
        lines += [f"- {u['text']} ({u['why']}, {u['minutes']} min)" for u in result["unplaced"]]
    lines.append(f"Free time left: {timeblocks.fmt_duration(result['free_after'])}.")
    if not applied and result["placed"]:
        lines.append("Run plan_my_day again with apply=true to save these as time blocks.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name != "plan_my_day":
        return f"Unknown planning tool: {name}"
    try:
        result = plan(inp.get("date"), inp.get("max_tasks"), inp.get("default_minutes"))
        apply = inp.get("apply")
        if apply not in (None, True, False):
            raise ValueError("apply must be true or false.")
        if apply and result["placed"]:
            apply_plan(result)
        return format_plan(result, bool(apply) and bool(result["placed"]))
    except (ValueError, TypeError) as e:
        return f"Cannot plan the day: {e}"
