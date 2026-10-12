"""
Hermes Life OS - Entry Management
===================================
Until v1.40.0 only expenses could be corrected. A meal logged with the wrong
calories, a workout logged twice or a sleep entry for the wrong night stayed
in the data (and in every streak, average and correlation built on it) for
good. This module adds list / edit / delete / undo for the other trackers,
plus a finder for days with nothing logged (so they can be filled in with the
`date` argument of the log tools).

Trackers covered: meals, sleep, workouts, stress, meditation, gratitude,
focus, social, substances, reading, medication. (Expenses have their own
tools in expenses.py; hydration is a running counter and is not covered.)

Every row now carries a short persistent `id`. The log tools add one, and
the memory-journal entry they write gets a matching `log_id`, so the two stay
linked. Rows saved by older versions get an id the first time they are
listed, edited or deleted (once, in file order), and have no journal twin:
for those only the tracker row changes.

Editing or deleting a row also fixes its journal entry, so the life score,
"on this day" and the other journal-based tools agree with the tracker data.

No network call is made by this module.
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import clock
import storage
from storage import find_memory_ids, edit_memory_entry, delete_memory_entry

MAX_LIST = 200
MAX_GAP_DAYS = 366

# argument kinds: ("str",) ("lstr",) ("num",) ("int", lo, hi) ("bool",) ("list",)
S, LS, N, B, L = ("str",), ("lstr",), ("num",), ("bool",), ("list",)


def _i(lo: int, hi: int):
    return ("int", lo, hi)


def _g(row: Dict[str, Any], key: str, default: Any = "") -> Any:
    value = row.get(key)
    return default if value is None else value


# name -> {store, match (row -> bool), fields {arg: (row key, kind)},
#          label (row -> str), journal (row -> memory fields) or None}
TRACKERS: Dict[str, Dict[str, Any]] = {
    "meals": {
        "store": "nutrition",
        "match": lambda r: True,
        "fields": {"food": ("food", S), "meal_time": ("time", S), "calories": ("calories", N),
                   "protein_g": ("protein", N), "carbs_g": ("carbs", N), "fat_g": ("fat", N),
                   "notes": ("notes", S)},
        "label": lambda r: f"{_g(r, 'food', '?')} ({_g(r, 'calories', 0)} cal)",
        "journal": lambda r: {"content": _g(r, "food"), "calories": _g(r, "calories", 0),
                              "meal_time": _g(r, "time")},
    },
    "sleep": {
        "store": "sleep",
        "match": lambda r: True,
        "fields": {"hours": ("hours", ("num",)), "quality": ("quality", _i(1, 10)),
                   "bedtime": ("bedtime", S), "wake_time": ("wake_time", S), "notes": ("notes", S)},
        "label": lambda r: f"{_g(r, 'hours', 0)}h, quality {_g(r, 'quality', 5)}/10",
        "journal": lambda r: {"content": f"{_g(r, 'hours', 0)}h sleep", "hours": _g(r, "hours", 0),
                              "quality": _g(r, "quality", 5)},
    },
    "workouts": {
        "store": "fitness",
        "match": lambda r: True,
        "fields": {"workout_type": ("type", S), "duration_min": ("duration", N),
                   "intensity": ("intensity", S), "calories_burned": ("calories", N),
                   "notes": ("notes", S)},
        "label": lambda r: f"{_g(r, 'type', '?')} {_g(r, 'duration', 0)} min",
        "journal": lambda r: {"content": f"{_g(r, 'type')} {_g(r, 'duration', 0)}min",
                              "workout_type": _g(r, "type"), "duration": _g(r, "duration", 0)},
    },
    "stress": {
        "store": "mental",
        "match": lambda r: not r.get("type") and "score" in r,
        "fields": {"score": ("score", _i(1, 10)), "trigger": ("trigger", S), "notes": ("notes", S)},
        "label": lambda r: f"stress {_g(r, 'score', '?')}/10 - {_g(r, 'trigger', '')}".rstrip(" -"),
        "journal": lambda r: {"content": _g(r, "trigger") or "stress logged", "score": _g(r, "score", 5)},
    },
    "meditation": {
        "store": "mental",
        "match": lambda r: r.get("type") == "meditation",
        "fields": {"duration_min": ("duration", N), "notes": ("notes", S)},
        "label": lambda r: f"meditation {_g(r, 'duration', 0)} min",
        "journal": lambda r: {"content": f"{_g(r, 'duration', 0)}min meditation",
                              "duration": _g(r, "duration", 0)},
    },
    "gratitude": {
        "store": "mental",
        "match": lambda r: r.get("type") == "gratitude",
        "fields": {"items": ("items", L), "notes": ("notes", S)},
        "label": lambda r: "gratitude: " + ", ".join(str(x) for x in _g(r, "items", [])[:3]),
        "journal": lambda r: {"content": ", ".join(str(x) for x in _g(r, "items", [])[:3])},
    },
    "focus": {
        "store": "focus",
        "match": lambda r: True,
        "fields": {"duration_min": ("duration", N), "task": ("task", S), "completed": ("completed", B),
                   "distractions": ("distractions", _i(0, 1000)), "quality": ("quality", _i(1, 10))},
        "label": lambda r: f"{_g(r, 'duration', 0)} min on '{_g(r, 'task', '')}'",
        "journal": lambda r: {"content": _g(r, "task") or "focus session",
                              "duration": _g(r, "duration", 0), "quality": _g(r, "quality", 7)},
    },
    "social": {
        "store": "social",
        "match": lambda r: True,
        "fields": {"with_who": ("with_who", S), "quality": ("quality", _i(1, 10)),
                   "duration_min": ("duration_min", N), "notes": ("notes", S)},
        "label": lambda r: f"{_g(r, 'with_who', '?')}, quality {_g(r, 'quality', '?')}/10",
        "journal": lambda r: {"content": f"Time with {_g(r, 'with_who')}", "quality": _g(r, "quality", 5),
                              "duration_min": _g(r, "duration_min", 0)},
    },
    "substances": {
        "store": "substance",
        "match": lambda r: True,
        "fields": {"substance": ("substance", LS), "amount": ("amount", N), "unit": ("unit", S),
                   "notes": ("notes", S)},
        "label": lambda r: f"{_g(r, 'amount', 0)} {_g(r, 'unit', '')} {_g(r, 'substance', '?')}".replace("  ", " "),
        "journal": lambda r: {"content": f"{_g(r, 'substance')}: {_g(r, 'amount', 0)} {_g(r, 'unit')}".strip(),
                              "substance": _g(r, "substance"), "amount": _g(r, "amount", 0)},
    },
    "reading": {
        "store": "reading",
        "match": lambda r: True,
        "fields": {"title": ("title", S), "minutes": ("minutes", N), "pages": ("pages", N),
                   "total_pages": ("total_pages", N), "notes": ("notes", S)},
        "label": lambda r: f"'{_g(r, 'title', '?')}' {_g(r, 'minutes', 0)} min",
        "journal": lambda r: {"content": _g(r, "title"), "minutes": _g(r, "minutes", 0),
                              "pages": _g(r, "pages", 0)},
    },
    "medication": {
        "store": "medication",
        "match": lambda r: True,
        "fields": {"name": ("name", S), "taken": ("taken", B), "notes": ("notes", S)},
        "label": lambda r: f"{_g(r, 'name', '?')}: {'taken' if r.get('taken', True) else 'SKIPPED'}",
        "journal": None,
    },
}

# extra trackers that only the gap finder and undo know about
_GAP_ONLY = {"hydration": "hydration", "expenses": "spending"}


def tracker_names() -> List[str]:
    return list(TRACKERS)


def gap_tracker_names() -> List[str]:
    return list(TRACKERS) + list(_GAP_ONLY)


def _spec(tracker: Any) -> Dict[str, Any]:
    key = str(tracker or "").strip().lower()
    if key not in TRACKERS:
        raise ValueError(f"Unknown tracker '{tracker}'. Choose one of: {', '.join(TRACKERS)}.")
    return TRACKERS[key]


def new_log_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------- loading

def _rows_of(store: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in store if isinstance(r, dict)]


def _load_with_ids(store_name: str) -> List[Any]:
    """The whole store, giving id-less rows an id and saving once."""
    data = storage.load_store(store_name)
    if not isinstance(data, list):
        return []
    seen = {r.get("id") for r in _rows_of(data) if r.get("id")}
    changed = False
    for r in _rows_of(data):
        if not r.get("id"):
            new = new_log_id()
            while new in seen:
                new = new_log_id()
            seen.add(new)
            r["id"] = new
            changed = True
    if changed:
        storage.save_store(store_name, data)
    return data


# ---------------------------------------------------------------- listing

def list_logs(tracker: str, days: int = 7, limit: int = 20) -> List[Dict[str, Any]]:
    """Rows of one tracker, newest first. `days` looks back from the user's
    today (0 = today only). `limit` is capped at MAX_LIST. Raises ValueError
    for an unknown tracker."""
    spec = _spec(tracker)
    data = _load_with_ids(spec["store"])
    cutoff = clock.days_ago_str(max(0, int(days)))
    rows = [r for r in _rows_of(data) if spec["match"](r) and str(r.get("date", "")) >= cutoff]
    rows.sort(key=lambda r: str(r.get("date", "")), reverse=True)
    return rows[:max(1, min(int(limit), MAX_LIST))]


def describe(tracker: str, row: Dict[str, Any]) -> str:
    return _spec(tracker)["label"](row)


def format_log_list(tracker: str, rows: List[Dict[str, Any]], days: int) -> str:
    name = str(tracker).strip().lower()
    if not rows:
        return f"No {name} entries found in the last {days} days."
    lines = [f"{len(rows)} {name} entr{'y' if len(rows) == 1 else 'ies'}, newest first:"]
    for r in rows:
        lines.append(f"[id={r['id']}] {r.get('date', '?')}  {describe(name, r)}")
    return "\n".join(lines)


# ---------------------------------------------------------------- editing

def _coerce(arg: str, kind: Tuple, value: Any) -> Any:
    tag = kind[0]
    if tag in ("str", "lstr"):
        if not isinstance(value, str):
            raise ValueError(f"{arg} must be text.")
        text = value.strip()
        return text.lower() if tag == "lstr" else text
    if tag == "num":
        if isinstance(value, bool):
            raise ValueError(f"{arg} must be a number.")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{arg} must be a number, got {value!r}.") from None
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{arg} must be a number of 0 or more.")
        return int(number) if isinstance(value, int) or number.is_integer() else number
    if tag == "int":
        lo, hi = kind[1], kind[2]
        if isinstance(value, bool):
            raise ValueError(f"{arg} must be a whole number from {lo} to {hi}.")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{arg} must be a whole number from {lo} to {hi}, got {value!r}.") from None
        if not math.isfinite(number) or number != int(number) or not lo <= int(number) <= hi:
            raise ValueError(f"{arg} must be a whole number from {lo} to {hi}.")
        return int(number)
    if tag == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "yes", "1"):
            return True
        if isinstance(value, str) and value.strip().lower() in ("false", "no", "0"):
            return False
        raise ValueError(f"{arg} must be true or false.")
    if tag == "list":
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"{arg} must be a list of text items.")
        items = [x.strip() for x in value if x.strip()]
        if not items:
            raise ValueError(f"{arg} needs at least one item.")
        return items
    raise ValueError(f"{arg} has an unsupported type.")  # pragma: no cover


def editable_fields(tracker: str) -> List[str]:
    return list(_spec(tracker)["fields"]) + ["date"]


def edit_log(tracker: str, log_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Changes fields of one entry. `fields` uses the same argument names as
    the matching log tool (plus `date`). Returns the updated row, or None if
    the tracker has no entry with that id. Raises ValueError, changing
    nothing, for an unknown tracker, an unknown or invalid field, or an empty
    `fields`."""
    spec = _spec(tracker)
    if not isinstance(fields, dict) or not fields:
        raise ValueError("Nothing to change - give at least one field to edit "
                         f"({', '.join(editable_fields(tracker))}).")
    changes: Dict[str, Any] = {}
    for arg, value in fields.items():
        if arg == "date":
            if value is None or (isinstance(value, str) and not value.strip()):
                _bad_date()
            changes["date"] = clock.resolve_entry_date(value)
        elif arg in spec["fields"]:
            key, kind = spec["fields"][arg]
            changes[key] = _coerce(arg, kind, value)
        else:
            raise ValueError(f"'{arg}' cannot be edited for {tracker}. "
                             f"Editable: {', '.join(editable_fields(tracker))}.")

    data = _load_with_ids(spec["store"])
    for row in _rows_of(data):
        if row.get("id") != log_id or not spec["match"](row):
            continue
        row.update(changes)
        storage.save_store(spec["store"], data)
        if spec["journal"]:
            for mid in find_memory_ids("log_id", log_id):
                update = dict(spec["journal"](row))
                if "date" in changes:
                    update["timestamp"] = f"{changes['date']}T12:00:00Z"
                edit_memory_entry(mid, update)
        return row
    return None


