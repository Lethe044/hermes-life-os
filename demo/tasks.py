"""
Hermes Life OS - Tasks
========================
A small to-do list that lives next to the trackers: add a task (optionally
with a due date, priority, tags and a repeat), list what is open or overdue,
complete, edit and delete it. Until v1.42.0 the only way to remember "call the
dentist by Friday" was a reminder, which fires at a time but has no notion of
done / overdue.

Stored in tasks.json as a list of {"id", "text", "created", "due", "priority",
"tags", "repeat", "notes", "done", "done_date"} dicts. `due` is "YYYY-MM-DD" or
None; `priority` is "high" | "normal" | "low"; `repeat` is None, "daily",
"weekdays", "weekly" or "monthly". Completing a repeating task also creates
the next occurrence (due date moved forward past today, so a late completion
does not leave an already-overdue copy behind).

Due dates can be written as YYYY-MM-DD, "today", "tomorrow", "in 3 days",
"in 2 weeks" or a weekday name ("friday" = the next Friday after today).
"Today" is the user's day (clock.py, LIFE_OS_DAY_START_HOUR). No network call
is made by this module.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import clock


def _storage():
    """The storage module as it is right now (looked up on every call, so a
    reloaded storage - another profile, a test's temp HOME - is never missed)."""
    import storage
    return storage


PRIORITIES = ("high", "normal", "low")
_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
_PRIORITY_ALIASES = {"urgent": "high", "important": "high", "medium": "normal", "med": "normal",
                     "default": "normal", "none": "normal", "1": "high", "2": "normal", "3": "low"}
REPEATS = ("daily", "weekdays", "weekly", "monthly")
MAX_TEXT = 200
MAX_TAGS = 10
MAX_TAG_LEN = 30
MAX_OPEN = 1000
_WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
             "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
             "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}


def new_task_id() -> str:
    return uuid.uuid4().hex[:8]


# ------------------------------------------------------------------ parsing

def parse_due(value: Any) -> Optional[str]:
    """A due date as YYYY-MM-DD, or None for "no due date" (None / blank).
    Raises ValueError for anything not understood."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("due date must be text: YYYY-MM-DD, today, tomorrow, in 3 days or a weekday.")
    text = " ".join(value.strip().lower().split())
    if not text:
        return None
    today = clock.today()
    if text == "today":
        return today.isoformat()
    if text == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    m = re.fullmatch(r"in (\d{1,4}) (day|days|week|weeks)", text)
    if m:
        n = int(m.group(1)) * (7 if m.group(2).startswith("week") else 1)
        return (today + timedelta(days=n)).isoformat()
    word = text[5:] if text.startswith("next ") else text
    if word in _WEEKDAYS:
        ahead = (_WEEKDAYS[word] - today.weekday() - 1) % 7 + 1  # 1..7, never today
        return (today + timedelta(days=ahead)).isoformat()
    try:
        return clock.parse_day(text).isoformat()
    except ValueError:
        raise ValueError(f"I couldn't understand the due date '{value.strip()}'. Use YYYY-MM-DD, today, "
                         f"tomorrow, in 3 days or a weekday name.") from None


def parse_priority(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "normal"
    key = str(value).strip().lower()
    key = _PRIORITY_ALIASES.get(key, key)
    if key not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}.")
    return key


def parse_repeat(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    key = str(value).strip().lower()
    key = {"every day": "daily", "everyday": "daily", "every week": "weekly", "every month": "monthly",
           "weekday": "weekdays", "none": ""}.get(key, key)
    if key == "":
        return None
    if key not in REPEATS:
        raise ValueError(f"repeat must be one of: {', '.join(REPEATS)}.")
    return key


def parse_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.replace("#", " ").replace(",", " ").split()
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise ValueError("tags must be a list of words.")
    tags: List[str] = []
    for t in value:
        t = t.strip().lstrip("#").lower()
        if not t:
            continue
        if len(t) > MAX_TAG_LEN:
            raise ValueError(f"a tag can be at most {MAX_TAG_LEN} characters.")
        if t not in tags:
            tags.append(t)
    if len(tags) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags per task.")
    return tags


def _clean_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("the task needs some text.")
    text = " ".join(value.split())
    if len(text) > MAX_TEXT:
        raise ValueError(f"the task text can be at most {MAX_TEXT} characters.")
    return text


def next_due(current_due: Optional[str], repeat: str) -> str:
    """The next due date for a repeating task completed now: one step after the
    current due date (or after today if it has none), moved forward until it is
    after today."""
    today = clock.today()
    base = clock.parse_day(current_due) if current_due else today

    if repeat == "monthly":
        # measured from the original day each time, so Jan 31 gives Feb 28, Mar 31, ...
        k = 1
        while clock.add_months(base, k) <= today and k < 4000:
            k += 1
        return clock.add_months(base, k).isoformat()

    def step(d: date) -> date:
        if repeat == "daily":
            return d + timedelta(days=1)
        if repeat == "weekly":
            return d + timedelta(days=7)
        d = d + timedelta(days=1)  # weekdays
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    nxt = step(base)
    guard = 0
    while nxt <= today and guard < 4000:
        nxt = step(nxt)
        guard += 1
    return nxt.isoformat()


# ------------------------------------------------------------------ storage

def _load() -> List[Dict[str, Any]]:
    """The task list with ids guaranteed (hand-edited rows without one get one)."""
    tasks = _storage().load_tasks()
    if not isinstance(tasks, list):
        return []
    seen = {t.get("id") for t in tasks if isinstance(t, dict) and t.get("id")}
    changed = False
    for t in tasks:
        if isinstance(t, dict) and not t.get("id"):
            new = new_task_id()
            while new in seen:
                new = new_task_id()
            seen.add(new)
            t["id"] = new
            changed = True
    if changed:
        _storage().save_tasks(tasks)
    return tasks


def _rows(tasks: List[Any]) -> List[Dict[str, Any]]:
    return [t for t in tasks if isinstance(t, dict)]


def _resolve(tasks: List[Dict[str, Any]], ref: Any, open_only: bool = False,
             prefer_open: bool = False) -> Dict[str, Any]:
    """The task a user means by an id or some words from its text. An exact id
    always wins. With `prefer_open`, words that match both finished and open
    tasks mean the open ones (a repeating task leaves a finished copy behind).
    Raises ValueError (with the candidates) if none or several match."""
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which task (its id or some words from it).")
    key = ref.strip().lower()
    pool = [t for t in _rows(tasks) if not (open_only and t.get("done"))]
    for t in pool:
        if str(t.get("id", "")).lower() == key:
            return t
    hits = [t for t in pool if key in str(t.get("text", "")).lower()]
    if prefer_open:
        hits = [t for t in hits if not t.get("done")] or hits
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no {'open ' if open_only else ''}task matches '{ref.strip()}'. Use list_tasks to see ids.")
    options = "; ".join(f"[id={t['id']}] {t.get('text', '')}" for t in hits[:5])
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} tasks ({options}). Use the id.")


# ------------------------------------------------------------------ operations

def add_task(text: Any, due: Any = None, priority: Any = None, tags: Any = None,
             repeat: Any = None, notes: Any = None) -> Dict[str, Any]:
    """Creates a task. Raises ValueError, adding nothing, for blank/too long
    text, an unreadable due date, a bad priority/repeat/tags, or when 1000
    tasks are already open."""
    clean = _clean_text(text)
    due_s = parse_due(due)
    prio = parse_priority(priority)
    rep = parse_repeat(repeat)
    tag_list = parse_tags(tags)
    if rep and not due_s:
        due_s = clock.today_str()  # a repeating task needs an anchor day
    tasks = _load()
    if sum(1 for t in _rows(tasks) if not t.get("done")) >= MAX_OPEN:
        raise ValueError(f"you already have {MAX_OPEN} open tasks - complete or delete some first.")
    task = {"id": new_task_id(), "text": clean, "created": clock.today_str(), "due": due_s,
            "priority": prio, "tags": tag_list, "repeat": rep,
            "notes": str(notes).strip() if isinstance(notes, str) else "",
            "done": False, "done_date": None}
    tasks.append(task)
    _storage().save_tasks(tasks)
    return task


def complete_task(ref: Any) -> Dict[str, Any]:
    """Marks a task done. Returns {"task": done row, "next": new row or None,
    "already": bool}. Raises ValueError if the task is unknown or ambiguous."""
    tasks = _load()
    task = _resolve(tasks, ref, prefer_open=True)
    if task.get("done"):
        return {"task": task, "next": None, "already": True}
    task["done"] = True
    task["done_date"] = clock.today_str()
    follow = None
    if task.get("repeat") in REPEATS:
        follow = dict(task)
        follow.update({"id": new_task_id(), "created": clock.today_str(),
                       "due": next_due(task.get("due"), task["repeat"]), "done": False, "done_date": None})
        tasks.append(follow)
    _storage().save_tasks(tasks)
    return {"task": task, "next": follow, "already": False}


def update_task(ref: Any, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Edits a task. `fields` may hold text, due ("" clears), priority, tags,
    repeat ("" clears), notes and done (false reopens a finished task).
    Everything is validated before anything changes."""
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change - give at least one of text, due, priority, tags, repeat, "
                         "notes or done.")
    allowed = {"text", "due", "priority", "tags", "repeat", "notes", "done"}
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError(f"cannot change {', '.join(unknown)}. Editable: {', '.join(sorted(allowed))}.")
    changes: Dict[str, Any] = {}
    if "text" in fields:
        changes["text"] = _clean_text(fields["text"])
    if "due" in fields:
        changes["due"] = parse_due(fields["due"])
    if "priority" in fields:
        changes["priority"] = parse_priority(fields["priority"])
    if "tags" in fields:
        changes["tags"] = parse_tags(fields["tags"])
    if "repeat" in fields:
        changes["repeat"] = parse_repeat(fields["repeat"])
    if "notes" in fields:
        if not isinstance(fields["notes"], str):
            raise ValueError("notes must be text.")
        changes["notes"] = fields["notes"].strip()
    if "done" in fields:
        if fields["done"] is not False:
            raise ValueError("done can only be set to false (to reopen); use complete_task to finish a task.")
        changes["done"] = False
        changes["done_date"] = None
    tasks = _load()
    task = _resolve(tasks, ref)
    if changes.get("repeat") and not (changes.get("due", task.get("due"))):
        changes["due"] = clock.today_str()
    task.update(changes)
    _storage().save_tasks(tasks)
    return task


