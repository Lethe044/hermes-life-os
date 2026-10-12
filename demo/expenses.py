"""
Hermes Life OS - Expenses
==========================
Until v1.39.0 an expense could be logged but never corrected: a typo in the
amount or a double entry stayed in the spending totals and the budgets for
good. This module adds list / update / delete on top of spending.json.

Every expense now carries a short persistent `id` (log_expense adds one, and
the journal entry it writes gets `expense_id`, so the two stay linked).
Expenses saved by older versions have no id; the first list/update/delete
call gives them one (once, in file order) and saves the file.

Changing or deleting an expense also fixes its memory-journal entry, so the
life score, "on this day" and the other journal-based tools agree with the
spending data. Entries from before the link existed have no journal twin and
only the spending row changes.

No network call is made by this module.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import clock
from storage import (load_spending, save_spending, find_memory_ids,
                     edit_memory_entry, delete_memory_entry)

MAX_LIST = 200


def new_expense_id() -> str:
    return uuid.uuid4().hex[:8]


def _load_with_ids() -> List[Dict[str, Any]]:
    """The spending list, giving id-less (legacy) rows an id and saving once."""
    spending = load_spending()
    changed = False
    seen = {e.get("id") for e in spending if isinstance(e, dict) and e.get("id")}
    for e in spending:
        if isinstance(e, dict) and not e.get("id"):
            new = new_expense_id()
            while new in seen:
                new = new_expense_id()
            seen.add(new)
            e["id"] = new
            changed = True
    if changed:
        save_spending(spending)
    return spending


def list_expenses(days: int = 30, category: Optional[str] = None,
                  limit: int = 20) -> List[Dict[str, Any]]:
    """Newest first. `days` looks back from the user's today (0 = today only);
    `category` matches case-insensitively; `limit` is capped at MAX_LIST."""
    spending = _load_with_ids()
    cutoff = clock.days_ago_str(max(0, int(days)))
    cat = category.strip().lower() if isinstance(category, str) and category.strip() else None
    rows = [e for e in spending
            if isinstance(e, dict) and str(e.get("date", "")) >= cutoff
            and (cat is None or str(e.get("category", "")).lower() == cat)]
    rows.sort(key=lambda e: str(e.get("date", "")), reverse=True)  # stable: keeps file order within a day
    return rows[:max(1, min(int(limit), MAX_LIST))]


def format_expense_list(rows: List[Dict[str, Any]], days: int) -> str:
    if not rows:
        return f"No expenses found in the last {days} days."
    lines = [f"{len(rows)} expense(s), newest first:"]
    for e in rows:
        note = f" - {e['notes']}" if e.get("notes") else ""
        lines.append(f"[id={e['id']}] {e.get('date', '?')}  {float(e.get('amount', 0)):.2f}  "
                     f"{e.get('category', 'uncategorized')}{note}")
    return "\n".join(lines)


def _journal_text(e: Dict[str, Any]) -> str:
    return f"{e.get('category', 'uncategorized')}: {e.get('amount', 0)}"


def update_expense(expense_id: str, amount=None, category=None, notes=None,
                   date=None) -> Optional[Dict[str, Any]]:
    """Edits an expense. Arguments left as None stay unchanged. Raises
    ValueError, changing nothing, for an unusable amount (not a finite number
    above 0), a blank category or an invalid date (same rules as backdating).
    Returns the updated row, or None if no expense has that id."""
    new_amount = None
    if amount is not None:
        try:
            new_amount = float(amount)
        except (TypeError, ValueError):
            raise ValueError(f"amount must be a number, got {amount!r}.") from None
        if not new_amount > 0 or new_amount == float("inf"):
            raise ValueError("amount must be a number above 0.")
    if category is not None and not str(category).strip():
        raise ValueError("category cannot be empty.")
    new_date = clock.resolve_entry_date(date) if date is not None else None

    spending = _load_with_ids()
    for e in spending:
        if e.get("id") != expense_id:
            continue
        if new_amount is not None:
            e["amount"] = new_amount
        if category is not None:
            e["category"] = str(category).strip().lower()
        if notes is not None:
            e["notes"] = str(notes)
        if new_date is not None:
            e["date"] = new_date
        save_spending(spending)
        for mid in find_memory_ids("expense_id", expense_id):
            fields: Dict[str, Any] = {"content": _journal_text(e), "amount": e.get("amount", 0),
                                      "category": e.get("category", "uncategorized")}
            if new_date is not None:
                fields["timestamp"] = f"{new_date}T12:00:00Z"
            edit_memory_entry(mid, fields)
        return e
    return None


def describe(e: Dict[str, Any]) -> str:
    return f"{float(e.get('amount', 0)):.2f} {e.get('category', 'uncategorized')}"


def delete_expense(expense_id: str, sync_journal: bool = True) -> Optional[Dict[str, Any]]:
    """Removes an expense (and its journal entry, unless `sync_journal` is
    False because the caller is deleting that entry itself). Returns the
    removed row, or None if no expense has that id."""
    spending = _load_with_ids()
    for i, e in enumerate(spending):
        if e.get("id") == expense_id:
            del spending[i]
            save_spending(spending)
            if sync_journal:
                for mid in find_memory_ids("expense_id", expense_id):
                    delete_memory_entry(mid)
            return e
    return None
