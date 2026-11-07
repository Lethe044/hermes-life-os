"""
Hermes Life OS - Net Worth
============================
Keep a simple list of what you own (assets) and what you owe (liabilities)
and update each balance whenever you look at it. Hermes keeps the history of
every account, so it can show your net worth today, how it changed since the
previous update and a month-by-month trend. Amounts have no currency; they are
whatever you use. Balances of liabilities are stored as positive amounts.

Stored in networth.json as {"id", "name", "kind", "category", "balance",
"updated", "history"} dicts; `history` is a list of {"date", "balance"} with at
most one entry per day. No network call is made by this module.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

KINDS = ("asset", "liability")
MAX_ACCOUNTS = 100
MAX_HISTORY = 1500
MAX_AMOUNT = 1e12
STALE_DAYS = 35
CATEGORIES = ("cash", "savings", "investments", "property", "vehicle", "loan", "credit", "other")


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_networth(), lambda r: _storage().save_networth(r))


def _amount(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("balance must be a number.")
    if abs(value) > MAX_AMOUNT:
        raise ValueError("that balance is too large.")
    return round(float(value), 2)


def _valid(a: Any) -> bool:
    return isinstance(a, dict) and isinstance(a.get("name"), str) and a.get("kind") in KINDS \
        and isinstance(a.get("history"), list)


def set_balance(name: Any, balance: Any, kind: Any = None, category: Any = None) -> Dict[str, Any]:
    """Creates the account (kind is required then) or records a new balance
    for it. Returns {"account", "created", "previous"}."""
    clean = kit.clean_text(name, "name", 60)
    amount = _amount(balance)
    rows = _load()
    acct = next((a for a in rows if isinstance(a, dict) and str(a.get("name", "")).lower() == clean.lower()), None)
    today = clock.today_str()
    cat = kit.clean_text(category, "category", 30, required=False).lower() or None
    created, previous = False, None
    if acct is None:
        k = str(kind).strip().lower() if isinstance(kind, str) else ""
        if k not in KINDS:
            raise ValueError(f"'{clean}' is a new account: say whether it is an asset or a liability.")
        if len(rows) >= MAX_ACCOUNTS:
            raise ValueError(f"you already have {MAX_ACCOUNTS} accounts.")
        acct = {"id": kit.new_id(), "name": clean, "kind": k, "category": cat or "other", "balance": amount,
                "updated": today, "history": []}
        rows.append(acct)
        created = True
    else:
        if not _valid(acct):
            raise ValueError(f"the account '{clean}' is damaged. Run the doctor.")
        previous = acct.get("balance")
        if kind not in (None, "") and str(kind).strip().lower() != acct["kind"]:
            raise ValueError(f"'{acct['name']}' is a {acct['kind']}. Delete it first to change that.")
        if cat:
            acct["category"] = cat
    hist = [h for h in acct["history"] if isinstance(h, dict)]
    hist = [h for h in hist if h.get("date") != today] + [{"date": today, "balance": amount}]
    acct["history"] = sorted(hist, key=lambda h: str(h.get("date")))[-MAX_HISTORY:]
    acct["balance"], acct["updated"] = amount, today
    _storage().save_networth(rows)
    return {"account": acct, "created": created, "previous": previous}


def delete_account(ref: Any) -> Dict[str, Any]:
    rows = _load()
    acct = kit.resolve([a for a in rows if _valid(a)], ref, "account", "name", "get_net_worth")
    _storage().save_networth([a for a in rows if a is not acct])
    return acct


def _balance_on(acct: Dict[str, Any], day: str) -> Optional[float]:
    best = None
    for h in acct["history"]:
        if isinstance(h, dict) and isinstance(h.get("balance"), (int, float)) and str(h.get("date") or "") <= day:
            best = h["balance"]
    return best


def total_on(day: str) -> Optional[Dict[str, float]]:
    """Assets, liabilities and net worth on `day`, None when no account existed yet."""
    assets = liabilities = 0.0
    seen = False
    for a in _load():
        if not _valid(a):
            continue
        b = _balance_on(a, day)
        if b is None:
            continue
        seen = True
        if a["kind"] == "asset":
            assets += b
        else:
            liabilities += b
    return {"assets": assets, "liabilities": liabilities, "net": assets - liabilities} if seen else None


def trend(months: int = 6) -> List[Dict[str, Any]]:
    today = clock.today()
    points = []
    for i in range(months - 1, -1, -1):
        first = clock.add_months(today.replace(day=1), -i)
        end = today if i == 0 else clock.add_months(first, 1) - timedelta(days=1)
        t = total_on(end.isoformat())
        points.append({"label": end.strftime("%Y-%m") if i else f"{end.strftime('%Y-%m')} (today)", "total": t})
    return points


def days_since_update() -> Optional[int]:
    days = []
    for a in _load():
        if _valid(a):
            try:
                days.append((clock.today() - clock.parse_day(a.get("updated"))).days)
            except (ValueError, TypeError):
                continue
    return min(days) if days else None


def nudges(max_items: int = 1) -> List[str]:
    gap = days_since_update()
    if gap is None or gap < STALE_DAYS:
        return []
    return [f"Your net worth was last updated {gap} days ago. Record fresh balances with set_account_balance."][:max_items]


def _money(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def format_net_worth() -> str:
    accounts = [a for a in _load() if _valid(a)]
    if not accounts:
        return "No accounts yet. Add one with set_account_balance (kind asset or liability)."
    now = total_on(clock.today_str())
    lines = [f"Net worth: {_money(now['net'])} (assets {_money(now['assets'])}, liabilities {_money(now['liabilities'])})"]
    prior_days = sorted({h["date"] for a in accounts for h in a["history"] if isinstance(h, dict) and h.get("date") and h["date"] < clock.today_str()})
    if prior_days:
        before = total_on(prior_days[-1])
        diff = now["net"] - before["net"]
        lines.append(f"Change since {prior_days[-1]}: {'+' if diff > 0 else ''}{_money(diff)}")
    for kind, label in (("asset", "Assets"), ("liability", "Liabilities")):
        rows = sorted((a for a in accounts if a["kind"] == kind), key=lambda a: -float(a.get("balance") or 0))
        if rows:
            lines.append(f"{label}:")
            lines += [f"- {a['name']} ({a.get('category', 'other')}): {_money(float(a.get('balance') or 0))} [id={a.get('id', '?')}]" for a in rows]
    return "\n".join(lines)


def format_trend(months: int) -> str:
    pts = [p for p in trend(months)]
    known = [p for p in pts if p["total"]]
    if not known:
        return "No history yet. Record balances with set_account_balance."
    top = max(abs(p["total"]["net"]) for p in known) or 1
    lines = [f"Net worth, last {kit.plural(months, 'month')}:"]
    for p in pts:
        if not p["total"]:
            lines.append(f"- {p['label']}: no data")
            continue
        n = p["total"]["net"]
        bar = "#" * max(1, round(abs(n) / top * 20)) if n else ""
        lines.append(f"- {p['label']}: {_money(n)} {'-' if n < 0 else ''}{bar}")
    first, last = known[0]["total"]["net"], known[-1]["total"]["net"]
    lines.append(f"From {_money(first)} to {_money(last)} ({'+' if last - first > 0 else ''}{_money(last - first)}).")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "set_account_balance":
            r = set_balance(inp.get("name"), inp.get("balance"), inp.get("kind"), inp.get("category"))
            a = r["account"]
            head = f"Added {a['kind']} {a['name']}: {_money(a['balance'])}." if r["created"] else \
                f"{a['name']} is now {_money(a['balance'])} (was {_money(float(r['previous'] or 0))})."
            now = total_on(clock.today_str())
            return f"{head} Net worth: {_money(now['net'])}."
        if name == "get_net_worth":
            return format_net_worth()
        if name == "get_net_worth_trend":
            months = inp.get("months", 6)
            if isinstance(months, bool) or not isinstance(months, int) or not 2 <= months <= 36:
                raise ValueError("months must be a whole number from 2 to 36.")
            return format_trend(months)
        if name == "delete_account":
            return f"Deleted the account {delete_account(inp.get('account'))['name']}."
    except (ValueError, TypeError) as e:
        verb = {"set_account_balance": "Balance not saved", "get_net_worth_trend": "Cannot show the trend",
                "get_net_worth": "Cannot show net worth"}.get(name, "Account not deleted")
        return f"{verb}: {e}"
    return f"Unknown net worth tool: {name}"
