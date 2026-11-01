"""
Hermes Life OS - Recently Deleted (trash)
===========================================
Deleting is the one thing in a planner that cannot be taken back, and the
person typing the command is often a language model acting on a vague
sentence. Every delete or clear tool of the planner now keeps what it removed
for 30 days: `get_trash` lists it, `restore_deleted` puts it back and
`empty_trash` removes it for good.

Nothing in the deleting tools themselves changed. `capture` wraps the call: it
reads the affected store before and after, and what disappeared (rows with an
id) is filed in trash.json as one entry per call and store. Covered: whole
entries of tasks, notes, people, subscriptions, savings goals, debts,
countdowns, supplies, time blocks, objectives, recipes, planned meals, trips,
chores, expiry dates, routines, gift ideas, decisions and lists (including
`clear_done_tasks`, `clear_checked_items`, `remove_list_items` and
`delete_list`). Not covered: logged entries (use `undo_last_log`), parts of an
entry (a key result, a packing item) and habits, goals, budgets, reminders and
templates.

Stored in trash.json as {"id", "store", "tool", "deleted", "label", "count",
"rows"} dicts. Entries older than 30 days are dropped when something new is
filed; at most 100 are kept. No network call is made by this module.
"""

from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

RETAIN_DAYS = 30
MAX_ENTRIES = 100
MAX_ROWS = 500
MAX_LABEL = 70

# tool -> the stores whose removed entries are kept
WATCHED: Dict[str, tuple] = {
    "delete_task": ("tasks",), "clear_done_tasks": ("tasks",), "delete_note": ("notes",), "delete_person": ("people",),
    "delete_subscription": ("subscriptions",), "delete_savings_goal": ("savings",), "delete_debt": ("debts",),
    "delete_countdown": ("countdowns",), "delete_supply": ("supplies",), "delete_time_block": ("timeblocks",),
    "delete_okr": ("okrs",), "delete_recipe": ("recipes",), "clear_meals": ("mealplan",), "delete_trip": ("trips",),
    "delete_chore": ("chores",), "delete_expiry": ("expiries",), "delete_routine": ("routines",),
    "delete_gift_idea": ("gifts",), "delete_decision": ("decisions",), "delete_list": ("lists",),
    "remove_list_items": ("lists",), "clear_checked_items": ("lists",),
}
NOUNS = {"tasks": "task", "notes": "note", "people": "person", "subscriptions": "subscription", "savings": "savings goal",
         "debts": "debt", "countdowns": "countdown", "supplies": "supply", "timeblocks": "time block", "okrs": "objective",
         "recipes": "recipe", "mealplan": "planned meal", "trips": "trip", "chores": "chore", "expiries": "expiry date",
         "routines": "routine", "gifts": "gift idea", "decisions": "decision", "lists": "list item"}
_LABEL_KEYS = ("name", "title", "text", "idea", "who", "symptom")


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_trash(), lambda r: _storage().save_trash(r))


def row_label(row: Dict[str, Any]) -> str:
    for key in _LABEL_KEYS:
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            text = " ".join(v.split())
            return text if len(text) <= MAX_LABEL else text[:MAX_LABEL - 3] + "..."
    return str(row.get("id", "entry"))


def _rows_with_ids(store: str) -> List[Dict[str, Any]]:
    data = _storage().load_store(store)
    return [r for r in data if isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"]] if isinstance(data, list) else []


def age_days(entry: Dict[str, Any]) -> Optional[int]:
    try:
        return (clock.today() - clock.parse_day(entry.get("deleted"))).days
    except ValueError:
        return None


def days_left(entry: Dict[str, Any]) -> int:
    age = age_days(entry)
    return RETAIN_DAYS - age if age is not None else 0


def _alive(entries: List[Any]) -> List[Dict[str, Any]]:
    return [e for e in kit.only_dicts(entries) if days_left(e) > 0]


def _file(store: str, tool: str, removed: List[Dict[str, Any]]) -> None:
    entries = [e for e in kit.only_dicts(_load()) if days_left(e) > 0]
    removed = copy.deepcopy(removed[:MAX_ROWS])
    names = [row_label(r) for r in removed]
    label = ", ".join(names) if len(names) <= 3 else f"{names[0]}, {names[1]} and {len(names) - 2} more"
    if len(label) > MAX_LABEL * 2:
        label = label[:MAX_LABEL * 2 - 3] + "..."
    entries.append({"id": kit.new_id(), "store": store, "tool": tool, "deleted": clock.today_str(), "label": label,
                    "count": len(removed), "rows": removed})
    _storage().save_trash(entries[-MAX_ENTRIES:])


def capture(name: str, run) -> str:
    """Runs `run()` (a delete or clear tool) and files what it removed. Filing
    can never change or break the tool's own result."""
    stores = WATCHED.get(name, ())
    try:
        before = {s: _rows_with_ids(s) for s in stores}
    except Exception:  # noqa: BLE001 - a store that cannot be read is simply not watched
        before = None
    result = run()
    if before is not None:
        try:
            for s in stores:
                kept = {r["id"] for r in _rows_with_ids(s)}
                gone = [r for r in before[s] if r["id"] not in kept]
                if gone:
                    _file(s, name, gone)
        except Exception:  # noqa: BLE001
            pass
    return result


# ------------------------------------------------------------------ operations

def listing(store: Any = None) -> List[Dict[str, Any]]:
    entries = _alive(_load())
    if store not in (None, ""):
        key = str(store).strip().lower()
        known = {k: v for k, v in NOUNS.items()}
        match = [s for s in known if key == s or key == known[s] or key == known[s] + "s"]
        if not match:
            raise ValueError(f"unknown kind '{str(store).strip()}'. Kinds: {', '.join(NOUNS.values())}.")
        entries = [e for e in entries if e.get("store") == match[0]]
    return sorted(entries, key=lambda e: (str(e.get("deleted")), str(e.get("id"))), reverse=True)


def _find(entries: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    """The entry whose id equals `ref`, or whose label or any removed row's name contains it."""
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which deleted item (its id from get_trash or some words from its name).")
    key = ref.strip().lower()
    for e in entries:
        if str(e.get("id", "")).lower() == key:
            return e
    hits = [e for e in entries if key in str(e.get("label", "")).lower()
            or any(isinstance(r, dict) and key in row_label(r).lower() for r in (e.get("rows") if isinstance(e.get("rows"), list) else []))]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no deleted item matches '{ref.strip()}'. Use get_trash to see them.")
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} deleted items ({'; '.join(str(e.get('label')) for e in hits[:5])}). "
                     f"Use the id from get_trash.")


