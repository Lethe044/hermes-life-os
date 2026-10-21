"""
Hermes Life OS - Notes
========================
A quick-capture inbox: a thought, an idea, a gift idea, a recipe link. A note
is text with optional tags and a pin. Unlike the journal tools it is not
mood-related and not dated to a day you lived, just something to find again:
list the newest notes, pull one tag, or search by words.

Stored in notes.json as a list of {"id", "text", "created", "updated", "tags",
"pinned"} dicts. Pinned notes come first in listings. No network call is made
by this module.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

import clock
from tasks import parse_tags  # the same tag rules as tasks

MAX_TEXT = 2000
MAX_NOTES = 5000
MAX_LIST = 100


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def _clean_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("the note needs some text.")
    text = value.strip()
    if len(text) > MAX_TEXT:
        raise ValueError(f"a note can be at most {MAX_TEXT} characters.")
    return text


def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_notes()
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
        _storage().save_notes(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def _resolve(rows: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which note (its id or some words from it).")
    key = ref.strip().lower()
    pool = _rows(rows)
    for r in pool:
        if str(r.get("id", "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get("text", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no note matches '{ref.strip()}'. Use list_notes or search_notes to see ids.")
    options = "; ".join(f"[id={r['id']}] {_preview(r)}" for r in hits[:5])
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} notes ({options}). Use the id.")


def _sorted(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pinned first, then newest first."""
    ordered = sorted(rows, key=lambda r: str(r.get("updated") or r.get("created") or ""), reverse=True)
    return sorted(ordered, key=lambda r: not r.get("pinned"))


# ------------------------------------------------------------------ operations

def add_note(text: Any, tags: Any = None, pinned: Any = False) -> Dict[str, Any]:
    clean = _clean_text(text)
    tag_list = parse_tags(tags)
    rows = _load()
    if len(rows) >= MAX_NOTES:
        raise ValueError(f"you already have {MAX_NOTES} notes - delete some first.")
    today = clock.today_str()
    note = {"id": new_id(), "text": clean, "created": today, "updated": today, "tags": tag_list,
            "pinned": bool(pinned)}
    rows.append(note)
    _storage().save_notes(rows)
    return note


def list_notes(tag: Any = None, pinned: Any = None, limit: Any = 20) -> List[Dict[str, Any]]:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        raise ValueError("limit must be a whole number.") from None
    if n < 1:
        raise ValueError("limit must be at least 1.")
    rows = _rows(_load())
    if isinstance(tag, str) and tag.strip():
        key = tag.strip().lstrip("#").lower()
        rows = [r for r in rows if key in (r.get("tags") or [])]
    if pinned is not None:
        rows = [r for r in rows if bool(r.get("pinned")) == bool(pinned)]
    return _sorted(rows)[:min(n, MAX_LIST)]


def search_notes(query: Any, limit: Any = 20) -> List[Dict[str, Any]]:
    """Notes containing every word of the query in their text or tags."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("say what to search for.")
    words = query.lower().replace("#", " ").split()
    hits = []
    for r in _rows(_load()):
        hay = (str(r.get("text", "")) + " " + " ".join(r.get("tags") or [])).lower()
        if all(w in hay for w in words):
            hits.append(r)
    try:
        n = max(1, min(int(limit), MAX_LIST))
    except (TypeError, ValueError):
        raise ValueError("limit must be a whole number.") from None
    return _sorted(hits)[:n]


def update_note(ref: Any, fields: Any) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields (text, tags, pinned).")
    unknown = [k for k in fields if k not in ("text", "tags", "pinned")]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change text, tags and pinned.")
    rows = _load()
    note = _resolve(rows, ref)
    changes: Dict[str, Any] = {}
    if "text" in fields:
        changes["text"] = _clean_text(fields["text"])
    if "tags" in fields:
        changes["tags"] = parse_tags(fields["tags"])
    if "pinned" in fields:
        if not isinstance(fields["pinned"], bool):
            raise ValueError("pinned must be true or false.")
        changes["pinned"] = fields["pinned"]
    note.update(changes)
    note["updated"] = clock.today_str()
    _storage().save_notes(rows)
    return note


def delete_note(ref: Any) -> Dict[str, Any]:
    rows = _load()
    note = _resolve(rows, ref)
    _storage().save_notes([r for r in rows if r is not note])
    return note


# ------------------------------------------------------------------ formatting

def _preview(r: Dict[str, Any], width: int = 80) -> str:
    text = " ".join(str(r.get("text", "")).split())
    return text if len(text) <= width else text[:width - 3] + "..."


def format_note(r: Dict[str, Any], full: bool = False) -> str:
    tags = (" " + " ".join("#" + t for t in r.get("tags") or [])) if r.get("tags") else ""
    pin = "[pinned] " if r.get("pinned") else ""
    text = r.get("text", "") if full else _preview(r)
    return f"{pin}{text}{tags} ({r.get('updated') or r.get('created') or '?'}) [id={r.get('id', '?')}]"


def format_notes(rows: List[Dict[str, Any]], empty: str = "No notes yet.") -> str:
    if not rows:
        return empty
    return f"{len(rows)} note{'s' if len(rows) != 1 else ''}:\n" + "\n".join(f"- {format_note(r)}" for r in rows)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_note":
            return "Note saved: " + format_note(add_note(inp.get("text"), inp.get("tags"), inp.get("pinned", False)), True)
        if name == "list_notes":
            return format_notes(list_notes(inp.get("tag"), inp.get("pinned"), inp.get("limit", 20)))
        if name == "search_notes":
            return format_notes(search_notes(inp.get("query"), inp.get("limit", 20)),
                                f"No notes match '{str(inp.get('query', '')).strip()}'.")
        if name == "update_note":
            return "Note updated: " + format_note(update_note(inp.get("note"), inp.get("fields")), True)
        if name == "delete_note":
            return f"Deleted note: {_preview(delete_note(inp.get('note')))}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_note": "Note not saved", "list_notes": "Cannot list notes",
                "search_notes": "Cannot search notes"}.get(name, "Note not changed")
        return f"{verb}: {e}"
    return f"Unknown note tool: {name}"