def delete_task(ref: Any) -> Dict[str, Any]:
    tasks = _load()
    task = _resolve(tasks, ref)
    tasks.remove(task)
    _storage().save_tasks(tasks)
    return task


def clear_done(older_than_days: int = 0) -> int:
    """Deletes finished tasks (those finished at least `older_than_days` days
    ago; 0 = all). Returns how many were removed."""
    cutoff = clock.days_ago_str(max(0, int(older_than_days)))
    tasks = _load()
    keep = [t for t in tasks
            if not (isinstance(t, dict) and t.get("done") and str(t.get("done_date") or "") <= cutoff)]
    removed = len(tasks) - len(keep)
    if removed:
        _storage().save_tasks(keep)
    return removed


def _sort_key(t: Dict[str, Any]):
    due = t.get("due")
    return (due is None, due or "", _PRIORITY_ORDER.get(t.get("priority"), 1), str(t.get("created", "")))


def list_tasks(status: str = "open", tag: Optional[str] = None, due_within: Optional[int] = None,
               limit: int = 30) -> List[Dict[str, Any]]:
    """Tasks, most urgent first (overdue, then by due date, then priority).
    `status` is open / done / all, `tag` filters, `due_within` keeps open tasks
    due in that many days or earlier (overdue included). Raises ValueError for
    an unknown status."""
    status = (status or "open").strip().lower()
    if status not in ("open", "done", "all"):
        raise ValueError("status must be open, done or all.")
    tasks = _rows(_load())
    if status == "open":
        tasks = [t for t in tasks if not t.get("done")]
    elif status == "done":
        tasks = [t for t in tasks if t.get("done")]
    if tag:
        key = str(tag).strip().lstrip("#").lower()
        tasks = [t for t in tasks if key in (t.get("tags") or [])]
    if due_within is not None:
        limit_day = (clock.today() + timedelta(days=max(0, int(due_within)))).isoformat()
        tasks = [t for t in tasks if not t.get("done") and t.get("due") and t["due"] <= limit_day]
    if status == "done":
        tasks.sort(key=lambda t: str(t.get("done_date") or ""), reverse=True)
    else:
        tasks.sort(key=_sort_key)
    return tasks[:max(1, min(int(limit), 200))]


