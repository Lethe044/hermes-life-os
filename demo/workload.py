"""
Hermes Life OS - Workload Forecast
====================================
Looks ahead at the next days and answers "can I actually do all this?". For
each day Hermes adds up the minutes of the open tasks due then (30 minutes
when a task has no estimate; overdue tasks count against today; tasks that
already have a time block are skipped because the block holds their time)
and compares that with the free time left in the day plan, capped at eight
hours of focused work. Days are marked clear, ok, tight or overloaded, and
for overloaded days Hermes proposes which lower priority tasks to move to the
next day with room. Nothing is changed by this module: it only reads, and no
network call is made.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import clock
import plannerkit as kit

DEFAULT_MINUTES = 30
DAILY_CAP = 8 * 60
DEFAULT_DAYS = 14
MAX_DAYS = 30
TIGHT_AT = 0.7
_RANK = {"low": 0, "normal": 1, "high": 2}


def _minutes(t: Dict[str, Any]) -> int:
    m = t.get("minutes")
    return m if isinstance(m, int) and not isinstance(m, bool) and m > 0 else DEFAULT_MINUTES


def _free(day: str) -> int:
    import planday
    import timeblocks
    if day == clock.today_str():
        free = sum(max(0, b - a) for a, b in planday._gaps(day))
    else:
        free = timeblocks.day_plan(day)["free"]
    return min(free, DAILY_CAP)


def _label(load: int, free: int) -> str:
    if load == 0:
        return "clear"
    if load > free:
        return "overloaded"
    return "tight" if load > free * TIGHT_AT else "ok"


def forecast(days: Any = None) -> Dict[str, Any]:
    """{"days": [{"date", "load", "free", "status", "tasks": [...]}],
    "moves": [{"task", "minutes", "from", "to"}]}."""
    import tasks
    import timeblocks
    span = DEFAULT_DAYS if days in (None, "") else days
    if isinstance(span, bool) or not isinstance(span, int) or not 1 <= span <= MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {MAX_DAYS}.")
    today = clock.today()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(span)]
    open_rows = [t for t in tasks._rows(tasks._load()) if not t.get("done") and isinstance(t.get("due"), str)]
    out: List[Dict[str, Any]] = []
    for day in dates:
        blocks = timeblocks.day_plan(day)["blocks"]
        held = {b.get("task_id") for b in blocks if b.get("task_id")}
        due = [t for t in open_rows if (t["due"] == day or (day == dates[0] and t["due"] < day)) and t.get("id") not in held]
        load = sum(_minutes(t) for t in due)
        free = _free(day)
        out.append({"date": day, "load": load, "free": free, "status": _label(load, free), "tasks": due})
    return {"days": out, "moves": _moves(out)}


def _moves(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Greedy proposals: from each overloaded day, the lowest priority tasks
    that are due that day (not overdue ones) go to the next day with room."""
    room = {r["date"]: r["free"] - r["load"] for r in rows}
    moves: List[Dict[str, Any]] = []
    for i, r in enumerate(rows):
        over = r["load"] - r["free"]
        if over <= 0:
            continue
        movable = sorted((t for t in r["tasks"] if t["due"] == r["date"]),
                         key=lambda t: (_RANK.get(t.get("priority"), 1), -_minutes(t)))
        for t in movable:
            if over <= 0:
                break
            need = _minutes(t)
            target = next((x["date"] for x in rows[i + 1:] if room[x["date"]] >= need), None)
            if target is None:
                continue
            room[target] -= need
            room[r["date"]] += need
            over -= need
            moves.append({"task": t.get("text", "?"), "minutes": need, "from": r["date"], "to": target})
    return moves


def _hm(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if h and m else f"{h}h" if h else f"{m}m"


def format_forecast(res: Dict[str, Any]) -> str:
    rows = res["days"]
    if not any(r["load"] for r in rows):
        return (f"Nothing is due in the next {kit.plural(len(rows), 'day')}, so there is no workload to forecast. "
                f"Add due dates and minutes with add_task.")
    lines = [f"Workload for the next {kit.plural(len(rows), 'day')} (task minutes due vs free time, max 8h a day):"]
    for r in rows:
        day = clock.parse_day(r["date"]).strftime("%a %d %b")
        mark = {"overloaded": "OVER", "tight": "tight", "ok": "ok", "clear": "-"}[r["status"]]
        if r["load"]:
            lines.append(f"- {day}: {_hm(r['load'])} of work, {_hm(r['free'])} free [{mark}]")
        else:
            lines.append(f"- {day}: nothing due, {_hm(r['free'])} free")
    over = [r for r in rows if r["status"] == "overloaded"]
    if not over:
        lines.append("No day is overloaded.")
    else:
        lines.append(f"{kit.plural(len(over), 'day')} overloaded: " + ", ".join(clock.parse_day(r["date"]).strftime("%a") for r in over) + ".")
        if res["moves"]:
            lines.append("Suggested moves:")
            lines += [f"- move '{m['task']}' ({m['minutes']} min) from {m['from']} to {m['to']}" for m in res["moves"][:8]]
            lines.append("Apply one with update_task and a new due date.")
        else:
            lines.append("No later day in this window has room. Drop something, shorten an estimate or extend the window.")
    return "\n".join(lines)


def _worst_soon() -> List[str]:
    try:
        res = forecast(2)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r, word in zip(res["days"], ("Today", "Tomorrow")):
        if r["status"] == "overloaded":
            out.append(f"{word} is overloaded: {_hm(r['load'])} of work due and {_hm(r['free'])} free. "
                       f"See get_workload_forecast for what to move.")
    return out


def nudges(max_items: int = 1) -> List[str]:
    return _worst_soon()[:max_items]


def agenda_lines() -> List[str]:
    return _worst_soon()[:1]


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name != "get_workload_forecast":
        return f"Unknown workload tool: {name}"
    try:
        return format_forecast(forecast(inp.get("days")))
    except (ValueError, TypeError) as e:
        return f"Cannot forecast the workload: {e}"
