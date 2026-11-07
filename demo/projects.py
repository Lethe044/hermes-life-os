"""
Hermes Life OS - Projects
===========================
A project is an outcome that takes more than one task: "launch the website",
"plan the wedding". Every project owns a tag; the tasks that carry the tag
belong to it. Hermes shows progress (done of all tasks), the next action, and
flags projects that are stuck (active but with no open task) or past their due
date. `add_project_task` adds a task already tagged for the project.

Stored in projects.json as {"id", "name", "outcome", "tag", "status", "due",
"created", "updated", "notes"} dicts; status is active, paused or done. The
tasks stay in tasks.json. No network call is made by this module.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

STATUSES = ("active", "paused", "done")
MAX_PROJECTS = 200
MAX_NAME = 60
MAX_OUTCOME = 200
MAX_NOTES = 300
TAG_LEN = 20


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_projects(), lambda r: _storage().save_projects(r))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:TAG_LEN].strip("-") or "project"


def _due(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    import tasks
    return tasks.parse_due(value)


def add_project(name: Any, outcome: Any = None, due: Any = None, tag: Any = None, notes: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(name, "name", MAX_NAME)
    rows = _load()
    if len(rows) >= MAX_PROJECTS:
        raise ValueError(f"you already have {MAX_PROJECTS} projects.")
    pool = kit.only_dicts(rows)
    if any(str(r.get("name", "")).lower() == clean.lower() for r in pool):
        raise ValueError(f"the project '{clean}' already exists.")
    if tag in (None, ""):
        key = _slug(clean)
    else:
        import tasks
        tags = tasks.parse_tags(tag)
        if len(tags) != 1 or len(tags[0]) > TAG_LEN:
            raise ValueError(f"the tag must be one word of at most {TAG_LEN} characters.")
        key = tags[0]
    if any(r.get("tag") == key for r in pool):
        raise ValueError(f"the tag '{key}' belongs to another project. Choose a different tag.")
    today = clock.today_str()
    item = {"id": kit.new_id(), "name": clean, "outcome": kit.clean_text(outcome, "outcome", MAX_OUTCOME, required=False),
            "tag": key, "status": "active", "due": _due(due), "created": today, "updated": today,
            "notes": kit.clean_text(notes, "notes", MAX_NOTES, required=False)}
    rows.append(item)
    _storage().save_projects(rows)
    return item


def _find(rows: List[Any], ref: Any) -> Dict[str, Any]:
    return kit.resolve(rows, ref, "project", "name", "get_projects")


def update_project(ref: Any, fields: Any) -> Dict[str, Any]:
    kit.check_fields(fields, ("name", "outcome", "status", "due", "notes"))
    rows = _load()
    item = _find(rows, ref)
    changes: Dict[str, Any] = {}
    if "name" in fields:
        new = kit.clean_text(fields["name"], "name", MAX_NAME)
        if any(r is not item and str(r.get("name", "")).lower() == new.lower() for r in kit.only_dicts(rows)):
            raise ValueError(f"the project '{new}' already exists.")
        changes["name"] = new
    if "outcome" in fields:
        changes["outcome"] = kit.clean_text(fields["outcome"], "outcome", MAX_OUTCOME, required=False)
    if "notes" in fields:
        changes["notes"] = kit.clean_text(fields["notes"], "notes", MAX_NOTES, required=False)
    if "due" in fields:
        changes["due"] = _due(fields["due"])
    if "status" in fields:
        st = str(fields["status"]).strip().lower() if isinstance(fields["status"], str) else ""
        if st not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}.")
        changes["status"] = st
    item.update(changes)
    item["updated"] = clock.today_str()
    _storage().save_projects(rows)
    return item


def delete_project(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = _find(rows, ref)
    _storage().save_projects([r for r in rows if r is not item])
    return item


def add_task(ref: Any, text: Any, due: Any = None, priority: Any = None, minutes: Any = None) -> Dict[str, Any]:
    """A task tagged for the project (the project must not be done)."""
    import tasks
    item = _find(_load(), ref)
    if item.get("status") == "done":
        raise ValueError(f"'{item['name']}' is done. Reopen it with update_project first.")
    made = tasks.add_task(text, due, priority, [item["tag"]], None, None, minutes)
    return {"project": item, "task": made}


def progress(item: Dict[str, Any]) -> Dict[str, Any]:
    import tasks
    rows = [t for t in tasks._rows(tasks._load()) if item.get("tag") in (t.get("tags") or [])]
    open_ = [t for t in rows if not t.get("done")]
    open_.sort(key=lambda t: (t.get("due") is None, str(t.get("due") or ""), {"high": 0, "normal": 1, "low": 2}.get(t.get("priority"), 1)))
    done = len(rows) - len(open_)
    return {"total": len(rows), "done": done, "open": len(open_), "next": open_[0] if open_ else None,
            "percent": round(done * 100 / len(rows)) if rows else 0}


def overdue(item: Dict[str, Any]) -> bool:
    return item.get("status") != "done" and bool(item.get("due")) and str(item["due"]) < clock.today_str()


def stuck(item: Dict[str, Any], prog: Optional[Dict[str, Any]] = None) -> bool:
    return item.get("status") == "active" and (prog or progress(item))["open"] == 0


def listing(status: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = [r for r in kit.only_dicts(_load()) if isinstance(r.get("name"), str) and r.get("status") in STATUSES]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    order = {"active": 0, "paused": 1, "done": 2}
    return sorted(rows, key=lambda r: (order[r["status"]], str(r.get("due") or "9999"), r["name"].lower()))


def nudges(max_items: int = 1) -> List[str]:
    out = []
    for r in listing("active"):
        try:
            p = progress(r)
        except Exception:  # noqa: BLE001
            continue
        if overdue(r):
            out.append(f"Project '{r['name']}' was due {r['due']}. Finish it, move the date or pause it.")
        elif stuck(r, p):
            out.append(f"Project '{r['name']}' has no open task. Add the next action with add_project_task.")
    return out[:max_items]


def agenda_lines() -> List[str]:
    out = []
    for r in listing("active"):
        p = progress(r)
        if p["next"] is not None and p["next"].get("due") == clock.today_str():
            out.append(f"{r['name']}: {p['next'].get('text')}")
    return out


def _bar(pct: int) -> str:
    n = round(pct / 10)
    return "#" * n + "." * (10 - n)


def format_project(r: Dict[str, Any], detail: bool = False) -> str:
    p = progress(r)
    flags = []
    if overdue(r):
        flags.append("overdue")
    if stuck(r, p):
        flags.append("no next action")
    head = f"{r['name']} ({r['status']}) {_bar(p['percent'])} {p['percent']}% - {p['done']}/{p['total']} tasks"
    if r.get("due"):
        head += f", due {r['due']}"
    if flags:
        head += f" [{', '.join(flags)}]"
    head += f" [id={r.get('id', '?')}]"
    if not detail:
        return head
    lines = [head]
    if r.get("outcome"):
        lines.append(f"  Outcome: {r['outcome']}")
    if p["next"] is not None:
        t = p["next"]
        lines.append(f"  Next action: {t.get('text')}" + (f" (due {t['due']})" if t.get("due") else ""))
    lines.append(f"  Tasks carry the tag #{r['tag']}.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_project":
            r = add_project(inp.get("name"), inp.get("outcome"), inp.get("due"), inp.get("tag"), inp.get("notes"))
            return f"Project added: {format_project(r)}. Add tasks with add_project_task (they carry #{r['tag']})."
        if name == "get_projects":
            st = inp.get("status")
            if st not in (None, "") and st not in STATUSES:
                raise ValueError(f"status must be one of {', '.join(STATUSES)}.")
            rows = listing(st or None)
            if not rows:
                return "No projects yet. Create one with add_project." if not st else f"No {st} projects."
            return f"{kit.plural(len(rows), 'project')}:\n" + "\n".join(f"- {format_project(r)}" for r in rows)
        if name == "get_project":
            return format_project(_find(_load(), inp.get("project")), True)
        if name == "update_project":
            return "Updated: " + format_project(update_project(inp.get("project"), inp.get("fields")))
        if name == "add_project_task":
            r = add_task(inp.get("project"), inp.get("text"), inp.get("due"), inp.get("priority"), inp.get("minutes"))
            return f"Task added to {r['project']['name']}: {r['task']['text']} [id={r['task']['id']}]"
        if name == "delete_project":
            r = delete_project(inp.get("project"))
            return f"Deleted the project {r['name']}. Its tasks are still there (tag #{r['tag']})."
    except (ValueError, TypeError) as e:
        verb = {"add_project": "Project not added", "get_projects": "Cannot show projects", "get_project": "Cannot show the project",
                "update_project": "Project not changed", "add_project_task": "Task not added"}.get(name, "Project not deleted")
        return f"{verb}: {e}"
    return f"Unknown project tool: {name}"
