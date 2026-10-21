"""
Hermes Life OS - Lists
========================
Named checklists that are not tasks: the shopping list, a packing list, "movies
to watch". Items have no due dates, you add several at once ("milk, eggs,
bread"), tick them off while you shop and clear what is ticked afterwards.

Stored in lists.json as a flat list of {"id", "list", "text", "quantity",
"done", "added", "done_date"} dicts; a list exists as long as it has an item.
The default list is "shopping". An item is found by its id or by words from its
text, optionally within one list. No network call is made by this module.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import clock

DEFAULT_LIST = "shopping"
MAX_ITEMS_TOTAL = 3000
MAX_ITEMS_PER_CALL = 50
MAX_NAME = 40
MAX_TEXT = 120
MAX_QTY = 30


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def norm_list(name: Any) -> str:
    """The list name as stored: trimmed, lower case, single spaces; blank or
    None means the default list. Raises ValueError if it is not text or too long."""
    if name is None:
        return DEFAULT_LIST
    if not isinstance(name, str):
        raise ValueError("the list name must be text.")
    text = " ".join(name.strip().lower().split())
    if not text:
        return DEFAULT_LIST
    if len(text) > MAX_NAME:
        raise ValueError(f"a list name can be at most {MAX_NAME} characters.")
    return text


def _clean_item(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("an item needs some text.")
    text = " ".join(value.split())
    if len(text) > MAX_TEXT:
        raise ValueError(f"an item can be at most {MAX_TEXT} characters.")
    return text


def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_lists()
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
        _storage().save_lists(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def _in_list(r: Dict[str, Any], name: str) -> bool:
    return str(r.get("list") or DEFAULT_LIST) == name


# ------------------------------------------------------------------ operations

def add_items(list_name: Any, items: Any, quantity: Any = None) -> Dict[str, Any]:
    """Adds items to a list. `items` is a text (split on commas and new lines)
    or a list of texts. Returns {"list", "added": rows, "skipped": [texts]};
    an item already open on the list is skipped, not duplicated. Raises
    ValueError, adding nothing, for no items, a bad item or too many."""
    name = norm_list(list_name)
    if isinstance(items, str):
        parts = [p for chunk in items.replace("\n", ",").split(",") for p in [chunk.strip()] if p]
    elif isinstance(items, list):
        parts = items
    else:
        raise ValueError("say what to add: one item, several separated by commas, or a list.")
    if not parts:
        raise ValueError("there is nothing to add.")
    if len(parts) > MAX_ITEMS_PER_CALL:
        raise ValueError(f"at most {MAX_ITEMS_PER_CALL} items at a time.")
    texts = [_clean_item(p) for p in parts]
    qty = None
    if quantity is not None and str(quantity).strip():
        if len(texts) != 1:
            raise ValueError("a quantity can only be given when adding one item.")
        qty = str(quantity).strip()
        if len(qty) > MAX_QTY:
            raise ValueError(f"the quantity can be at most {MAX_QTY} characters.")
    rows = _load()
    if len(rows) + len(texts) > MAX_ITEMS_TOTAL:
        raise ValueError(f"lists are full ({MAX_ITEMS_TOTAL} items) - clear some first.")
    open_here = {str(r.get("text", "")).lower() for r in _rows(rows) if _in_list(r, name) and not r.get("done")}
    added: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for t in texts:
        if t.lower() in open_here:
            skipped.append(t)
            continue
        open_here.add(t.lower())
        row = {"id": new_id(), "list": name, "text": t, "quantity": qty, "done": False,
               "added": clock.today_str(), "done_date": None}
        rows.append(row)
        added.append(row)
    if added:
        _storage().save_lists(rows)
    return {"list": name, "added": added, "skipped": skipped}


def _resolve(rows: List[Dict[str, Any]], ref: Any, name: Optional[str]) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which item (its id or some words from it).")
    key = ref.strip().lower()
    pool = [r for r in _rows(rows) if name is None or _in_list(r, name)]
    for r in pool:
        if str(r.get("id", "")).lower() == key:
            return r
    exact = [r for r in pool if str(r.get("text", "")).lower() == key]
    hits = exact or [r for r in pool if key in str(r.get("text", "")).lower()]
    if len(hits) > 1:
        # prefer the open ones, which is what ticking or removing normally means
        open_hits = [r for r in hits if not r.get("done")]
        hits = open_hits if len(open_hits) == 1 else hits
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no item matches '{ref.strip()}'.")
    options = "; ".join(f"[id={r['id']}] {r.get('text', '')} ({r.get('list', DEFAULT_LIST)})" for r in hits[:5])
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} items ({options}). Use the id.")


def _refs(item: Any, items: Any) -> List[Any]:
    refs: List[Any] = []
    if item is not None:
        refs.append(item)
    if isinstance(items, list):
        refs.extend(items)
    elif items is not None:
        raise ValueError("items must be a list of item names or ids.")
    if not refs:
        raise ValueError("say which item(s).")
    if len(refs) > MAX_ITEMS_PER_CALL:
        raise ValueError(f"at most {MAX_ITEMS_PER_CALL} items at a time.")
    return refs


def check_items(item: Any, items: Any, list_name: Any = None, checked: bool = True) -> List[Dict[str, Any]]:
    """Ticks (or unticks) items, all or nothing. Returns the rows."""
    name = norm_list(list_name) if list_name else None
    rows = _load()
    found: List[Dict[str, Any]] = []
    for ref in _refs(item, items):
        row = _resolve(rows, ref, name)
        if not any(f is row for f in found):
            found.append(row)
    for row in found:
        row["done"] = bool(checked)
        row["done_date"] = clock.today_str() if checked else None
    _storage().save_lists(rows)
    return found


def remove_items(item: Any, items: Any, list_name: Any = None) -> List[Dict[str, Any]]:
    name = norm_list(list_name) if list_name else None
    rows = _load()
    found: List[Dict[str, Any]] = []
    for ref in _refs(item, items):
        row = _resolve(rows, ref, name)
        if not any(f is row for f in found):
            found.append(row)
    gone = {id(f) for f in found}
    _storage().save_lists([r for r in rows if id(r) not in gone])
    return found


def clear_checked(list_name: Any = None) -> int:
    """Removes ticked items from one list, or from all lists when no list is given."""
    name = norm_list(list_name) if list_name else None
    rows = _load()
    keep = [r for r in rows if not (isinstance(r, dict) and r.get("done") and (name is None or _in_list(r, name)))]
    removed = len(rows) - len(keep)
    if removed:
        _storage().save_lists(keep)
    return removed


def delete_list(list_name: Any) -> int:
    name = norm_list(list_name)
    rows = _load()
    keep = [r for r in rows if not (isinstance(r, dict) and _in_list(r, name))]
    removed = len(rows) - len(keep)
    if not removed:
        raise ValueError(f"there is no list called '{name}'.")
    _storage().save_lists(keep)
    return removed


def get_list(list_name: Any = None) -> List[Dict[str, Any]]:
    name = norm_list(list_name)
    return [r for r in _rows(_load()) if _in_list(r, name)]


def overview() -> List[Dict[str, Any]]:
    """[{"list", "open", "done"}] for every list, the biggest first."""
    counts: Dict[str, Dict[str, Any]] = {}
    for r in _rows(_load()):
        name = str(r.get("list") or DEFAULT_LIST)
        c = counts.setdefault(name, {"list": name, "open": 0, "done": 0})
        c["done" if r.get("done") else "open"] += 1
    return sorted(counts.values(), key=lambda c: (-(c["open"] + c["done"]), c["list"]))


# ------------------------------------------------------------------ formatting

def format_item(r: Dict[str, Any]) -> str:
    qty = f" ({r['quantity']})" if r.get("quantity") else ""
    return f"[{'x' if r.get('done') else ' '}] {r.get('text', '?')}{qty} [id={r.get('id', '?')}]"


def format_list(name: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return f"The {name} list is empty."
    open_rows = [r for r in rows if not r.get("done")]
    done_rows = [r for r in rows if r.get("done")]
    head = f"{name.capitalize()}: {len(open_rows)} to get" + (f", {len(done_rows)} ticked" if done_rows else "")
    return head + "\n" + "\n".join(format_item(r) for r in open_rows + done_rows)


def format_overview(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No lists yet. Add items with add_list_items."
    return f"{len(rows)} list{'s' if len(rows) != 1 else ''}:\n" + "\n".join(
        f"- {c['list']}: {c['open']} open" + (f", {c['done']} ticked" if c["done"] else "") for c in rows)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_list_items":
            r = add_items(inp.get("list"), inp.get("items"), inp.get("quantity"))
            parts = []
            if r["added"]:
                parts.append(f"Added to {r['list']}: " + ", ".join(
                    x["text"] + (f" ({x['quantity']})" if x.get("quantity") else "") for x in r["added"]) + ".")
            if r["skipped"]:
                parts.append("Already on the list: " + ", ".join(r["skipped"]) + ".")
            return " ".join(parts)
        if name == "get_list":
            n = norm_list(inp.get("list"))
            return format_list(n, get_list(n))
        if name == "get_lists":
            return format_overview(overview())
        if name == "check_list_item":
            checked = inp.get("checked", True) is not False
            rows = check_items(inp.get("item"), inp.get("items"), inp.get("list"), checked)
            return f"{'Ticked' if checked else 'Unticked'}: " + ", ".join(r["text"] for r in rows) + "."
        if name == "remove_list_items":
            rows = remove_items(inp.get("item"), inp.get("items"), inp.get("list"))
            return "Removed: " + ", ".join(r["text"] for r in rows) + "."
        if name == "clear_checked_items":
            n = clear_checked(inp.get("list"))
            return f"Removed {n} ticked item(s)." if n else "Nothing was ticked."
        if name == "delete_list":
            n = delete_list(inp.get("list"))
            return f"Deleted the {norm_list(inp.get('list'))} list ({n} item(s)). This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_list_items": "Not added", "get_list": "Cannot show list", "get_lists": "Cannot show lists",
                "check_list_item": "Not changed", "remove_list_items": "Not removed",
                "clear_checked_items": "Not cleared", "delete_list": "Not deleted"}.get(name, "Error")
        return f"{verb}: {e}"
    return f"Unknown list tool: {name}"
