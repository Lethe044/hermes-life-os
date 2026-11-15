"""
Hermes Life OS - Life Timeline
================================
One chronological view of what actually happened, pulled from everything
Hermes keeps: tasks and priorities you finished, time blocks you completed,
books and shows you started or finished, trips, weekly reviews, life wheel
check-ins, decisions logged or reviewed, things you received, experiments
started or concluded and a one-line summary of the health readings logged each
day. It reads only; nothing is stored and no network call is made.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import clock
import plannerkit as kit

DEFAULT_DAYS = 7
MAX_DAYS = 90
MAX_LINES = 120
KINDS = ("tasks", "priorities", "blocks", "library", "trips", "reviews", "wheel", "decisions", "waiting",
         "experiments", "health")

Event = Tuple[str, str, str]  # (date, kind, text)


def _rows(loader: str) -> List[Dict[str, Any]]:
    import storage
    got = getattr(storage, loader)()
    return kit.only_dicts(got)


def _ok(day: Any, first: str, last: str) -> bool:
    return isinstance(day, str) and first <= day <= last and _readable(day)


def _readable(day: str) -> bool:
    try:
        clock.parse_day(day)
        return True
    except (ValueError, TypeError):
        return False


def _tasks(first: str, last: str) -> List[Event]:
    return [(r["done_date"], "tasks", f"Finished task: {r.get('text', '?')}") for r in _rows("load_tasks")
            if r.get("done") and _ok(r.get("done_date"), first, last)]


def _priorities(first: str, last: str) -> List[Event]:
    return [(r["done_on"], "priorities", f"Top priority done: {r.get('text', '?')}") for r in _rows("load_priorities")
            if r.get("done") and _ok(r.get("done_on"), first, last)]


def _blocks(first: str, last: str) -> List[Event]:
    return [(r["date"], "blocks", f"Time block done: {r.get('title', '?')} ({r.get('start')}-{r.get('end')})")
            for r in _rows("load_timeblocks") if r.get("done") and _ok(r.get("date"), first, last)]


def _library(first: str, last: str) -> List[Event]:
    out: List[Event] = []
    for r in _rows("load_library"):
        label = f"{r.get('kind', 'item')} '{r.get('title', '?')}'"
        if _ok(r.get("finished"), first, last):
            stars = f" ({r['rating']}/5)" if isinstance(r.get("rating"), int) else ""
            out.append((r["finished"], "library", f"Finished {label}{stars}"))
        if _ok(r.get("started"), first, last) and r.get("started") != r.get("finished"):
            out.append((r["started"], "library", f"Started {label}"))
    return out


def _trips(first: str, last: str) -> List[Event]:
    out: List[Event] = []
    for r in _rows("load_trips"):
        name = r.get("name", "?")
        if _ok(r.get("start"), first, last):
            out.append((r["start"], "trips", f"Trip began: {name}" + (f" ({r['destination']})" if r.get("destination") else "")))
        if _ok(r.get("end"), first, last) and r.get("end") != r.get("start"):
            out.append((r["end"], "trips", f"Trip ended: {name}"))
    return out


def _reviews(first: str, last: str) -> List[Event]:
    return [(r["saved"], "reviews", f"Weekly review saved for the week of {r.get('week', '?')}")
            for r in _rows("load_reviews") if _ok(r.get("saved"), first, last)]


def _wheel(first: str, last: str) -> List[Event]:
    import wheel
    out: List[Event] = []
    for r in _rows("load_wheel"):
        if _ok(r.get("date"), first, last) and wheel._valid(r):
            out.append((r["date"], "wheel", f"Life wheel check-in, average {wheel.average(r):.1f}/10"))
    return out


def _decisions(first: str, last: str) -> List[Event]:
    out: List[Event] = []
    for r in _rows("load_decisions"):
        text = r.get("title") or r.get("decision") or "?"
        if _ok(r.get("created"), first, last):
            out.append((r["created"], "decisions", f"Decision logged: {text}"))
        if _ok(r.get("reviewed_on"), first, last):
            out.append((r["reviewed_on"], "decisions", f"Decision reviewed: {text}"))
    return out


def _waiting(first: str, last: str) -> List[Event]:
    return [(r["done_on"], "waiting", f"Received: {r.get('what', '?')}" + (f" from {r['who']}" if r.get("who") else ""))
            for r in _rows("load_waiting") if r.get("done") and _ok(r.get("done_on"), first, last)]


def _experiments(first: str, last: str) -> List[Event]:
    out: List[Event] = []
    for r in _rows("load_experiments"):
        if _ok(r.get("start"), first, last):
            out.append((r["start"], "experiments", f"Experiment started: {r.get('name', '?')} on {r.get('metric', '?')}"))
        if _ok(r.get("concluded"), first, last):
            verdict = (r.get("result") or {}).get("verdict", "?") if isinstance(r.get("result"), dict) else "?"
            out.append((r["concluded"], "experiments", f"Experiment concluded: {r.get('name', '?')} ({verdict})"))
    return out


def _health(first: str, last: str) -> List[Event]:
    import metricseries as ms
    try:
        daily = ms.load_daily()
    except Exception:  # noqa: BLE001
        return []
    out: List[Event] = []
    for day, row in daily.items():
        if not _ok(day, first, last) or not isinstance(row, dict):
            continue
        bits = [f"{m.replace('_', ' ')} {row[m]:.1f}" for m in ms.LOGGED if isinstance(row.get(m), (int, float))]
        if bits:
            out.append((day, "health", "Logged: " + ", ".join(bits[:5])))
    return out


SOURCES: Dict[str, Callable[[str, str], List[Event]]] = {
    "tasks": _tasks, "priorities": _priorities, "blocks": _blocks, "library": _library, "trips": _trips,
    "reviews": _reviews, "wheel": _wheel, "decisions": _decisions, "waiting": _waiting,
    "experiments": _experiments, "health": _health,
}


def _kinds(value: Any) -> Optional[List[str]]:
    if value in (None, "", []):
        return None
    items = value.split(",") if isinstance(value, str) else value
    if not isinstance(items, list):
        raise ValueError(f"kinds must be some of: {', '.join(KINDS)}.")
    got = [str(x).strip().lower() for x in items if str(x).strip()]
    bad = [k for k in got if k not in KINDS]
    if bad:
        raise ValueError(f"unknown kind {', '.join(bad)}. Choose from: {', '.join(KINDS)}.")
    return got


def events(days: Any = None, kinds: Any = None) -> Dict[str, Any]:
    """{"first", "last", "events": [(date, kind, text)] newest day first,
    "skipped": [kinds whose data could not be read]}."""
    span = DEFAULT_DAYS if days in (None, "") else days
    if isinstance(span, bool) or not isinstance(span, int) or not 1 <= span <= MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {MAX_DAYS}.")
    chosen = _kinds(kinds) or list(KINDS)
    last = clock.today_str()
    first = (clock.today() - timedelta(days=span - 1)).isoformat()
    found: List[Event] = []
    skipped: List[str] = []
    for kind in chosen:
        try:
            found.extend(SOURCES[kind](first, last))
        except Exception:  # noqa: BLE001
            skipped.append(kind)
    order = {k: i for i, k in enumerate(KINDS)}
    found.sort(key=lambda e: (e[0], -order[e[1]], e[2]), reverse=True)
    return {"first": first, "last": last, "events": found, "skipped": skipped}


def format_timeline(res: Dict[str, Any]) -> str:
    ev = res["events"]
    span = f"{res['first']} to {res['last']}"
    if not ev:
        return f"Nothing on your timeline for {span}. Finish a task, log how you feel or save a weekly review and it will show up here."
    lines = [f"Your timeline, {span} ({kit.plural(len(ev), 'event')}):"]
    day = None
    for date, _kind, text in ev[:MAX_LINES]:
        if date != day:
            day = date
            lines.append(f"{clock.parse_day(date).strftime('%a %d %b')} ({kit.when_text((clock.parse_day(date) - clock.today()).days)})")
        lines.append(f"- {text}")
    if len(ev) > MAX_LINES:
        lines.append(f"...and {len(ev) - MAX_LINES} older events. Use a shorter window or kinds to narrow it.")
    if res["skipped"]:
        lines.append(f"Could not read: {', '.join(res['skipped'])}.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name != "get_life_timeline":
        return f"Unknown timeline tool: {name}"
    try:
        return format_timeline(events(inp.get("days"), inp.get("kinds")))
    except (ValueError, TypeError) as e:
        return f"Cannot build the timeline: {e}"
