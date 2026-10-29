"""
Hermes Life OS - Time Blocks (day planner)
============================================
Plan the hours of a day, not just its to-do list. A time block is a title
with a start and an end ("Deep work 09:00-10:30"); blocks on one day may not
overlap. The day plan shows the blocks in order with the free gaps between
them, where you are right now and how much of the day is planned. Free time
can be searched for ("find me 90 minutes this week"), a task can be dropped
into the first free slot, and a block can complete its task when you finish it.
Over a period, the time allocation says how many hours went to which category.

Stored in timeblocks.json as {"id", "date", "start", "end", "title",
"category", "task_id", "notes", "done"} dicts; times are "HH:MM" on one
calendar day (a block cannot run past midnight; "24:00" is allowed as an end).
Blocks are personal plans: nothing here leaves the machine and no network call
is made by this module.
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import clock

MAX_BLOCKS = 5000
MAX_PER_DAY = 40
MAX_TITLE = 80
MAX_NOTES = 160
MAX_CATEGORY = 20
DEFAULT_CATEGORY = "general"
DAY_START = 7 * 60          # the free-time search and the day plan's gaps run from 07:00 ...
DAY_END = 22 * 60           # ... to 22:00
MIN_GAP = 15                # a gap shorter than this is not worth showing
MIN_DURATION = 5
MAX_DURATION = 16 * 60
NUDGE_MINUTES = 15
MAX_SLOTS = 5
MAX_SEARCH_DAYS = 14
DATE_RANGE_DAYS = 730       # how far from today a block can be planned or recorded
MAX_ALLOCATION_DAYS = 90
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")


def _pct(x: float) -> int:
    return int(x * 100 + 0.5)


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


# ------------------------------------------------------------------ parsing

def parse_time(value: Any, what: str = "time", allow_24: bool = False) -> int:
    """Minutes since midnight for "9", "9:30", "09:30", "2pm" or "2:30 pm".
    Raises ValueError for anything else (and for 24:00 unless `allow_24`)."""
    problem = f"{what} must be a time such as 09:30 or 2:30pm."
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise ValueError(problem)
    m = _TIME_RE.match(value.strip().lower())
    if not m:
        raise ValueError(problem)
    hour, minute, suffix = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if minute > 59:
        raise ValueError(problem)
    if suffix:
        if not 1 <= hour <= 12:
            raise ValueError(problem)
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    elif hour == 24 and minute == 0 and allow_24:
        return 1440
    if hour > 23:
        raise ValueError(problem)
    return hour * 60 + minute


def fmt_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}min"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h{rest:02d}" if rest else f"{hours}h"


def _whole(value: Any, low: int, high: int, what: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a whole number from {low} to {high}.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a whole number from {low} to {high}.") from None
    if number != number or number != int(number) or not low <= number <= high:
        raise ValueError(f"{what} must be a whole number from {low} to {high}.")
    return int(number)


def _clean_title(value: Any) -> str:
    if not isinstance(value, str) or not " ".join(value.split()):
        raise ValueError("the block needs a title.")
    title = " ".join(value.split())
    if len(title) > MAX_TITLE:
        raise ValueError(f"the title can be at most {MAX_TITLE} characters.")
    return title


def _clean_category(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return DEFAULT_CATEGORY
    if not isinstance(value, str):
        raise ValueError("the category must be text.")
    text = " ".join(value.strip().lower().split())
    if len(text) > MAX_CATEGORY:
        raise ValueError(f"the category can be at most {MAX_CATEGORY} characters.")
    return text


def _clean_notes(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("notes must be text.")
    return value.strip()[:MAX_NOTES]


def parse_date(value: Any) -> str:
    """YYYY-MM-DD for a date, today, tomorrow, in 3 days or a weekday name;
    blank means today. Dates more than two years away are rejected."""
    import tasks
    day = tasks.parse_due(value) or clock.today_str()
    gap = abs((clock.parse_day(day) - clock.today()).days)
    if gap > DATE_RANGE_DAYS:
        raise ValueError(f"the date must be within {DATE_RANGE_DAYS} days of today.")
    return day


# ------------------------------------------------------------------ storage

def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_timeblocks()
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
        _storage().save_timeblocks(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def span(row: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """(start, end) in minutes of a usable block, else None (hand-edited rows)."""
    try:
        start = parse_time(row.get("start"), allow_24=False)
        end = parse_time(row.get("end"), allow_24=True)
        clock.parse_day(row.get("date"))
    except (ValueError, TypeError):
        return None
    return (start, end) if end > start else None


def _on(rows: List[Dict[str, Any]], day: str) -> List[Dict[str, Any]]:
    out = [r for r in _rows(rows) if r.get("date") == day and span(r)]
    out.sort(key=lambda r: span(r))
    return out


def _resolve(rows: List[Dict[str, Any]], ref: Any, on_date: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which block (its id or some words from its title).")
    key = ref.strip().lower()
    pool = [r for r in _rows(rows) if on_date is None or r.get("date") == on_date]
    for r in pool:
        if str(r.get("id", "")).lower() == key:
            return r
    exact = [r for r in pool if str(r.get("title", "")).lower() == key]
    hits = exact or [r for r in pool if key in str(r.get("title", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no time block matches '{ref.strip()}'. Use get_day_plan to see them.")
    options = "; ".join(f"[id={r.get('id', '?')}] {r.get('date')} {r.get('start')} {r.get('title')}"
                        for r in sorted(hits, key=lambda r: (str(r.get("date")), str(r.get("start"))))[:5])
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} blocks ({options}). Use the id or add a date.")


def _check_free(rows: List[Dict[str, Any]], day: str, start: int, end: int,
                ignore: Optional[Dict[str, Any]] = None) -> None:
    for r in _on(rows, day):
        if r is ignore:
            continue
        a, b = span(r)
        if start < b and a < end:
            raise ValueError(f"that overlaps '{r.get('title')}' ({fmt_time(a)}-{fmt_time(b)}) on {day}.")


def _resolve_task(ref: Any) -> Dict[str, Any]:
    import tasks
    return tasks._resolve(tasks._load(), ref, open_only=True)


# ------------------------------------------------------------------ operations

def add_time_block(title: Any = None, start: Any = None, end: Any = None, duration_minutes: Any = None,
                   date: Any = None, category: Any = None, task: Any = None, notes: Any = None) -> Dict[str, Any]:
    """Plans a block. Either `end` or `duration_minutes` is needed. `task` (an
    open task) links the block to it and supplies the title when none is given.
    Raises ValueError, adding nothing, for a bad value or an overlap."""
    linked = _resolve_task(task) if task not in (None, "") else None
    if title in (None, "") and linked:
        title = str(linked.get("text", ""))[:MAX_TITLE]
    clean = _clean_title(title)
    first = parse_time(start, "start")
    if end not in (None, "") and duration_minutes not in (None, ""):
        raise ValueError("give either an end time or duration_minutes, not both.")
    if end not in (None, ""):
        last = parse_time(end, "end", allow_24=True)
    elif duration_minutes not in (None, ""):
        last = first + _whole(duration_minutes, MIN_DURATION, MAX_DURATION, "duration_minutes")
        if last > 1440:
            raise ValueError("a block cannot run past midnight.")
    else:
        raise ValueError("give an end time or duration_minutes.")
    if last <= first:
        raise ValueError("the end must be after the start.")
    if not MIN_DURATION <= last - first <= MAX_DURATION:
        raise ValueError(f"a block lasts from {MIN_DURATION} minutes to {MAX_DURATION // 60} hours.")
    day = parse_date(date)
    cat = _clean_category(category)
    note = _clean_notes(notes)
    rows = _load()
    if len(rows) >= MAX_BLOCKS:
        raise ValueError(f"you already have {MAX_BLOCKS} time blocks - delete old ones first.")
    if len(_on(rows, day)) >= MAX_PER_DAY:
        raise ValueError(f"{day} already has {MAX_PER_DAY} blocks.")
    _check_free(rows, day, first, last)
    row = {"id": new_id(), "date": day, "start": fmt_time(first), "end": fmt_time(last), "title": clean,
           "category": cat, "task_id": linked.get("id") if linked else None, "notes": note, "done": False}
    rows.append(row)
    _storage().save_timeblocks(rows)
    return row


def update_time_block(ref: Any, fields: Any, on_date: Any = None) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields (title, date, start, end, category, notes, done).")
    unknown = [k for k in fields if k not in ("title", "date", "start", "end", "category", "notes", "done")]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change title, date, start, end, "
                         f"category, notes and done.")
    rows = _load()
    row = _resolve(rows, ref, parse_date(on_date) if on_date else None)
    old = span(row)
    changes: Dict[str, Any] = {}
    if "title" in fields:
        changes["title"] = _clean_title(fields["title"])
    if "category" in fields:
        changes["category"] = _clean_category(fields["category"])
    if "notes" in fields:
        changes["notes"] = _clean_notes(fields["notes"])
    if "done" in fields:
        if not isinstance(fields["done"], bool):
            raise ValueError("done must be true or false.")
        changes["done"] = fields["done"]
    if any(k in fields for k in ("date", "start", "end")):
        if "date" in fields:
            changes["date"] = parse_date(fields["date"])
        start = parse_time(fields["start"], "start") if "start" in fields else (old[0] if old else None)
        end = parse_time(fields["end"], "end", allow_24=True) if "end" in fields else (old[1] if old else None)
        if start is None or end is None:
            raise ValueError("this block has no readable start and end - give both.")
        if end <= start:
            raise ValueError("the end must be after the start.")
        if not MIN_DURATION <= end - start <= MAX_DURATION:
            raise ValueError(f"a block lasts from {MIN_DURATION} minutes to {MAX_DURATION // 60} hours.")
        day = changes.get("date", row.get("date"))
        if not isinstance(day, str):
            raise ValueError("this block has no readable date - give one.")
        _check_free(rows, day, start, end, ignore=row)
        changes["start"], changes["end"] = fmt_time(start), fmt_time(end)
    row.update(changes)
    _storage().save_timeblocks(rows)
    return row


def delete_time_block(ref: Any, on_date: Any = None) -> Dict[str, Any]:
    rows = _load()
    row = _resolve(rows, ref, parse_date(on_date) if on_date else None)
    _storage().save_timeblocks([r for r in rows if r is not row])
    return row


def finish_time_block(ref: Any, complete_task: Any = False, on_date: Any = None) -> Dict[str, Any]:
    """Marks a block done; with `complete_task`, also completes the task it is
    linked to. Returns {"block", "already", "task"} where task is the completed
    task's text, "missing" if the link points nowhere, or None."""
    if not isinstance(complete_task, bool):
        raise ValueError("complete_task must be true or false.")
    rows = _load()
    row = _resolve(rows, ref, parse_date(on_date) if on_date else None)
    already = bool(row.get("done"))
    row["done"] = True
    _storage().save_timeblocks(rows)
    task_note = None
    if complete_task and row.get("task_id"):
        import tasks
        try:
            res = tasks.complete_task(row["task_id"])
            task_note = res["task"].get("text", "")
        except ValueError:
            task_note = "missing"
    return {"block": row, "already": already, "task": task_note}


