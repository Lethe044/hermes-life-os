"""
Hermes Life OS - Workload Forecast
====================================
Looks ahead at the next days and answers "can I actually do all this?". For
each day Hermes adds up the minutes of the open tasks due then (30 minutes
when a task has no estimate; overdue tasks count against today; tasks that
already have a time block are skipped because the block holds their time)
(scaled by how long your finished tasks really took, once the focus log has enough data) and compares that with the free time left in the day plan, capped at eight
hours of focused work. Days are marked clear, ok, tight or overloaded, and
for overloaded days Hermes proposes which lower priority tasks to move to the
next day with room. Forecasting only reads. check_capacity asks whether a new piece of work fits before a
deadline, and rebalance_workload proposes (or with apply=true makes) the moves of
lower priority tasks to days with room; high priority tasks are never moved. No
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


def _minutes(t: Dict[str, Any], factor: float = 1.0) -> int:
    m = t.get("minutes")
    base = m if isinstance(m, int) and not isinstance(m, bool) and m > 0 else DEFAULT_MINUTES
    return max(1, round(base * factor))


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


def forecast(days: Any = None, calibrate: Any = None) -> Dict[str, Any]:
    """{"days": [{"date", "load", "free", "status", "tasks": [...]}],
    "moves": [{"task", "minutes", "from", "to"}]}."""
    import tasks
    import timeblocks
    span = DEFAULT_DAYS if days in (None, "") else days
    if isinstance(span, bool) or not isinstance(span, int) or not 1 <= span <= MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {MAX_DAYS}.")
    if calibrate not in (None, True, False):
        raise ValueError("calibrate must be true or false.")
    import estimates
    factor = estimates.calibration_factor() if calibrate is not False else None
    f = factor or 1.0
    today = clock.today()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(span)]
    open_rows = [t for t in tasks._rows(tasks._load()) if not t.get("done") and isinstance(t.get("due"), str)]
    out: List[Dict[str, Any]] = []
    for day in dates:
        blocks = timeblocks.day_plan(day)["blocks"]
        held = {b.get("task_id") for b in blocks if b.get("task_id")}
        due = [t for t in open_rows if (t["due"] == day or (day == dates[0] and t["due"] < day)) and t.get("id") not in held]
        load = sum(_minutes(t, f) for t in due)
        free = _free(day)
        out.append({"date": day, "load": load, "free": free, "status": _label(load, free), "tasks": due})
    return {"days": out, "moves": _moves(out, f), "factor": factor}


def _moves(rows: List[Dict[str, Any]], factor: float = 1.0) -> List[Dict[str, Any]]:
    """Greedy proposals: from each overloaded day, the lowest priority tasks
    that are due that day (not overdue ones, never high priority ones) go to the next day with room."""
    room = {r["date"]: r["free"] - r["load"] for r in rows}
    moves: List[Dict[str, Any]] = []
    for i, r in enumerate(rows):
        over = r["load"] - r["free"]
        if over <= 0:
            continue
        movable = sorted((t for t in r["tasks"] if t["due"] == r["date"] and t.get("priority") != "high"),
                         key=lambda t: (_RANK.get(t.get("priority"), 1), -_minutes(t, factor)))
        for t in movable:
            if over <= 0:
                break
            need = _minutes(t, factor)
            target = next((x["date"] for x in rows[i + 1:] if room[x["date"]] >= need), None)
            if target is None:
                continue
            room[target] -= need
            room[r["date"]] += need
            over -= need
            moves.append({"task": t.get("text", "?"), "task_id": t.get("id"), "minutes": need, "from": r["date"],
                          "to": target})
    return moves


def _hm(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if h and m else f"{h}h" if h else f"{m}m"


def format_forecast(res: Dict[str, Any]) -> str:
    rows = res["days"]
    if not any(r["load"] for r in rows):
        return (f"Nothing is due in the next {kit.plural(len(rows), 'day')}, so there is no workload to forecast. "
                f"Add due dates and minutes with add_task.")
    scale = res.get("factor")
    lines = [f"Workload for the next {kit.plural(len(rows), 'day')} (task minutes due vs free time, max 8h a day):"]
    for r in rows:
        day = clock.parse_day(r["date"]).strftime("%a %d %b")
        mark = {"overloaded": "OVER", "tight": "tight", "ok": "ok", "clear": "-"}[r["status"]]
        if r["load"]:
            lines.append(f"- {day}: {_hm(r['load'])} of work, {_hm(r['free'])} free [{mark}]")
        else:
            lines.append(f"- {day}: nothing due, {_hm(r['free'])} free")
    if scale and abs(scale - 1.0) >= 0.05:
        lines.append(f"Estimates are scaled by {scale:.2f} because that is how long your finished tasks really took "
                     f"(see get_estimate_accuracy).")
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


def check_capacity(minutes: Any, by: Any, calibrate: Any = None) -> Dict[str, Any]:
    """Whether `minutes` of new work fits before the deadline `by`: {"need",
    "by", "room", "fits", "plan": [(date, minutes)]}. Room is the free time of
    each day minus the work already due, filled from the earliest day."""
    import tasks
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes != int(minutes) or not 5 <= minutes <= 2400:
        raise ValueError("minutes must be a whole number from 5 to 2400.")
    if by in (None, ""):
        raise ValueError("say the deadline (by): YYYY-MM-DD, today, tomorrow or a weekday.")
    deadline = tasks.parse_due(by)
    span = (clock.parse_day(deadline) - clock.today()).days + 1
    if span < 1:
        raise ValueError("the deadline is in the past.")
    if span > MAX_DAYS:
        raise ValueError(f"the deadline can be at most {MAX_DAYS} days away.")
    res = forecast(span, calibrate)
    factor = res.get("factor") or 1.0
    need = max(1, round(int(minutes) * factor))
    left, plan = need, []
    room = 0
    for r in res["days"]:
        free = max(0, r["free"] - r["load"])
        room += free
        take = min(left, free)
        if take > 0:
            plan.append((r["date"], take))
            left -= take
    return {"need": need, "asked": int(minutes), "by": deadline, "room": room, "fits": left == 0, "plan": plan,
            "factor": res.get("factor")}


def format_capacity(c: Dict[str, Any]) -> str:
    scale = f" ({_hm(c['asked'])} scaled by {c['factor']:.2f} from your estimate history)" if c["factor"] and abs(c["factor"] - 1) >= 0.05 else ""
    if c["fits"]:
        parts = ", ".join(f"{_hm(m)} on {clock.parse_day(d).strftime('%a %d %b')}" for d, m in c["plan"])
        return f"Yes, {_hm(c['need'])} fits before {c['by']}{scale}. Room is there on: {parts}."
    short = c["need"] - c["room"]
    return (f"No. {_hm(c['need'])} does not fit before {c['by']}{scale}: only {_hm(c['room'])} of room is left after the "
            f"work already due, {_hm(short)} short. Move the deadline, drop something or shorten the estimate.")


def rebalance(days: Any = None, apply: Any = None) -> Dict[str, Any]:
    """The moves of the forecast; with apply=true the tasks get their new due
    dates. High priority tasks are never moved."""
    if apply not in (None, True, False):
        raise ValueError("apply must be true or false.")
    import tasks
    res = forecast(days)
    done: List[Dict[str, Any]] = []
    if apply:
        for m in res["moves"]:
            if m.get("task_id") is None:
                continue
            tasks.update_task(m["task_id"], {"due": m["to"]})
            done.append(m)
    return {"moves": res["moves"], "applied": done, "overloaded": [r["date"] for r in res["days"] if r["status"] == "overloaded"]}


def format_rebalance(r: Dict[str, Any], applied: bool) -> str:
    if not r["overloaded"]:
        return "No day is overloaded, so there is nothing to rebalance."
    if not r["moves"]:
        return ("Some days are overloaded but no lower priority task can move to a day with room. High priority tasks "
                "are never moved: drop something, shorten an estimate or extend the window.")
    head = "Moved:" if applied else "Proposed moves (nothing changed yet):"
    lines = [head] + [f"- '{m['task']}' ({m['minutes']} min) from {m['from']} to {m['to']}" for m in r["moves"]]
    if not applied:
        lines.append("Run rebalance_workload again with apply=true to change the due dates.")
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
    if name not in ("get_workload_forecast", "check_capacity", "rebalance_workload"):
        return f"Unknown workload tool: {name}"
    try:
        if name == "check_capacity":
            return format_capacity(check_capacity(inp.get("minutes"), inp.get("by"), inp.get("calibrate")))
        if name == "rebalance_workload":
            res = rebalance(inp.get("days"), inp.get("apply"))
            return format_rebalance(res, bool(inp.get("apply")))
        return format_forecast(forecast(inp.get("days"), inp.get("calibrate")))
    except (ValueError, TypeError) as e:
        return {"check_capacity": "Cannot check capacity", "rebalance_workload": "Cannot rebalance"}.get(
            name, "Cannot forecast the workload") + f": {e}"
