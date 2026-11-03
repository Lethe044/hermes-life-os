"""
Hermes Life OS - Library
==========================
One backlog for everything you want to read, watch, play or learn: books,
movies, shows, games, podcasts, courses. Items move from want to doing to done
(or dropped), can carry a progress percentage and a 1 to 5 rating, and Hermes
can suggest what to pick up next and summarise what you finished this year.

Stored in library.json as {"id", "title", "kind", "creator", "status",
"progress", "rating", "notes", "added", "started", "finished", "updated"}
dicts. No network call is made by this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

KINDS = ("book", "movie", "show", "game", "podcast", "course", "other")
STATUSES = ("want", "doing", "done", "dropped")
MAX_ITEMS = 1000
MAX_TITLE = 100
MAX_CREATOR = 60
MAX_NOTES = 300
STALE_DAYS = 30


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_library(), lambda r: _storage().save_library(r))


def _choice(value: Any, allowed, what: str, default: Optional[str] = None) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is None:
            raise ValueError(f"say the {what} ({', '.join(allowed)}).")
        return default
    key = value.strip().lower() if isinstance(value, str) else ""
    if key not in allowed:
        raise ValueError(f"the {what} must be one of {', '.join(allowed)}.")
    return key


def _whole(value: Any, what: str, low: int, high: int) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not low <= value <= high:
        raise ValueError(f"{what} must be a whole number from {low} to {high}.")
    return int(value)


def _day_ok(value: Any) -> bool:
    try:
        clock.parse_day(value)
        return True
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ operations

def add_item(title: Any, kind: Any = None, creator: Any = None, status: Any = None, notes: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(title, "title", MAX_TITLE)
    k = _choice(kind, KINDS, "kind", "book")
    st = _choice(status, STATUSES, "status", "want")
    rows = _load()
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"you already have {MAX_ITEMS} items.")
    for r in kit.only_dicts(rows):
        if str(r.get("title", "")).lower() == clean.lower() and r.get("kind") == k:
            raise ValueError(f"'{r.get('title')}' is already in your library ({r.get('status')}).")
    today = clock.today_str()
    item = {"id": kit.new_id(), "title": clean, "kind": k, "creator": kit.clean_text(creator, "creator", MAX_CREATOR, required=False),
            "status": st, "progress": 100 if st == "done" else 0, "rating": None,
            "notes": kit.clean_text(notes, "notes", MAX_NOTES, required=False), "added": today,
            "started": today if st in ("doing", "done") else None, "finished": today if st == "done" else None,
            "updated": today}
    rows.append(item)
    _storage().save_library(rows)
    return item


def _apply_status(item: Dict[str, Any], status: str) -> None:
    today = clock.today_str()
    item["status"] = status
    if status == "doing" and not item.get("started"):
        item["started"] = today
    if status == "done":
        item["finished"] = item.get("finished") or today
        item["started"] = item.get("started") or today
        item["progress"] = 100
    elif status == "want":
        item["started"] = None
        item["finished"] = None
        item["progress"] = 0
    else:
        item["finished"] = None


def update_item(ref: Any, fields: Any) -> Dict[str, Any]:
    kit.check_fields(fields, ("title", "kind", "creator", "status", "progress", "rating", "notes"))
    rows = _load()
    item = kit.resolve(rows, ref, "library item", "title", "get_library")
    changes: Dict[str, Any] = {}
    if "title" in fields:
        changes["title"] = kit.clean_text(fields["title"], "title", MAX_TITLE)
    if "kind" in fields:
        changes["kind"] = _choice(fields["kind"], KINDS, "kind")
    if "creator" in fields:
        changes["creator"] = kit.clean_text(fields["creator"], "creator", MAX_CREATOR, required=False)
    if "notes" in fields:
        changes["notes"] = kit.clean_text(fields["notes"], "notes", MAX_NOTES, required=False)
    if "rating" in fields:
        changes["rating"] = _whole(fields["rating"], "rating", 1, 5)
    progress = _whole(fields["progress"], "progress", 0, 100) if "progress" in fields else None
    status = _choice(fields["status"], STATUSES, "status") if "status" in fields else None
    item.update(changes)
    if status:
        _apply_status(item, status)
    if progress is not None and status != "done":
        item["progress"] = progress
        if status is None:
            if progress >= 100:
                _apply_status(item, "done")
            elif progress > 0 and item.get("status") == "want":
                _apply_status(item, "doing")
                item["progress"] = progress
    item["updated"] = clock.today_str()
    _storage().save_library(rows)
    return item


def finish_item(ref: Any, rating: Any = None, notes: Any = None) -> Dict[str, Any]:
    fields: Dict[str, Any] = {"status": "done"}
    if rating not in (None, ""):
        fields["rating"] = rating
    if notes not in (None, ""):
        fields["notes"] = notes
    return update_item(ref, fields)


def delete_item(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "library item", "title", "get_library")
    _storage().save_library([r for r in rows if r is not item])
    return item


def listing(status: Optional[str] = None, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = kit.only_dicts(_load())
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    order = {"doing": 0, "want": 1, "done": 2, "dropped": 3}
    return sorted(rows, key=lambda r: (order.get(r.get("status"), 9), str(r.get("updated") or ""), str(r.get("title", "")).lower()))


def suggest(kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """What to pick up next: an item already in progress that has been idle the
    longest, otherwise the item that has waited longest on the want list."""
    rows = kit.only_dicts(_load())
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    doing = sorted((r for r in rows if r.get("status") == "doing"), key=lambda r: str(r.get("updated") or ""))
    if doing:
        return doing[0]
    want = sorted((r for r in rows if r.get("status") == "want"), key=lambda r: (str(r.get("added") or ""), str(r.get("title", "")).lower()))
    return want[0] if want else None


def stats(year: Optional[int] = None) -> Dict[str, Any]:
    rows = kit.only_dicts(_load())
    year = year or clock.today().year
    by_status = {s: sum(1 for r in rows if r.get("status") == s) for s in STATUSES}
    finished = [r for r in rows if r.get("status") == "done" and str(r.get("finished") or "").startswith(f"{year}-")]
    by_kind: Dict[str, int] = {}
    for r in finished:
        by_kind[r.get("kind", "other")] = by_kind.get(r.get("kind", "other"), 0) + 1
    rated = [r["rating"] for r in finished if isinstance(r.get("rating"), int)]
    best = sorted((r for r in finished if r.get("rating") == 5), key=lambda r: str(r.get("finished")))
    return {"year": year, "total": len(rows), "by_status": by_status, "finished": len(finished), "by_kind": by_kind,
            "avg_rating": (sum(rated) / len(rated)) if rated else None, "favorites": [r.get("title") for r in best[:5]]}


def nudges(max_items: int = 1) -> List[str]:
    today = clock.today()
    out = []
    for r in listing("doing"):
        try:
            idle = (today - clock.parse_day(r.get("updated"))).days
        except (ValueError, TypeError):
            continue
        if idle >= STALE_DAYS:
            out.append((idle, f"'{r.get('title')}' has sat in progress for {idle} days. Pick it up, finish it or drop it."))
    out.sort(key=lambda x: -x[0])
    return [m for _, m in out][:max_items]


# ------------------------------------------------------------------ formatting

def format_item(r: Dict[str, Any]) -> str:
    by = f" by {r['creator']}" if r.get("creator") else ""
    bits = [f"{r.get('title', '?')}{by} ({r.get('kind', '?')}, {r.get('status', '?')}"]
    if r.get("status") == "doing" and isinstance(r.get("progress"), int):
        bits[0] += f", {r['progress']}%"
    if isinstance(r.get("rating"), int):
        bits[0] += f", {r['rating']}/5"
    return bits[0] + f") [id={r.get('id', '?')}]"


def format_all(rows: List[Dict[str, Any]], label: str) -> str:
    if not rows:
        return "Your library is empty here. Add something with add_library_item." if label == "all" else \
            f"Nothing in your library matches {label}."
    return f"{kit.plural(len(rows), 'item')} ({label}):\n" + "\n".join(f"- {format_item(r)}" for r in rows[:60]) + \
        (f"\n...and {len(rows) - 60} more." if len(rows) > 60 else "")


def format_stats(s: Dict[str, Any]) -> str:
    b = s["by_status"]
    lines = [f"Library: {s['total']} items - {b['doing']} in progress, {b['want']} waiting, {b['done']} done, {b['dropped']} dropped."]
    if s["finished"]:
        kinds = ", ".join(f"{n} {k}" for k, n in sorted(s["by_kind"].items(), key=lambda kv: (-kv[1], kv[0])))
        avg = f", average rating {s['avg_rating']:.1f}/5" if s["avg_rating"] is not None else ""
        lines.append(f"Finished in {s['year']}: {s['finished']} ({kinds}){avg}.")
        if s["favorites"]:
            lines.append("Five-star picks: " + ", ".join(s["favorites"]) + ".")
    else:
        lines.append(f"Nothing finished in {s['year']} yet.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_library_item":
            return "Added: " + format_item(add_item(inp.get("title"), inp.get("kind"), inp.get("creator"),
                                                    inp.get("status"), inp.get("notes")))
        if name == "get_library":
            status = _choice(inp.get("status"), STATUSES, "status", "") or None
            kind = _choice(inp.get("kind"), KINDS, "kind", "") or None
            label = " ".join(x for x in (status, kind) if x) or "all"
            return format_all(listing(status, kind), label)
        if name == "update_library_item":
            return "Updated: " + format_item(update_item(inp.get("item"), inp.get("fields")))
        if name == "finish_library_item":
            return "Finished: " + format_item(finish_item(inp.get("item"), inp.get("rating"), inp.get("notes")))
        if name == "suggest_library_item":
            kind = _choice(inp.get("kind"), KINDS, "kind", "") or None
            pick = suggest(kind)
            if pick is None:
                return "Nothing is waiting in your library. Add something with add_library_item."
            why = "you already started it" if pick.get("status") == "doing" else "it has waited the longest"
            return f"Next up: {format_item(pick)} - {why}."
        if name == "get_library_stats":
            return format_stats(stats(_whole(inp.get("year"), "year", 1900, 2200)))
        if name == "delete_library_item":
            return f"Deleted {delete_item(inp.get('item'))['title']} from your library."
    except (ValueError, TypeError) as e:
        verb = {"add_library_item": "Item not added", "get_library": "Cannot show the library",
                "finish_library_item": "Item not finished", "suggest_library_item": "No suggestion",
                "get_library_stats": "Cannot show stats", "delete_library_item": "Item not deleted"}.get(name, "Item not changed")
        return f"{verb}: {e}"
    return f"Unknown library tool: {name}"