# ------------------------------------------------------------------ the day

def _gaps(blocks: List[Dict[str, Any]], low: int = DAY_START, high: int = DAY_END,
          min_len: int = MIN_GAP) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    cursor = low
    for r in blocks:
        a, b = span(r)
        if a > cursor and min(a, high) - cursor >= min_len:
            out.append((cursor, min(a, high)))
        cursor = max(cursor, b)
        if cursor >= high:
            break
    if high - cursor >= min_len:
        out.append((cursor, high))
    return out


def day_plan(day: Any = None) -> Dict[str, Any]:
    d = parse_date(day)
    blocks = _on(_load(), d)
    planned = sum(span(r)[1] - span(r)[0] for r in blocks)
    done = sum(span(r)[1] - span(r)[0] for r in blocks if r.get("done"))
    gaps = _gaps(blocks)
    return {"date": d, "blocks": blocks, "gaps": gaps, "planned": planned, "done": done,
            "free": sum(b - a for a, b in gaps)}


def _clock_minutes() -> int:
    now = clock.now()
    return now.hour * 60 + now.minute


def _where_now(plan: Dict[str, Any]) -> Optional[str]:
    if plan["date"] != clock.today_str():
        return None
    now = _clock_minutes()
    for r in plan["blocks"]:
        a, b = span(r)
        if a <= now < b:
            return f"Now: {r['title']} until {fmt_time(b)}" + (" (marked done)" if r.get("done") else "") + "."
    for r in plan["blocks"]:
        a, _ = span(r)
        if a > now and not r.get("done"):
            return f"Next: {r['title']} at {fmt_time(a)}, in {fmt_duration(a - now)}."
    return None


