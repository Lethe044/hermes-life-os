"""
Hermes Life OS - Subscriptions
================================
Recurring payments (streaming, gym, cloud storage, insurance, rent...): what
each one costs, when it renews, what they add up to per month and per year,
and which renewals are coming up. Budgets and spending tracking only see
money after it has been spent; subscriptions are the part of the budget you
can see coming.

Stored in subscriptions.json as a list of {"id", "name", "amount", "cycle",
"next_date", "category", "active", "notes", "created", "cancelled"} dicts.
`cycle` is weekly, monthly, quarterly or yearly. `next_date` is the next
renewal; once it is in the past the subscription is treated as renewed (the
date rolls forward by whole cycles, month-end safe) without anything being
written, and `pay_subscription` is how a payment is actually recorded: it logs
an expense in the subscription's category and moves `next_date` on.

Monthly equivalents: weekly x 52 / 12, quarterly / 3, yearly / 12. No network
call is made by this module.
"""

from __future__ import annotations

import math
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import clock


def _storage():
    """The storage module as it is right now (looked up on every call, so a
    reloaded storage - another profile, a test's temp HOME - is never missed)."""
    import storage
    return storage


CYCLES = ("weekly", "monthly", "quarterly", "yearly")
_CYCLE_ALIASES = {"week": "weekly", "month": "monthly", "year": "yearly", "annual": "yearly",
                  "annually": "yearly", "quarter": "quarterly", "yr": "yearly", "mo": "monthly",
                  "per month": "monthly", "per year": "yearly", "per week": "weekly"}
_MONTHS_PER_CYCLE = {"monthly": 1, "quarterly": 3, "yearly": 12}
MAX_NAME = 80
MAX_SUBS = 500
MAX_AMOUNT = 10_000_000


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def parse_cycle(value: Any) -> str:
    key = str(value or "monthly").strip().lower()
    key = _CYCLE_ALIASES.get(key, key)
    if key not in CYCLES:
        raise ValueError(f"cycle must be one of: {', '.join(CYCLES)}.")
    return key


