"""
Hermes Life OS - Daily Priorities ("Big 3")
=============================================
Pick the few things that make today a good day: at most three per day. A
priority is free text or an open task (completing the priority then completes
the task too). Unfinished priorities can be carried over to today, and the
agenda, the nudges and the closing summary show what is still open.

Stored in priorities.json as {"id", "date", "text", "task_id", "done",
"done_on"} dicts. Entries older than 90 days are dropped when a new one is
added. No network call is made by this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import clock
import plannerkit as kit

MAX_PER_DAY = 3
MAX_TEXT = 100
KEEP_DAYS = 90
NUDGE_AFTER_HOUR = 15


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_priorities(), lambda r: _storage().save_priorities(r))


def _day(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return clock.today_str()
    import tasks
    try:
        got = tasks.parse_due(value)
    except ValueError:
        raise ValueError("I couldn't understand the date. Use YYYY-MM-DD, today, tomorrow or a weekday.") from None
    return got or clock.today_str()


def _on(rows: List[Dict[str, Any]], day: str) -> List[Dict[str, Any]]:
    return [r for r in kit.only_dicts(rows) if r.get("date") == day]


def _linked_task(ref: Any) -> Dict[str, Any]:
    import tasks
    return tasks._resolve(tasks._load(), ref, open_only=True)


# ------------------------------------------------------------------ operations

def add_priority(text: Any = None, task: Any = None, date: Any = None) -> Dict[str, Any]:
    """One of the day's priorities. Give `text`, an open `task`, or both (the
    text then wins as the label). Raises ValueError, adding nothing, when the
    day already has three, the same text is already there or nothing is given."""
    day = _day(date)
    linked = _linked_task(task) if task not in (None, "") else None
    if text in (None, "") and linked is None:
        raise ValueError("say what the priority is (text) or which open task (task).")
    label = kit.clean_text(text if text not in (None, "") else linked.get("text"), "priority", MAX_TEXT)
    rows = _load()
    today_rows = _on(rows, day)
    if len(today_rows) >= MAX_PER_DAY:
        raise ValueError(f"{day} already has {MAX_PER_DAY} priorities. Finish or delete one first.")
    if any(str(r.get("text", "")).lower() == label.lower() for r in today_rows):
        raise ValueError(f"'{label}' is already a priority for {day}.")
    if linked and any(r.get("task_id") == linked.get("id") for r in today_rows):
        raise ValueError(f"that task is already a priority for {day}.")
    cutoff = (clock.today() - timedelta(days=KEEP_DAYS)).isoformat()
    rows = [r for r in rows if not (isinstance(r, dict) and str(r.get("date", "9999")) < cutoff)]
    item = {"id": kit.new_id(), "date": day, "text": label, "task_id": linked.get("id") if linked else None,
            "done": False, "done_on": None}
    rows.append(item)
    _storage().save_priorities(rows)
    return item


def complete_priority(ref: Any) -> Dict[str, Any]:
    """Marks a priority done (and its linked task, when it is still open)."""
    rows = _load()
    item = kit.resolve(rows, ref, "priority", "text", "get_priorities")
    if item.get("done"):
        return {"item": item, "already": True, "task_done": False}
    item["done"] = True
    item["done_on"] = clock.today_str()
    _storage().save_priorities(rows)
    task_done = False
    if item.get("task_id"):
        try:
            import tasks
            res = tasks.complete_task(item["task_id"])
            task_done = not res["already"]
        except ValueError:
            task_done = False
    return {"item": item, "already": False, "task_done": task_done}


def delete_priority(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "priority", "text", "get_priorities")
    _storage().save_priorities([r for r in rows if r is not item])
    return item


def carry_over(source: Any = None, date: Any = None) -> Dict[str, Any]:
    """Copies the unfinished priorities of `source` (yesterday by default) to
    `date` (today by default), as many as fit. Returns {"moved", "skipped"}."""
    target = _day(date)
    src = _day(source) if source not in (None, "") else (clock.parse_day(target) - timedelta(days=1)).isoformat()
    if src == target:
        raise ValueError("the source day and the target day are the same.")
    rows = _load()
    moved: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for r in _on(rows, src):
        if r.get("done"):
            continue
        have = _on(rows, target)
        if len(have) >= MAX_PER_DAY:
            skipped.append(str(r.get("text", "?")))
            continue
        if any(str(h.get("text", "")).lower() == str(r.get("text", "")).lower() for h in have):
            continue
        item = {"id": kit.new_id(), "date": target, "text": r.get("text", ""), "task_id": r.get("task_id"),
                "done": False, "done_on": None}
        rows.append(item)
        moved.append(item)
    if moved:
        _storage().save_priorities(rows)
    return {"moved": moved, "skipped": skipped, "source": src, "target": target}


def open_today() -> List[Dict[str, Any]]:
    return [r for r in _on(_load(), clock.today_str()) if not r.get("done")]


def day_rows(day: Any = None) -> List[Dict[str, Any]]:
    return _on(_load(), _day(day))


def streak() -> int:
    """Days in a row (ending today or yesterday) on which every priority that
    was set got done."""
    rows = kit.only_dicts(_load())
    days = sorted({r.get("date") for r in rows if isinstance(r.get("date"), str)}, reverse=True)
    by_day = {d: [r for r in rows if r.get("date") == d] for d in days}
    today = clock.today()
    count, cursor = 0, today
    if clock.today_str() not in by_day or not all(r.get("done") for r in by_day[clock.today_str()]):
        cursor = today - timedelta(days=1)
    while True:
        got = by_day.get(cursor.isoformat())
        if not got or not all(r.get("done") for r in got):
            break
        count += 1
        cursor -= timedelta(days=1)
    return count


def nudges(max_items: int = 1) -> List[str]:
    if clock.now().hour < NUDGE_AFTER_HOUR:
        return []
    left = open_today()
    if not left:
        return []
    names = ", ".join(f"'{r.get('text')}'" for r in left[:2])
    more = f" and {len(left) - 2} more" if len(left) > 2 else ""
    return [f"{kit.plural(len(left), 'priority')} still open today: {names}{more}."][:max_items]


def agenda_lines() -> List[str]:
    return [f"{r.get('text')}" for r in open_today()]


# ------------------------------------------------------------------ formatting

def format_priority(r: Dict[str, Any]) -> str:
    box = "[x]" if r.get("done") else "[ ]"
    link = " (task)" if r.get("task_id") else ""
    return f"{box} {r.get('text', '?')}{link} [id={r.get('id', '?')}]"


def format_day(rows: List[Dict[str, Any]], day: str) -> str:
    if not rows:
        return f"No priorities for {day}. Pick up to {MAX_PER_DAY} with add_priority."
    done = sum(1 for r in rows if r.get("done"))
    lines = [f"Priorities for {day} ({done}/{len(rows)} done):"] + [f"- {format_priority(r)}" for r in rows]
    if done == len(rows):
        lines.append("All done. Nicely finished.")
    run = streak()
    if run >= 2:
        lines.append(f"Streak: {run} days in a row with every priority done.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_priority":
            r = add_priority(inp.get("text"), inp.get("task"), inp.get("date"))
            left = MAX_PER_DAY - len(_on(_load(), r["date"]))
            return f"Priority added for {r['date']}: {format_priority(r)}. {kit.plural(left, 'slot')} left."
        if name == "get_priorities":
            day = _day(inp.get("date"))
            return format_day(_on(_load(), day), day)
        if name == "complete_priority":
            res = complete_priority(inp.get("priority"))
            if res["already"]:
                return f"Already done: {res['item']['text']}"
            tail = " The linked task is done too." if res["task_done"] else ""
            return f"Priority done: {res['item']['text']}.{tail}"
        if name == "carry_over_priorities":
            res = carry_over(inp.get("from_date"), inp.get("date"))
            if not res["moved"] and not res["skipped"]:
                return f"Nothing to carry over from {res['source']}."
            text = f"Carried {kit.plural(len(res['moved']), 'priority')} over from {res['source']} to {res['target']}."
            if res["skipped"]:
                text += f" No room for: {', '.join(res['skipped'])}."
            return text
        if name == "delete_priority":
            return f"Deleted priority {delete_priority(inp.get('priority'))['text']}."
    except (ValueError, TypeError) as e:
        verb = {"add_priority": "Priority not added", "get_priorities": "Cannot show priorities",
                "complete_priority": "Priority not completed", "carry_over_priorities": "Nothing carried over"}.get(
            name, "Priority not deleted")
        return f"{verb}: {e}"
    return f"Unknown priority tool: {name}"