def format_block(r: Dict[str, Any]) -> str:
    a, b = span(r) or (0, 0)
    link = ", linked to a task" if r.get("task_id") else ""
    state = " (done)" if r.get("done") else ""
    return (f"{r.get('start')}-{r.get('end')} {r.get('title', '?')} [{r.get('category', DEFAULT_CATEGORY)}] "
            f"({fmt_duration(b - a)}){link}{state} [id={r.get('id', '?')}]")


def format_day_plan(plan: Dict[str, Any]) -> str:
    day = clock.parse_day(plan["date"]).strftime("%a")
    if not plan["blocks"]:
        return (f"Nothing planned for {day} {plan['date']}: {fmt_duration(plan['free'])} free between "
                f"{fmt_time(DAY_START)} and {fmt_time(DAY_END)}. Add a block with add_time_block.")
    head = (f"Plan for {day} {plan['date']}: {len(plan['blocks'])} block{'s' if len(plan['blocks']) != 1 else ''}, "
            f"{fmt_duration(plan['planned'])} planned, {fmt_duration(plan['done'])} done, "
            f"{fmt_duration(plan['free'])} free ({fmt_time(DAY_START)}-{fmt_time(DAY_END)}).")
    lines = [head]
    gaps = list(plan["gaps"])
    for r in plan["blocks"]:
        a, _ = span(r)
        while gaps and gaps[0][0] < a:
            g = gaps.pop(0)
            lines.append(f"  free {fmt_time(g[0])}-{fmt_time(g[1])} ({fmt_duration(g[1] - g[0])})")
        lines.append("- " + format_block(r))
    for g in gaps:
        lines.append(f"  free {fmt_time(g[0])}-{fmt_time(g[1])} ({fmt_duration(g[1] - g[0])})")
    where = _where_now(plan)
    if where:
        lines.append(where)
    return "\n".join(lines)


