"""
Hermes Life OS - Debts and IOUs
=================================
Money you owe and money owed to you: "I borrowed 500 from Ali, due the 1st",
"Mehmet owes me 120 for dinner". Record partial payments as they happen, see
what is still open on each side, what is overdue and what is due soon.

Stored in debts.json as {"id", "who", "direction", "amount", "paid", "due",
"created", "notes", "payments", "settled"} dicts. `direction` is "owe" (you owe
them) or "owed" (they owe you); `paid` is always the sum of `payments` (a list
of {"date", "amount", "note"}); `settled` is the day the last of it was paid.
Amounts have no currency. No network call is made by this module.
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock

MAX_DEBTS = 500
MAX_PAYMENTS = 500
MAX_WHO = 60
MAX_NOTE = 160
MAX_AMOUNT = 1_000_000_000_000
NUDGE_DAYS = 3

_OWE = {"owe", "i_owe", "i owe", "borrowed", "debt", "payable", "to_pay", "to pay"}
_OWED = {"owed", "they_owe", "they owe", "lent", "loan", "loaned", "receivable", "to_receive", "to receive"}


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def fmt(amount: float) -> str:
    return f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"


def money(value: Any, label: str = "amount") -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a number above zero.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number above zero.") from None
    if not math.isfinite(number) or number > MAX_AMOUNT:
        raise ValueError(f"{label} is not a sensible number.")
    number = round(number, 2)
    if number <= 0:
        raise ValueError(f"{label} must be a number above zero.")
    return number


def parse_direction(value: Any) -> str:
    key = str(value or "").strip().lower()
    if key in _OWE:
        return "owe"
    if key in _OWED:
        return "owed"
    raise ValueError("direction must be 'owe' (you owe them) or 'owed' (they owe you).")


def _clean_who(value: Any) -> str:
    if not isinstance(value, str) or not " ".join(value.split()):
        raise ValueError("say who the other person is.")
    who = " ".join(value.split())
    if len(who) > MAX_WHO:
        raise ValueError(f"the name can be at most {MAX_WHO} characters.")
    return who


def _parse_due(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return clock.parse_day(value).isoformat()


def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_debts()
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
        _storage().save_debts(rows)
    return rows


def _rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict)]


def paid_of(debt: Dict[str, Any]) -> float:
    total = sum(p.get("amount", 0) for p in debt.get("payments") or []
                if isinstance(p, dict) and isinstance(p.get("amount"), (int, float)))
    return round(total, 2)


def remaining(debt: Dict[str, Any]) -> float:
    amount = debt.get("amount")
    if not isinstance(amount, (int, float)):
        return 0.0
    return round(max(0.0, amount - paid_of(debt)), 2)


def _sync(debt: Dict[str, Any]) -> None:
    debt["paid"] = paid_of(debt)
    if remaining(debt) <= 0:
        if not debt.get("settled"):
            debt["settled"] = clock.today_str()
    else:
        debt["settled"] = None


def _resolve(rows: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    """By id, or by the other person's name; a name that has several open debts
    needs the id. Settled debts are only found by id or when nothing else matches."""
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which debt (its id or the other person's name).")
    key = ref.strip().lower()
    pool = _rows(rows)
    for r in pool:
        if str(r.get("id", "")).lower() == key:
            return r
    hits = [r for r in pool if key in str(r.get("who", "")).lower()]
    open_hits = [r for r in hits if not r.get("settled")]
    hits = open_hits or hits
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no debt matches '{ref.strip()}'. Use get_debts to see them.")
    options = "; ".join(f"[id={r['id']}] {describe(r)}" for r in hits[:5])
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} debts ({options}). Use the id.")


# ------------------------------------------------------------------ operations

def add_debt(who: Any, amount: Any, direction: Any, due: Any = None, notes: Any = None) -> Dict[str, Any]:
    name = _clean_who(who)
    total = money(amount)
    d = parse_direction(direction)
    due_s = _parse_due(due)
    rows = _load()
    if len(rows) >= MAX_DEBTS:
        raise ValueError(f"you already have {MAX_DEBTS} debts - delete some settled ones first.")
    debt = {"id": new_id(), "who": name, "direction": d, "amount": total, "paid": 0.0, "due": due_s,
            "created": clock.today_str(), "notes": str(notes).strip()[:MAX_NOTE] if isinstance(notes, str) else "",
            "payments": [], "settled": None}
    rows.append(debt)
    _storage().save_debts(rows)
    return debt


def record_payment(ref: Any, amount: Any, date: Optional[str] = None, note: Any = None) -> Dict[str, Any]:
    """Returns {"debt", "paid", "newly_settled"}. Raises ValueError, changing
    nothing, for an unknown debt, a bad amount/date or a payment larger than
    what is still open."""
    value = money(amount)
    day = clock.resolve_entry_date(date)
    rows = _load()
    debt = _resolve(rows, ref)
    left = remaining(debt)
    if left <= 0:
        raise ValueError(f"the debt with {debt.get('who')} is already settled.")
    if value > left + 1e-9:
        raise ValueError(f"only {fmt(left)} is still open with {debt.get('who')}, so {fmt(value)} is too much.")
    if len(debt.get("payments") or []) >= MAX_PAYMENTS:
        raise ValueError(f"this debt already has {MAX_PAYMENTS} payments.")
    entry = {"date": day, "amount": value}
    if isinstance(note, str) and note.strip():
        entry["note"] = note.strip()[:MAX_NOTE]
    debt.setdefault("payments", []).append(entry)
    debt["payments"].sort(key=lambda p: str(p.get("date", "")))
    was = bool(debt.get("settled"))
    _sync(debt)
    _storage().save_debts(rows)
    return {"debt": debt, "paid": value, "newly_settled": bool(debt.get("settled")) and not was}


def update_debt(ref: Any, fields: Any) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change: give some fields (who, amount, due, notes).")
    unknown = [k for k in fields if k not in ("who", "amount", "due", "notes")]
    if unknown:
        raise ValueError(f"cannot change {', '.join(sorted(unknown))}. You can change who, amount, due and notes.")
    rows = _load()
    debt = _resolve(rows, ref)
    changes: Dict[str, Any] = {}
    if "who" in fields:
        changes["who"] = _clean_who(fields["who"])
    if "amount" in fields:
        new_amount = money(fields["amount"])
        if new_amount < paid_of(debt):
            raise ValueError(f"{fmt(paid_of(debt))} has already been paid, so the amount cannot be below that.")
        changes["amount"] = new_amount
    if "due" in fields:
        changes["due"] = _parse_due(fields["due"])
    if "notes" in fields:
        if not isinstance(fields["notes"], str):
            raise ValueError("notes must be text.")
        changes["notes"] = fields["notes"].strip()[:MAX_NOTE]
    debt.update(changes)
    _sync(debt)
    _storage().save_debts(rows)
    return debt


def delete_debt(ref: Any) -> Dict[str, Any]:
    rows = _load()
    debt = _resolve(rows, ref)
    _storage().save_debts([r for r in rows if r is not debt])
    return debt


def debts(include_settled: bool = False) -> List[Dict[str, Any]]:
    rows = [r for r in _rows(_load()) if isinstance(r.get("amount"), (int, float))]
    return rows if include_settled else [r for r in rows if remaining(r) > 0]


def totals() -> Dict[str, float]:
    owe = round(sum(remaining(r) for r in debts() if r.get("direction") == "owe"), 2)
    owed = round(sum(remaining(r) for r in debts() if r.get("direction") == "owed"), 2)
    return {"owe": owe, "owed": owed, "net": round(owed - owe, 2)}


def due_soon(days: int = NUDGE_DAYS) -> List[Dict[str, Any]]:
    """Open debts overdue or due within `days` days, as {"debt", "in_days"}
    (negative when overdue), the most overdue first."""
    today = clock.today()
    out = []
    for r in debts():
        due = r.get("due")
        if not due:
            continue
        try:
            left = (clock.parse_day(due) - today).days
        except ValueError:
            continue
        if left <= days:
            out.append({"debt": r, "in_days": left})
    out.sort(key=lambda x: (x["in_days"], str(x["debt"].get("who", "")).lower()))
    return out


def nudges(max_items: int = 1) -> List[str]:
    out = []
    for item in due_soon()[:max_items]:
        r, left = item["debt"], item["in_days"]
        when = (f"{-left} day(s) overdue" if left < 0 else "due today" if left == 0
                else "due tomorrow" if left == 1 else f"due in {left} days")
        who = r["who"]
        out.append(f"You owe {who} {fmt(remaining(r))}: {when}." if r.get("direction") == "owe"
                   else f"{who} owes you {fmt(remaining(r))}: {when}.")
    return out


# ------------------------------------------------------------------ formatting

def describe(debt: Dict[str, Any]) -> str:
    left = fmt(remaining(debt))
    who = debt.get("who", "?")
    return f"you owe {who} {left}" if debt.get("direction") == "owe" else f"{who} owes you {left}"


def format_debt(debt: Dict[str, Any]) -> str:
    amount = debt.get("amount") or 0
    line = f"{describe(debt)}"
    if paid_of(debt):
        line += f" (of {fmt(amount)}, {fmt(paid_of(debt))} paid)"
    if remaining(debt) <= 0:
        line = f"{'you paid' if debt.get('direction') == 'owe' else 'they paid'} {debt.get('who', '?')} in full ({fmt(amount)})"
        if debt.get("settled"):
            line += f", settled {debt['settled']}"
    elif debt.get("due"):
        try:
            left = (clock.parse_day(debt["due"]) - clock.today()).days
            tag = f"OVERDUE by {-left} day(s)" if left < 0 else "due today" if left == 0 else f"due in {left} day(s)"
            line += f", due {debt['due']} ({tag})"
        except ValueError:
            line += f", due {debt['due']}"
    return f"{line} [id={debt.get('id', '?')}]"


def format_all(rows: List[Dict[str, Any]], include_settled: bool = False) -> str:
    if not rows:
        return "No debts recorded." if include_settled else "No open debts. Add one with add_debt."
    owe = [r for r in rows if r.get("direction") == "owe"]
    owed = [r for r in rows if r.get("direction") != "owe"]
    key = lambda r: (bool(r.get("settled")), r.get("due") or "9999", str(r.get("who", "")).lower())  # noqa: E731
    t = totals()
    lines = [f"Open: you owe {fmt(t['owe'])}, you are owed {fmt(t['owed'])} "
             f"(net {'+' if t['net'] > 0 else ''}{fmt(t['net'])})."]
    if owe:
        lines.append("You owe:")
        lines += [f"- {format_debt(r)}" for r in sorted(owe, key=key)]
    if owed:
        lines.append("Owed to you:")
        lines += [f"- {format_debt(r)}" for r in sorted(owed, key=key)]
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_debt":
            return "Debt added: " + format_debt(add_debt(inp.get("who"), inp.get("amount"), inp.get("direction"),
                                                         inp.get("due"), inp.get("notes")))
        if name == "record_debt_payment":
            r = record_payment(inp.get("debt"), inp.get("amount"), inp.get("date"), inp.get("note"))
            msg = f"Recorded {fmt(r['paid'])}. " + format_debt(r["debt"])
            if r["newly_settled"]:
                msg += "\nFully settled."
            return msg
        if name == "get_debts":
            inc = bool(inp.get("include_settled", False))
            return format_all(debts(inc), inc)
        if name == "update_debt":
            return "Debt updated: " + format_debt(update_debt(inp.get("debt"), inp.get("fields")))
        if name == "delete_debt":
            return f"Deleted debt with {delete_debt(inp.get('debt')).get('who')}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_debt": "Debt not added", "record_debt_payment": "Not recorded",
                "get_debts": "Cannot show debts"}.get(name, "Debt not changed")
        return f"{verb}: {e}"
    return f"Unknown debt tool: {name}"