def _bad_date():
    raise ValueError("date cannot be empty - write it as YYYY-MM-DD, for example 2026-10-09.")


# ---------------------------------------------------------------- deleting

def _remove_row(spec: Dict[str, Any], data: List[Any], index: int) -> Dict[str, Any]:
    row = data.pop(index)
    storage.save_store(spec["store"], data)
    for mid in find_memory_ids("log_id", row.get("id")):
        delete_memory_entry(mid)
    return row


def delete_log(tracker: str, log_id: str) -> Optional[Dict[str, Any]]:
    """Removes one entry (and its journal entry). Returns the removed row, or
    None if the tracker has no entry with that id."""
    spec = _spec(tracker)
    data = _load_with_ids(spec["store"])
    for i, row in enumerate(data):
        if isinstance(row, dict) and row.get("id") == log_id and spec["match"](row):
            return _remove_row(spec, data, i)
    return None


def delete_linked_row(memory_entry: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Called when a journal entry is deleted directly (the delete_entry tool):
    also removes the tracker row it was linked to. Returns (tracker, row) or
    None if the entry was not linked to a row."""
    expense_id = memory_entry.get("expense_id")
    if expense_id:
        import expenses
        row = expenses.delete_expense(expense_id, sync_journal=False)
        return ("expenses", row) if row else None
    log_id = memory_entry.get("log_id")
    if log_id:
        for name, spec in TRACKERS.items():
            data = _load_with_ids(spec["store"])
            for i, row in enumerate(data):
                if isinstance(row, dict) and row.get("id") == log_id and spec["match"](row):
                    data.pop(i)
                    storage.save_store(spec["store"], data)
                    return (name, row)
    return None


def undo_last_log(tracker: Optional[str] = None) -> Optional[Tuple[str, Dict[str, Any], str]]:
    """Deletes the most recently logged entry: of one tracker (the last row
    in its file; `expenses` is accepted too), or, with no tracker, of
    whichever tracker wrote the newest journal entry. Medication has no
    journal entry, so it is only reachable by name. Returns (tracker, row,
    description), or None if there is nothing to undo. Raises ValueError for
    an unknown tracker."""
    if tracker is not None and str(tracker).strip():
        key = str(tracker).strip().lower()
        if key == "expenses":
            import expenses
            spending = expenses._load_with_ids()
            if not spending:
                return None
            row = expenses.delete_expense(spending[-1]["id"])
            return ("expenses", row, expenses.describe(row)) if row else None
        spec = _spec(key)
        data = _load_with_ids(spec["store"])
        for i in range(len(data) - 1, -1, -1):
            if isinstance(data[i], dict) and spec["match"](data[i]):
                row = _remove_row(spec, data, i)
                return (key, row, spec["label"](row))
        return None

    import expenses
    for m in reversed(storage.get_all_memory()):
        if m.get("expense_id"):
            row = expenses.delete_expense(m["expense_id"])
            if row:
                return ("expenses", row, expenses.describe(row))
        elif m.get("log_id"):
            for name, spec in TRACKERS.items():
                data = _load_with_ids(spec["store"])
                for i, row in enumerate(data):
                    if isinstance(row, dict) and row.get("id") == m["log_id"] and spec["match"](row):
                        removed = _remove_row(spec, data, i)
                        return (name, removed, spec["label"](removed))
    return None


# ---------------------------------------------------------------- gaps

def _dates_of(tracker: str) -> set:
    if tracker in _GAP_ONLY:
        store_name = _GAP_ONLY[tracker]
        data = storage.load_store(store_name)
        if tracker == "hydration":
            data = data.get("log", []) if isinstance(data, dict) else []
        match: Callable[[Dict[str, Any]], bool] = lambda r: True  # noqa: E731
    else:
        spec = _spec(tracker)
        data = storage.load_store(spec["store"])
        match = spec["match"]
    if not isinstance(data, list):
        return set()
    return {str(r.get("date")) for r in _rows_of(data) if r.get("date") and match(r)}


def missing_days(tracker: str, days: int = 7) -> List[str]:
    """Dates (oldest first) among the last `days` COMPLETE days - today is
    not counted, it is not over yet - with no entry for this tracker. Raises
    ValueError for an unknown tracker."""
    key = str(tracker or "").strip().lower()
    if key not in TRACKERS and key not in _GAP_ONLY:
        raise ValueError(f"Unknown tracker '{tracker}'. Choose one of: {', '.join(gap_tracker_names())}.")
    n = max(1, min(int(days), MAX_GAP_DAYS))
    have = _dates_of(key)
    return [d for d in (clock.days_ago_str(k) for k in range(n, 0, -1)) if d not in have]


def format_missing_days(tracker: str, missing: List[str], days: int) -> str:
    key = str(tracker).strip().lower()
    n = max(1, min(int(days), MAX_GAP_DAYS))
    if not missing:
        return f"{key}: logged on every one of the last {n} complete days. Nothing to fill in."
    if len(missing) == n:
        # nothing at all in the window: could be an unused tracker
        return (f"{key}: nothing logged on any of the last {n} complete days "
                f"({missing[0]} to {missing[-1]}).")
    return (f"{key}: nothing logged on {len(missing)} of the last {n} complete days: "
            f"{', '.join(missing)}. Add them with the log tool's date argument.")


def gaps_overview(days: int = 7) -> str:
    """One line per tracker that has ever been used: how many of the last
    `days` complete days have nothing logged. Unused trackers are left out
    (an empty tracker is not a gap, it is just not in use)."""
    n = max(1, min(int(days), MAX_GAP_DAYS))
    lines = []
    for name in gap_tracker_names():
        if not _dates_of(name):
            continue
        missing = missing_days(name, n)
        if missing:
            shown = ", ".join(missing[-5:])
            more = f" (latest 5 shown)" if len(missing) > 5 else ""
            lines.append(f"- {name}: {len(missing)} of {n} days empty: {shown}{more}")
    if not lines:
        return f"No gaps: every tracker you use has an entry on each of the last {n} complete days."
    return (f"Days with nothing logged, last {n} complete days:\n" + "\n".join(lines)
            + "\nFill them in with the log tool's date argument.")