def due_label(task: Dict[str, Any]) -> str:
    due = task.get("due")
    if not due:
        return ""
    try:
        days = (clock.parse_day(due) - clock.today()).days
    except ValueError:
        return f"due {due}"
    if task.get("done"):
        return f"due {due}"
    if days < 0:
        return f"due {due}, overdue by {-days} day{'s' if days != -1 else ''}"
    if days == 0:
        return f"due {due} (today)"
    if days == 1:
        return f"due {due} (tomorrow)"
    if days <= 6:
        return f"due {due} (in {days} days)"
    return f"due {due}"


def format_task(task: Dict[str, Any]) -> str:
    box = "[x]" if task.get("done") else "[ ]"
    prio = f" !{task['priority']}" if task.get("priority") in ("high", "low") else ""
    bits = [f"[id={task['id']}] {box}{prio} {task.get('text', '')}"]
    label = due_label(task)
    if label:
        bits.append(f"- {label}")
    if task.get("done") and task.get("done_date"):
        bits.append(f"- done {task['done_date']}")
    if task.get("repeat"):
        bits.append(f"- repeats {task['repeat']}")
    if task.get("tags"):
        bits.append(" ".join("#" + t for t in task["tags"]))
    return " ".join(bits)


def format_task_list(tasks: List[Dict[str, Any]], status: str = "open") -> str:
    if not tasks:
        return {"open": "No open tasks.", "done": "No finished tasks.", "all": "No tasks yet."}.get(status, "No tasks.")
    head = f"{len(tasks)} {status if status != 'all' else ''} task{'s' if len(tasks) != 1 else ''}".replace("  ", " ")
    return head + ":\n" + "\n".join(format_task(t) for t in tasks)


