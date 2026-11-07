"""
Hermes Life OS - Inbox
========================
A place to dump anything the moment it crosses your mind, without deciding
what it is. Later you triage each item: turn it into a task, a note, a
library item or one of today's priorities, or just drop it. Hermes reminds you
when the inbox has grown or items have waited a few days.

Stored in inbox.json as {"id", "text", "added", "source"} dicts. Processing an
item removes it from the inbox. No network call is made by this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import clock
import plannerkit as kit

MAX_ITEMS = 300
MAX_TEXT = 300
STALE_DAYS = 3
BIG_INBOX = 10
TARGETS = ("task", "note", "library", "priority")


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_inbox(), lambda r: _storage().save_inbox(r))


def add_item(text: Any, source: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(text, "item", MAX_TEXT)
    rows = _load()
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"your inbox already holds {MAX_ITEMS} items. Process some first.")
    if any(str(r.get("text", "")).lower() == clean.lower() for r in kit.only_dicts(rows)):
        raise ValueError(f"'{clean}' is already in your inbox.")
    item = {"id": kit.new_id(), "text": clean, "added": clock.today_str(),
            "source": kit.clean_text(source, "source", 30, required=False)}
    rows.append(item)
    _storage().save_inbox(rows)
    return item


def listing() -> List[Dict[str, Any]]:
    return sorted(kit.only_dicts(_load()), key=lambda r: (str(r.get("added") or ""), str(r.get("text", "")).lower()))


def age_days(item: Dict[str, Any]) -> int:
    try:
        return (clock.today() - clock.parse_day(item.get("added"))).days
    except (ValueError, TypeError):
        return 0


def process_item(ref: Any, target: Any, **opts: Any) -> Dict[str, Any]:
    """Moves an item out of the inbox into `target` (task, note, library or
    priority). Nothing is removed unless the new entry was created."""
    key = str(target).strip().lower() if isinstance(target, str) else ""
    if key not in TARGETS:
        raise ValueError(f"say where it goes: {', '.join(TARGETS)}.")
    rows = _load()
    item = kit.resolve(rows, ref, "inbox item", "text", "get_inbox")
    text = item["text"]
    if key == "task":
        import tasks
        made = tasks.add_task(text, opts.get("due"), opts.get("priority"), opts.get("tags"), None, None, opts.get("minutes"))
        where = f"task {made['id']}"
    elif key == "note":
        import notes
        made = notes.add_note(text, opts.get("tags"))
        where = f"note {made['id']}"
    elif key == "library":
        import library
        made = library.add_item(text, opts.get("kind"))
        where = f"{made['kind']} {made['id']} in your library"
    else:
        import priorities
        made = priorities.add_priority(text, None, opts.get("due"))
        where = f"priority for {made['date']}"
    _storage().save_inbox([r for r in _load() if not (isinstance(r, dict) and r.get("id") == item["id"])])
    return {"item": item, "target": key, "where": where}


def delete_item(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "inbox item", "text", "get_inbox")
    _storage().save_inbox([r for r in rows if r is not item])
    return item


def nudges(max_items: int = 1) -> List[str]:
    rows = listing()
    if not rows:
        return []
    old = [r for r in rows if age_days(r) >= STALE_DAYS]
    if len(rows) >= BIG_INBOX:
        return [f"Your inbox holds {len(rows)} items. Sort them with get_inbox and process_inbox_item."][:max_items]
    if old:
        return [f"{kit.plural(len(old), 'inbox item')} {'has' if len(old) == 1 else 'have'} waited {STALE_DAYS}+ days, "
                f"for example '{old[0]['text']}'."][:max_items]
    return []


def agenda_lines() -> List[str]:
    rows = listing()
    return [f"{kit.plural(len(rows), 'unsorted item')} (oldest: {rows[0]['text']})"] if rows else []


def format_inbox(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "Your inbox is empty. Capture anything with add_to_inbox."
    lines = [f"Inbox: {kit.plural(len(rows), 'item')}"]
    for r in rows[:40]:
        age = age_days(r)
        lines.append(f"- {r['text']} ({'today' if age == 0 else kit.plural(age, 'day') + ' old'}) [id={r['id']}]")
    if len(rows) > 40:
        lines.append(f"...and {len(rows) - 40} more.")
    lines.append("Turn an item into a task, note, library item or priority with process_inbox_item.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_to_inbox":
            r = add_item(inp.get("text"), inp.get("source"))
            return f"Captured: {r['text']} [id={r['id']}]. {kit.plural(len(_load()), 'item')} in the inbox."
        if name == "get_inbox":
            return format_inbox(listing())
        if name == "process_inbox_item":
            r = process_item(inp.get("item"), inp.get("as"), due=inp.get("due"), priority=inp.get("priority"),
                             tags=inp.get("tags"), minutes=inp.get("minutes"), kind=inp.get("kind"))
            return f"Moved '{r['item']['text']}' to {r['where']}."
        if name == "delete_inbox_item":
            return f"Dropped '{delete_item(inp.get('item'))['text']}' from the inbox."
    except (ValueError, TypeError) as e:
        verb = {"add_to_inbox": "Not captured", "get_inbox": "Cannot show the inbox",
                "process_inbox_item": "Item not moved"}.get(name, "Item not dropped")
        return f"{verb}: {e}"
    return f"Unknown inbox tool: {name}"