def restore(ref: Any) -> Dict[str, Any]:
    entries = _load()
    entry = _find(_alive(entries), ref)
    store = entry.get("store")
    if store not in NOUNS or not isinstance(entry.get("rows"), list):
        raise ValueError("this trash entry cannot be restored (unknown store). Remove it with empty_trash.")
    current = _storage().load_store(store)
    current = current if isinstance(current, list) else []
    present = {r.get("id") for r in current if isinstance(r, dict)}
    back = [r for r in entry["rows"] if isinstance(r, dict) and r.get("id") not in present]
    skipped = len(entry["rows"]) - len(back)
    if back:
        _storage().save_store(store, current + copy.deepcopy(back))
    _storage().save_trash([e for e in entries if e is not entry])
    if not back:
        raise ValueError(f"everything in '{entry.get('label')}' is already back in your {store}. It was removed from the trash.")
    return {"entry": entry, "restored": len(back), "skipped": skipped}


def empty(ref: Any = None, older_than_days: Any = None) -> int:
    """Permanently removes one entry, entries older than N days, or everything.
    Returns how many entries were removed."""
    entries = _load()
    if ref not in (None, ""):
        entry = _find(_alive(entries), ref)
        keep = [e for e in entries if e is not entry]
    elif older_than_days not in (None, ""):
        if isinstance(older_than_days, bool) or not isinstance(older_than_days, (int, float)) or older_than_days != int(older_than_days) \
                or not 0 <= older_than_days <= RETAIN_DAYS:
            raise ValueError(f"older_than_days must be a whole number from 0 to {RETAIN_DAYS}.")
        limit = int(older_than_days)
        keep = [e for e in entries if isinstance(e, dict) and (age_days(e) or 0) <= limit] if limit else []
    else:
        keep = []
    removed = len(entries) - len(keep)
    _storage().save_trash(keep)
    return removed


# ------------------------------------------------------------------ formatting

def format_entry(e: Dict[str, Any]) -> str:
    noun = NOUNS.get(e.get("store"), str(e.get("store")))
    count = e.get("count") if isinstance(e.get("count"), int) else len(e.get("rows") or [])
    what = f"{noun} '{e.get('label')}'" if count <= 1 else f"{kit.plural(count, noun)}: {e.get('label')}"
    left = days_left(e)
    return (f"{e.get('deleted')} {what} (by {e.get('tool')}, {kit.plural(left, 'day')} left) [id={e.get('id', '?')}]")


def format_all(entries: List[Dict[str, Any]], filtered: bool = False) -> str:
    if not entries:
        return ("Nothing matching in the trash." if filtered
                else f"The trash is empty. Deleted tasks, notes, people and other planner entries are kept here for {RETAIN_DAYS} days.")
    return (f"{kit.plural(len(entries), 'deleted item')} (kept {RETAIN_DAYS} days, restore with restore_deleted):\n"
            + "\n".join(f"- {format_entry(e)}" for e in entries))


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "get_trash":
            return format_all(listing(inp.get("kind")), bool(inp.get("kind")))
        if name == "restore_deleted":
            r = restore(inp.get("item"))
            e = r["entry"]
            noun = NOUNS.get(e.get("store"), e.get("store"))
            what = f"'{e.get('label')}'" if e.get("count", 1) <= 1 else f"{kit.plural(r['restored'], noun)} ('{e.get('label')}')"
            extra = f" ({r['skipped']} already existed)" if r["skipped"] else ""
            note = " Planned meals that used it stay as text." if e.get("store") == "recipes" else ""
            return f"Restored {what} to your {e.get('store')}{extra}.{note}"
        if name == "empty_trash":
            n = empty(inp.get("item"), inp.get("older_than_days"))
            return f"Permanently removed {kit.plural(n, 'deleted item')} from the trash. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"get_trash": "Cannot show the trash", "restore_deleted": "Not restored"}.get(name, "Trash not emptied")
        return f"{verb}: {e}"
    return f"Unknown trash tool: {name}"
