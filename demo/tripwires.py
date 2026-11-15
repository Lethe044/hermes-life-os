"""
Hermes Life OS - Tripwires
============================
Rules you set while you are thinking clearly, that speak up when you are not:
"if sleep stays below 6 hours for 3 days, tell me to protect tonight", "if
more than 5 tasks are overdue, tell me to stop adding new ones". A tripwire
watches one metric (anything Hermes logs, or a live planner count such as
overdue tasks or inbox size), a direction (above or below), a threshold and
how many days in a row it has to hold. When it trips, the message you wrote
shows in the agenda and in the nudges.

Stored in tripwires.json as {"id", "name", "metric", "op", "threshold",
"days", "message", "created"} dicts. Evaluation is deterministic and local;
no network call is made by this module.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import clock
import metricseries as ms
import plannerkit as kit

OPS = ("above", "below")
MAX_ITEMS = 30
MAX_NAME = 60
MAX_MESSAGE = 160
MAX_DAYS = 30
STREAK_LOOKBACK = 60


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_tripwires(), lambda r: _storage().save_tripwires(r))


def _valid(r: Any) -> bool:
    return (isinstance(r, dict) and isinstance(r.get("name"), str) and bool(r["name"].strip()) and r.get("metric") in ms.METRICS
            and r.get("op") in OPS and isinstance(r.get("threshold"), (int, float))
            and not isinstance(r.get("threshold"), bool) and isinstance(r.get("days"), int) and r["days"] >= 1)


def _breach(r: Dict[str, Any], value: float) -> bool:
    return value > r["threshold"] if r["op"] == "above" else value < r["threshold"]


def evaluate(r: Dict[str, Any], daily: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """{"state": "tripped" | "ok" | "no data", "run": days in a row it has held,
    "latest": newest value}. For live counts the current value decides (run is
    1 or 0). For logged metrics the run counts back from today (or from
    yesterday while today has no reading yet)."""
    if r["metric"] in ms.STATE:
        val = ms.state_value(r["metric"])
        if val is None:
            return {"state": "no data", "run": 0, "latest": None}
        hit = _breach(r, val)
        return {"state": "tripped" if hit else "ok", "run": 1 if hit else 0, "latest": float(val)}
    daily = daily if daily is not None else ms.load_daily()
    today = clock.today_str()
    anchor = today if isinstance(daily.get(today, {}).get(r["metric"]), (int, float)) else ms.day_minus(today, 1)
    run = 0
    latest = None
    for i in range(STREAK_LOOKBACK):
        day = ms.day_minus(anchor, i)
        v = daily.get(day, {}).get(r["metric"]) if isinstance(daily.get(day), dict) else None
        if not isinstance(v, (int, float)):
            break
        if latest is None:
            latest = float(v)
        if not _breach(r, v):
            break
        run += 1
    if latest is None:
        return {"state": "no data", "run": 0, "latest": None}
    return {"state": "tripped" if run >= r["days"] else "ok", "run": run, "latest": latest}


def add_tripwire(name: Any, metric: Any, op: Any, threshold: Any, days: Any = None, message: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(name, "name", MAX_NAME)
    key = ms.check_metric(metric)
    word = op.strip().lower() if isinstance(op, str) else ""
    if word not in OPS:
        raise ValueError("the condition must be 'above' or 'below'.")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold):
        raise ValueError("the threshold must be a number.")
    if key in ms.STATE:
        length = 1
    elif days in (None, ""):
        length = 3
    elif isinstance(days, bool) or not isinstance(days, (int, float)) or days != int(days) or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {MAX_DAYS}.")
    else:
        length = int(days)
    rows = _load()
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"you already have {MAX_ITEMS} tripwires.")
    if any(str(r.get("name", "")).lower() == clean.lower() for r in kit.only_dicts(rows)):
        raise ValueError(f"a tripwire called '{clean}' already exists.")
    default = f"{key.replace('_', ' ')} has been {word} {threshold:g}" + ("" if key in ms.STATE else f" for {length} days in a row")
    item = {"id": kit.new_id(), "name": clean, "metric": key, "op": word, "threshold": threshold, "days": length,
            "message": kit.clean_text(message, "message", MAX_MESSAGE, required=False) or default,
            "created": clock.today_str()}
    rows.append(item)
    _storage().save_tripwires(rows)
    return item


def delete_tripwire(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "tripwire", "name", "get_tripwires")
    _storage().save_tripwires([r for r in rows if r is not item])
    return item


def listing() -> List[Dict[str, Any]]:
    return sorted((r for r in _load() if _valid(r)), key=lambda r: r["name"].lower())


def tripped() -> List[Dict[str, Any]]:
    """Tripped tripwires as {"wire", "result"}, the longest run first."""
    daily = ms.load_daily()
    out = []
    for r in listing():
        res = evaluate(r, daily)
        if res["state"] == "tripped":
            out.append({"wire": r, "result": res})
    return sorted(out, key=lambda x: -x["result"]["run"])


def nudges(max_items: int = 1) -> List[str]:
    return [f"Tripwire '{t['wire']['name']}': {t['wire']['message'].rstrip('.')}." for t in tripped()][:max_items]


def agenda_lines() -> List[str]:
    return [f"{t['wire']['name']}: {t['wire']['message']}" for t in tripped()]


def format_rule(r: Dict[str, Any]) -> str:
    when = "now" if r["metric"] in ms.STATE else f"for {kit.plural(r['days'], 'day')} in a row"
    return f"{r['name']}: {r['metric']} {r['op']} {r['threshold']:g} {when}"


def format_all() -> str:
    rows = listing()
    if not rows:
        return ("No tripwires yet. Add one with add_tripwire, for example metric='sleep', condition='below', "
                "threshold=6, days=3.")
    daily = ms.load_daily()
    lines = []
    trip = 0
    for r in rows:
        res = evaluate(r, daily)
        if res["state"] == "tripped":
            trip += 1
            status = f"TRIPPED (held {kit.plural(res['run'], 'day')}): {r['message']}"
        elif res["state"] == "no data":
            status = "no data yet"
        else:
            status = "ok" + (f" (latest {res['latest']:g})" if res["latest"] is not None else "")
        lines.append(f"- {format_rule(r)} -> {status} [id={r['id']}]")
    head = f"{kit.plural(len(rows), 'tripwire')}, {trip} tripped:" if trip else f"{kit.plural(len(rows), 'tripwire')}, none tripped:"
    return head + "\n" + "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_tripwire":
            r = add_tripwire(inp.get("name"), inp.get("metric"), inp.get("condition"), inp.get("threshold"),
                             inp.get("days"), inp.get("message"))
            return f"Tripwire set: {format_rule(r)}. [id={r['id']}]"
        if name == "get_tripwires":
            return format_all()
        if name == "delete_tripwire":
            return f"Deleted tripwire '{delete_tripwire(inp.get('tripwire'))['name']}'."
    except (ValueError, TypeError) as e:
        verb = {"add_tripwire": "Tripwire not set", "get_tripwires": "Cannot show tripwires"}.get(name, "Tripwire not deleted")
        return f"{verb}: {e}"
    return f"Unknown tripwire tool: {name}"