def find_free_time(duration_minutes: Any, date: Any = None, days: Any = 1, earliest: Any = None,
                   latest: Any = None) -> List[Dict[str, Any]]:
    """Up to five slots of the wanted length, one per free gap, soonest first,
    searched over `days` days from `date` (today by default). Today's slots
    start no earlier than the current time."""
    need = _whole(duration_minutes, MIN_DURATION, MAX_DURATION, "duration_minutes")
    count = _whole(days, 1, MAX_SEARCH_DAYS, "days")
    low = parse_time(earliest, "earliest") if earliest not in (None, "") else DAY_START
    high = parse_time(latest, "latest", allow_24=True) if latest not in (None, "") else DAY_END
    if high - low < need:
        raise ValueError("the search window is shorter than the time you asked for.")
    first = clock.parse_day(parse_date(date))
    rows = _load()
    now_min = _clock_minutes()
    out: List[Dict[str, Any]] = []
    for i in range(count):
        day = (first + timedelta(days=i)).isoformat()
        lo = low
        if day == clock.today_str():
            lo = max(lo, -(-now_min // 5) * 5)
        for a, b in _gaps(_on(rows, day), lo, high, need):
            out.append({"date": day, "start": fmt_time(a), "end": fmt_time(a + need), "gap_end": fmt_time(b)})
            if len(out) >= MAX_SLOTS:
                return out
    return out


def schedule_task(task: Any, duration_minutes: Any = 60, date: Any = None, earliest: Any = None,
                  latest: Any = None, category: Any = None) -> Dict[str, Any]:
    """Puts an open task into the first free slot: on `date` if given, else
    the next 7 days starting today."""
    linked = _resolve_task(task)
    slots = find_free_time(duration_minutes, date, 1 if date else 7, earliest, latest)
    if not slots:
        where = parse_date(date) if date else "the next 7 days"
        need = fmt_duration(_whole(duration_minutes, MIN_DURATION, MAX_DURATION, "duration_minutes"))
        raise ValueError(f"no free slot of {need} on {where}.")
    s = slots[0]
    return add_time_block(linked.get("text"), s["start"], s["end"], None, s["date"],
                          category or "task", linked.get("id"))


def allocation(days: Any = 7) -> Dict[str, Any]:
    n = _whole(days, 1, MAX_ALLOCATION_DAYS, "days")
    today = clock.today()
    start = (today - timedelta(days=n - 1)).isoformat()
    cats: Dict[str, Dict[str, int]] = {}
    blocks = 0
    for r in _rows(_load()):
        s = span(r)
        if not s or not start <= r["date"] <= today.isoformat():
            continue
        blocks += 1
        cat = str(r.get("category") or DEFAULT_CATEGORY)
        c = cats.setdefault(cat, {"planned": 0, "done": 0, "blocks": 0})
        c["planned"] += s[1] - s[0]
        c["blocks"] += 1
        if r.get("done"):
            c["done"] += s[1] - s[0]
    return {"days": n, "from": start, "to": today.isoformat(), "blocks": blocks, "categories": cats,
            "planned": sum(c["planned"] for c in cats.values()), "done": sum(c["done"] for c in cats.values())}


def format_allocation(a: Dict[str, Any]) -> str:
    if not a["blocks"]:
        return f"No time blocks in the last {a['days']} day(s)."
    pct = _pct(a["done"] / a["planned"]) if a["planned"] else 0
    lines = [f"Time blocks, {a['from']} to {a['to']}: {a['blocks']} block{'s' if a['blocks'] != 1 else ''}, "
             f"{fmt_duration(a['planned'])} planned, {fmt_duration(a['done'])} done ({pct}%)."]
    for cat, c in sorted(a["categories"].items(), key=lambda kv: (-kv[1]["planned"], kv[0])):
        share = _pct(c["planned"] / a["planned"]) if a["planned"] else 0
        done_pct = _pct(c["done"] / c["planned"]) if c["planned"] else 0
        lines.append(f"- {cat}: {fmt_duration(c['planned'])} planned ({share}% of the time), "
                     f"{fmt_duration(c['done'])} done ({done_pct}%), {c['blocks']} block(s)")
    return "\n".join(lines)


# ------------------------------------------------------------------ nudges and agenda

def nudges(max_items: int = 1) -> List[str]:
    """A block of today that starts within the next 15 minutes and is not done."""
    now = _clock_minutes()
    out = []
    for r in _on(_load(), clock.today_str()):
        a, _ = span(r)
        if not r.get("done") and 0 < a - now <= NUDGE_MINUTES:
            out.append(f"{r['title']} starts in {a - now} min ({fmt_time(a)}).")
    return out[:max_items]


def agenda_lines() -> List[str]:
    """Today's blocks that are not done, in time order, for the daily agenda."""
    return [f"{r['start']}-{r['end']} {r['title']}" for r in _on(_load(), clock.today_str()) if not r.get("done")]


# ------------------------------------------------------------------ tool entry point

def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_time_block":
            row = add_time_block(inp.get("title"), inp.get("start"), inp.get("end"), inp.get("duration_minutes"),
                                 inp.get("date"), inp.get("category"), inp.get("task"), inp.get("notes"))
            return f"Time block added on {row['date']}: " + format_block(row)
        if name == "get_day_plan":
            return format_day_plan(day_plan(inp.get("date")))
        if name == "update_time_block":
            return "Time block updated: " + format_block(update_time_block(inp.get("block"), inp.get("fields"),
                                                                           inp.get("date")))
        if name == "delete_time_block":
            row = delete_time_block(inp.get("block"), inp.get("date"))
            return f"Deleted time block {row.get('title')} ({row.get('date')} {row.get('start')}). This can't be undone."
        if name == "finish_time_block":
            res = finish_time_block(inp.get("block"), inp.get("complete_task", False), inp.get("date"))
            msg = ("Already done: " if res["already"] else "Done: ") + format_block(res["block"])
            if res["task"] == "missing":
                msg += "\nThe linked task no longer exists."
            elif res["task"] is not None:
                msg += f"\nCompleted the linked task: {res['task']}"
            return msg
        if name == "find_free_time":
            slots = find_free_time(inp.get("duration_minutes"), inp.get("date"), inp.get("days", 1),
                                   inp.get("earliest"), inp.get("latest"))
            if not slots:
                return "No free slot of that length in the search window."
            return f"{len(slots)} free slot{'s' if len(slots) != 1 else ''}:\n" + "\n".join(
                f"- {s['date']} {s['start']}-{s['end']} (the gap lasts until {s['gap_end']})" for s in slots)
        if name == "schedule_task":
            row = schedule_task(inp.get("task"), inp.get("duration_minutes", 60), inp.get("date"),
                                inp.get("earliest"), inp.get("latest"), inp.get("category"))
            return f"Scheduled on {row['date']}: " + format_block(row)
        if name == "get_time_allocation":
            return format_allocation(allocation(inp.get("days", 7)))
    except (ValueError, TypeError) as e:
        verb = {"add_time_block": "Time block not added", "get_day_plan": "Cannot show the plan",
                "find_free_time": "Cannot search for free time", "schedule_task": "Task not scheduled",
                "get_time_allocation": "Cannot show the time allocation"}.get(name, "Time block not changed")
        return f"{verb}: {e}"
    return f"Unknown time block tool: {name}"
