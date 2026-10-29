"""
Hermes Life OS - small shared helpers for the planner modules
===============================================================
Ids, text cleaning, lookup by id or words and the "in 3 days" wording that the
newer planner modules (chores, expiries, routines, gifts, decisions) share.
Pure functions: no storage access and no network call.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Iterable, List


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def clean_text(value: Any, what: str, max_len: int, required: bool = True) -> str:
    """`value` with whitespace collapsed. Raises ValueError for empty (when
    required), non-text or too long input."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"the {what} cannot be empty.")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"the {what} must be text.")
    text = " ".join(value.split())
    if len(text) > max_len:
        raise ValueError(f"the {what} can be at most {max_len} characters.")
    return text


def only_dicts(rows: Any) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def load_rows(loader: Callable[[], Any], saver: Callable[[Any], None]) -> List[Any]:
    """The stored list, with an id given to every dict entry that has none
    (saved back when that happened). Anything but a list reads as empty."""
    rows = loader()
    if not isinstance(rows, list):
        return []
    seen = {r.get("id") for r in rows if isinstance(r, dict) and r.get("id")}
    changed = False
    for r in rows:
        if isinstance(r, dict) and not r.get("id"):
            fresh = new_id()
            while fresh in seen:
                fresh = new_id()
            seen.add(fresh)
            r["id"] = fresh
            changed = True
    if changed:
        saver(rows)
    return rows


def resolve(rows: Iterable[Dict[str, Any]], ref: Any, what: str, label_key: str, list_tool: str) -> Dict[str, Any]:
    """The one entry whose id or `label_key` equals `ref`, or whose label
    contains it. Raises ValueError saying what is wrong when none or several
    match."""
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"say which {what} (its id or some words from its {label_key}).")
    key = ref.strip().lower()
    pool = only_dicts(list(rows))
    for r in pool:
        if str(r.get("id", "")).lower() == key or str(r.get(label_key, "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get(label_key, "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no {what} matches '{ref.strip()}'. Use {list_tool} to see them.")
    names = "; ".join(str(r.get(label_key, "?")) for r in hits[:5])
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} {what}s ({names}). Use the full {label_key} or the id.")


def check_fields(fields: Any, allowed: Iterable[str]) -> Dict[str, Any]:
    """`fields` when it is a non-empty dict of allowed keys, else ValueError."""
    allowed = list(allowed)
    if not isinstance(fields, dict) or not fields:
        raise ValueError(f"nothing to change: give some fields ({', '.join(allowed)}).")
    unknown = sorted(k for k in fields if k not in allowed)
    if unknown:
        raise ValueError(f"cannot change {', '.join(unknown)}. You can change {', '.join(allowed)}.")
    return fields


def when_text(days: int) -> str:
    """today / tomorrow / in 5 days / yesterday / 3 days ago."""
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days > 1:
        return f"in {days} days"
    return "yesterday" if days == -1 else f"{-days} days ago"


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"