def parse_amount(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("amount must be a number above 0.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"amount must be a number, got {value!r}.") from None
    if not math.isfinite(number) or number <= 0 or number > MAX_AMOUNT:
        raise ValueError("amount must be a number above 0.")
    return round(number, 2)


def _clean_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("the subscription needs a name.")
    name = " ".join(value.split())
    if len(name) > MAX_NAME:
        raise ValueError(f"the name can be at most {MAX_NAME} characters.")
    return name


def monthly_equivalent(amount: float, cycle: str) -> float:
    if cycle == "weekly":
        return amount * 52 / 12
    return amount / _MONTHS_PER_CYCLE[cycle]


def advance(day: date, cycle: str, steps: int = 1) -> date:
    """`day` moved `steps` renewal cycles forward (month-end safe)."""
    if cycle == "weekly":
        return day + timedelta(days=7 * steps)
    return clock.add_months(day, _MONTHS_PER_CYCLE[cycle] * steps)


def effective_next(sub: Dict[str, Any], today: Optional[date] = None) -> Optional[date]:
    """The next renewal on or after today: the stored next_date, rolled forward
    by whole cycles while it lies in the past. None if it is unreadable. For a
    monthly subscription anchored on the 31st the day sticks to the original
    anchor (Jan 31 -> Feb 28 -> Mar 31), because every step is measured from the
    stored date, not from the previous step."""
    today = today or clock.today()
    try:
        stored = clock.parse_day(sub.get("next_date"))
    except ValueError:
        return None
    if stored >= today:
        return stored
    cycle = sub.get("cycle", "monthly")
    if cycle not in CYCLES:
        return None
    k = 1
    while advance(stored, cycle, k) < today and k < 5000:
        k += 1
    return advance(stored, cycle, k)


# ------------------------------------------------------------------ storage

def _load() -> List[Dict[str, Any]]:
    subs = _storage().load_subscriptions()
    if not isinstance(subs, list):
        return []
    seen = {s.get("id") for s in subs if isinstance(s, dict) and s.get("id")}
    changed = False
    for s in subs:
        if isinstance(s, dict) and not s.get("id"):
            new = new_id()
            while new in seen:
                new = new_id()
            seen.add(new)
            s["id"] = new
            changed = True
    if changed:
        _storage().save_subscriptions(subs)
    return subs


def _rows(subs: List[Any]) -> List[Dict[str, Any]]:
    return [s for s in subs if isinstance(s, dict)]


def _resolve(subs: List[Dict[str, Any]], ref: Any) -> Dict[str, Any]:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("say which subscription (its id or name).")
    key = ref.strip().lower()
    pool = _rows(subs)
    for s in pool:
        if str(s.get("id", "")).lower() == key or str(s.get("name", "")).lower() == key:
            return s
    hits = [s for s in pool if key in str(s.get("name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no subscription matches '{ref.strip()}'. Use list_subscriptions to see them.")
    options = "; ".join(f"[id={s['id']}] {s.get('name', '')}" for s in hits[:5])
    raise ValueError(f"'{ref.strip()}' matches {len(hits)} subscriptions ({options}). Use the id.")


# ------------------------------------------------------------------ operations

def add_subscription(name: Any, amount: Any, cycle: Any = None, next_date: Any = None,
                     category: Any = None, notes: Any = None) -> Dict[str, Any]:
    """Adds a subscription. `next_date` defaults to one cycle from today and
    must be a valid YYYY-MM-DD. Raises ValueError, adding nothing, for a blank
    name, a bad amount/cycle/date, a duplicate active name, or when 500 exist."""
    clean = _clean_name(name)
    amt = parse_amount(amount)
    cyc = parse_cycle(cycle)
    if next_date is None or (isinstance(next_date, str) and not next_date.strip()):
        nxt = advance(clock.today(), cyc).isoformat()
    else:
        nxt = clock.parse_day(next_date).isoformat()
    cat = str(category).strip().lower() if isinstance(category, str) and category.strip() else "subscriptions"
    subs = _load()
    if len(subs) >= MAX_SUBS:
        raise ValueError(f"you already track {MAX_SUBS} subscriptions.")
    if any(s.get("active", True) and str(s.get("name", "")).lower() == clean.lower() for s in _rows(subs)):
        raise ValueError(f"'{clean}' already exists. Use update_subscription to change it.")
    sub = {"id": new_id(), "name": clean, "amount": amt, "cycle": cyc, "next_date": nxt, "category": cat,
           "active": True, "notes": notes.strip() if isinstance(notes, str) else "",
           "created": clock.today_str(), "cancelled": None}
    subs.append(sub)
    _storage().save_subscriptions(subs)
    return sub


def update_subscription(ref: Any, fields: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("nothing to change - give at least one of name, amount, cycle, next_date, "
                         "category or notes.")
    allowed = {"name", "amount", "cycle", "next_date", "category", "notes"}
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError(f"cannot change {', '.join(unknown)}. Editable: {', '.join(sorted(allowed))}.")
    changes: Dict[str, Any] = {}
    if "name" in fields:
        changes["name"] = _clean_name(fields["name"])
    if "amount" in fields:
        changes["amount"] = parse_amount(fields["amount"])
    if "cycle" in fields:
        changes["cycle"] = parse_cycle(fields["cycle"])
    if "next_date" in fields:
        changes["next_date"] = clock.parse_day(fields["next_date"]).isoformat()
    if "category" in fields:
        if not isinstance(fields["category"], str) or not fields["category"].strip():
            raise ValueError("category cannot be empty.")
        changes["category"] = fields["category"].strip().lower()
    if "notes" in fields:
        if not isinstance(fields["notes"], str):
            raise ValueError("notes must be text.")
        changes["notes"] = fields["notes"].strip()
    subs = _load()
    sub = _resolve(subs, ref)
    new_name = changes.get("name")
    if new_name and any(s is not sub and s.get("active", True) and str(s.get("name", "")).lower() == new_name.lower()
                        for s in _rows(subs)):
        raise ValueError(f"'{new_name}' already exists.")
    sub.update(changes)
    _storage().save_subscriptions(subs)
    return sub


def cancel_subscription(ref: Any) -> Dict[str, Any]:
    """Marks a subscription cancelled (kept for history, left out of totals).
    Raises ValueError if unknown/ambiguous or already cancelled."""
    subs = _load()
    sub = _resolve(subs, ref)
    if not sub.get("active", True):
        raise ValueError(f"'{sub.get('name')}' is already cancelled.")
    sub["active"] = False
    sub["cancelled"] = clock.today_str()
    _storage().save_subscriptions(subs)
    return sub


def resume_subscription(ref: Any, next_date: Any = None) -> Dict[str, Any]:
    subs = _load()
    sub = _resolve(subs, ref)
    if sub.get("active", True):
        raise ValueError(f"'{sub.get('name')}' is not cancelled.")
    if next_date is not None and not (isinstance(next_date, str) and not next_date.strip()):
        sub["next_date"] = clock.parse_day(next_date).isoformat()
    else:
        nxt = effective_next(sub)
        sub["next_date"] = (nxt or advance(clock.today(), sub.get("cycle", "monthly"))).isoformat()
    sub["active"] = True
    sub["cancelled"] = None
    _storage().save_subscriptions(subs)
    return sub


def delete_subscription(ref: Any) -> Dict[str, Any]:
    subs = _load()
    sub = _resolve(subs, ref)
    subs.remove(sub)
    _storage().save_subscriptions(subs)
    return sub


def mark_paid(ref: Any, paid_on: Optional[str] = None) -> Dict[str, Any]:
    """Moves a subscription's next_date one cycle past the renewal that was
    just paid (the stored date, rolled forward if it had passed unnoticed) and
    returns {"sub", "paid_for", "next"}. The caller records the expense."""
    subs = _load()
    sub = _resolve(subs, ref)
    if not sub.get("active", True):
        raise ValueError(f"'{sub.get('name')}' is cancelled - resume it first.")
    cycle = sub.get("cycle", "monthly")
    if cycle not in CYCLES:
        raise ValueError(f"'{sub.get('name')}' has an unknown cycle.")
    try:
        stored = clock.parse_day(sub.get("next_date"))
    except ValueError:
        raise ValueError(f"'{sub.get('name')}' has no readable renewal date - set one with update_subscription.") from None
    paid_for = stored
    nxt = advance(stored, cycle)
    today = clock.today()
    k = 1
    while nxt <= today and k < 5000:  # catching up after missed payments: next renewal lies ahead
        k += 1
        nxt = advance(stored, cycle, k)
    sub["next_date"] = nxt.isoformat()
    _storage().save_subscriptions(subs)
    return {"sub": sub, "paid_for": paid_for.isoformat(), "next": nxt.isoformat()}


# ------------------------------------------------------------------ reporting

def active() -> List[Dict[str, Any]]:
    return [s for s in _rows(_load()) if s.get("active", True)
            and isinstance(s.get("amount"), (int, float)) and s.get("cycle") in CYCLES]


def totals() -> Dict[str, Any]:
    subs = active()
    monthly = sum(monthly_equivalent(s["amount"], s["cycle"]) for s in subs)
    by_cat: Dict[str, float] = {}
    for s in subs:
        by_cat[s.get("category", "subscriptions")] = by_cat.get(s.get("category", "subscriptions"), 0.0) \
            + monthly_equivalent(s["amount"], s["cycle"])
    top = sorted(subs, key=lambda s: -monthly_equivalent(s["amount"], s["cycle"]))[:3]
    return {"count": len(subs), "monthly": monthly, "yearly": monthly * 12,
            "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])), "top": top}


def upcoming(days: int = 14) -> List[Dict[str, Any]]:
    """Active subscriptions renewing within `days` days (today included),
    soonest first, each as {"sub", "date", "in_days"}."""
    today = clock.today()
    horizon = today + timedelta(days=max(0, int(days)))
    out = []
    for s in active():
        nxt = effective_next(s, today)
        if nxt is not None and nxt <= horizon:
            out.append({"sub": s, "date": nxt.isoformat(), "in_days": (nxt - today).days})
    out.sort(key=lambda r: (r["date"], r["sub"].get("name", "")))
    return out


def renewal_nudge(days: int = 3) -> Optional[str]:
    due = upcoming(days)
    if not due:
        return None
    first = due[0]
    when = "today" if first["in_days"] == 0 else "tomorrow" if first["in_days"] == 1 else f"in {first['in_days']} days"
    msg = f"{first['sub']['name']} renews {when} ({first['sub']['amount']:g})"
    if len(due) > 1:
        msg += f", plus {len(due) - 1} more renewal{'s' if len(due) > 2 else ''} within {days} days"
    return msg + "."


def format_sub(s: Dict[str, Any]) -> str:
    state = "" if s.get("active", True) else f" (cancelled {s.get('cancelled') or '?'})"
    nxt = effective_next(s) if s.get("active", True) else None
    renews = f", renews {nxt.isoformat()}" if nxt else ""
    return (f"[id={s['id']}] {s.get('name', '?')}: {s.get('amount', 0):g} {s.get('cycle', '?')} "
            f"({monthly_equivalent(s['amount'], s['cycle']):.2f}/month, {s.get('category', 'subscriptions')})"
            f"{renews}{state}") if s.get("cycle") in CYCLES and isinstance(s.get("amount"), (int, float)) \
        else f"[id={s['id']}] {s.get('name', '?')} (incomplete entry)"


def format_list(include_cancelled: bool = False) -> str:
    subs = _rows(_load())
    if not include_cancelled:
        subs = [s for s in subs if s.get("active", True)]
    if not subs:
        return "No subscriptions tracked yet. Add one with add_subscription."
    subs.sort(key=lambda s: (not s.get("active", True), str(effective_next(s) or "9999-99-99")
                             if s.get("active", True) else "", str(s.get("name", "")).lower()))
    return f"{len(subs)} subscription(s):\n" + "\n".join(format_sub(s) for s in subs)


def format_summary(days: int = 14) -> str:
    t = totals()
    if not t["count"]:
        return "No active subscriptions. Add one with add_subscription."
    lines = [f"{t['count']} active subscription(s): {t['monthly']:.2f} per month, {t['yearly']:.2f} per year."]
    if len(t["by_category"]) > 1:
        lines.append("By category (per month): " + ", ".join(f"{c} {v:.2f}" for c, v in t["by_category"].items()))
    lines.append("Biggest: " + ", ".join(f"{s['name']} ({monthly_equivalent(s['amount'], s['cycle']):.2f}/month)"
                                         for s in t["top"]))
    up = upcoming(days)
    if up:
        lines.append(f"Renewing in the next {days} days:")
        for r in up:
            lines.append(f"  {r['date']} ({'today' if r['in_days'] == 0 else 'in ' + str(r['in_days']) + ' day(s)'}): "
                         f"{r['sub']['name']} {r['sub']['amount']:g}")
    else:
        lines.append(f"Nothing renews in the next {days} days.")
    return "\n".join(lines)


# ------------------------------------------------------------------ tool entry point

def run_tool(name: str, inp: Dict[str, Any], dispatch=None, **_ctx: Any) -> str:
    try:
        if name == "add_subscription":
            s = add_subscription(inp.get("name"), inp.get("amount"), inp.get("cycle"), inp.get("next_date"),
                                 inp.get("category"), inp.get("notes"))
            return "Subscription added: " + format_sub(s)
        if name == "list_subscriptions":
            return format_list(bool(inp.get("include_cancelled")))
        if name == "update_subscription":
            return "Subscription updated: " + format_sub(update_subscription(inp.get("subscription"), inp.get("fields")))
        if name == "cancel_subscription":
            s = cancel_subscription(inp.get("subscription"))
            return (f"Cancelled {s['name']}: it no longer counts in your totals "
                    f"({monthly_equivalent(s['amount'], s['cycle']):.2f} per month saved).")
        if name == "resume_subscription":
            return "Subscription resumed: " + format_sub(resume_subscription(inp.get("subscription"), inp.get("next_date")))
        if name == "delete_subscription":
            return f"Deleted subscription: {delete_subscription(inp.get('subscription'))['name']}. This can't be undone."
        if name == "get_subscription_summary":
            return format_summary(int(inp.get("days", 14)))
        if name == "pay_subscription":
            r = mark_paid(inp.get("subscription"))
            sub = r["sub"]
            line = ""
            if dispatch is not None and inp.get("log_expense", True):
                out = dispatch("log_expense", {"amount": sub["amount"], "category": sub.get("category", "subscriptions"),
                                               "notes": f"{sub['name']} subscription"})
                line = "\n" + str(out).splitlines()[0]
            return f"Recorded payment for {sub['name']} (renewal of {r['paid_for']}). Next renewal: {r['next']}.{line}"
    except (ValueError, TypeError) as e:
        verb = {"add_subscription": "Subscription not added", "list_subscriptions": "Cannot list",
                "get_subscription_summary": "Cannot summarize"}.get(name, "Subscription not changed")
        return f"{verb}: {e}"
    return f"Unknown subscription tool: {name}"