def summary() -> Dict[str, Any]:
    today = clock.today_str()
    week = (clock.today() + timedelta(days=7)).isoformat()
    tasks = _rows(_load())
    open_t = [t for t in tasks if not t.get("done")]
    overdue = sorted((t for t in open_t if t.get("due") and t["due"] < today), key=_sort_key)
    return {
        "open": len(open_t),
        "overdue": overdue,
        "due_today": [t for t in open_t if t.get("due") == today],
        "due_this_week": [t for t in open_t if t.get("due") and today < t["due"] <= week],
        "no_due_date": sum(1 for t in open_t if not t.get("due")),
        "done_today": sum(1 for t in tasks if t.get("done") and t.get("done_date") == today),
        "done_last_7_days": sum(1 for t in tasks if t.get("done") and
                                str(t.get("done_date") or "") >= clock.days_ago_str(6)),
    }


def format_summary(s: Dict[str, Any]) -> str:
    if not s["open"] and not s["done_last_7_days"]:
        return "No tasks yet. Add one with add_task."
    lines = [f"{s['open']} open task(s): {len(s['overdue'])} overdue, {len(s['due_today'])} due today, "
             f"{len(s['due_this_week'])} due in the next 7 days, {s['no_due_date']} without a due date.",
             f"Finished: {s['done_today']} today, {s['done_last_7_days']} in the last 7 days."]
    for t in s["overdue"][:3]:
        lines.append("Overdue: " + format_task(t))
    return "\n".join(lines)


def overdue_nudge() -> Optional[str]:
    over = summary()["overdue"]
    if not over:
        return None
    names = ", ".join(f"'{t['text']}'" for t in over[:2])
    more = f" and {len(over) - 2} more" if len(over) > 2 else ""
    return f"{len(over)} task{'s' if len(over) != 1 else ''} overdue: {names}{more}."


# ------------------------------------------------------------------ tool entry point

def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_task":
            t = add_task(inp.get("text"), inp.get("due"), inp.get("priority"), inp.get("tags"),
                         inp.get("repeat"), inp.get("notes"))
            return "Task added: " + format_task(t)
        if name == "list_tasks":
            status = inp.get("status") or "open"
            rows = list_tasks(status, inp.get("tag"), inp.get("due_within"), inp.get("limit", 30))
            return format_task_list(rows, status.strip().lower())
        if name == "complete_task":
            r = complete_task(inp.get("task"))
            if r["already"]:
                return f"Already done: {format_task(r['task'])}"
            msg = f"Done: {r['task']['text']}"
            if r["next"]:
                msg += f"\nNext {r['next']['repeat']} occurrence: {format_task(r['next'])}"
            return msg
        if name == "update_task":
            return "Task updated: " + format_task(update_task(inp.get("task"), inp.get("fields")))
        if name == "delete_task":
            return f"Deleted task: {delete_task(inp.get('task'))['text']}. This can't be undone."
        if name == "get_task_summary":
            return format_summary(summary())
        if name == "clear_done_tasks":
            n = clear_done(inp.get("older_than_days", 0))
            return f"Removed {n} finished task(s)." if n else "No finished tasks to remove."
    except (ValueError, TypeError) as e:
        verb = {"add_task": "Task not added", "list_tasks": "Cannot list tasks",
                "get_task_summary": "Cannot summarize tasks"}.get(name, "Task not changed")
        return f"{verb}: {e}"
    return f"Unknown task tool: {name}"
