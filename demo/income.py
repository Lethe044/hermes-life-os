"""
Hermes Life OS - Income and cash flow
=======================================
Hermes has long tracked what you spend. This adds what comes in: log a salary,
a refund or a side job, then ask how each month went: income, spending, what
was left over and the share of income you kept (the savings rate).

Stored in income.json as {"id", "date", "amount", "source", "notes"} dicts.
Income entries are a tracker like the others: they can be listed, edited,
deleted and backdated, and are mirrored in the memory journal (type "income").
Spending comes from the existing expense log; amounts have no currency. No
network call is made by this module.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

import clock

MAX_ROWS = 20000
MAX_SOURCE = 60
MAX_NOTES = 200
MAX_AMOUNT = 1_000_000_000_000
DEFAULT_SOURCE = "income"
MAX_MONTHS = 24


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def fmt(amount: float) -> str:
    return f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"


def clean_amount(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError("amount must be a number above zero.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("amount must be a number above zero.") from None
    if not math.isfinite(number) or number > MAX_AMOUNT:
        raise ValueError("amount is not a sensible number.")
    number = round(number, 2)
    if number <= 0:
        raise ValueError("amount must be a number above zero.")
    return number


def clean_source(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return DEFAULT_SOURCE
    if not isinstance(value, str):
        raise ValueError("source must be text, for example salary.")
    text = " ".join(value.split())
    if len(text) > MAX_SOURCE:
        raise ValueError(f"source can be at most {MAX_SOURCE} characters.")
    return text


def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_income()
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
        _storage().save_income(rows)
    return rows


def entries() -> List[Dict[str, Any]]:
    """Usable entries (a date and a positive number), oldest first."""
    out = [r for r in _load() if isinstance(r, dict) and isinstance(r.get("date"), str)
           and isinstance(r.get("amount"), (int, float)) and not isinstance(r.get("amount"), bool)
           and r["amount"] > 0]
    out.sort(key=lambda r: r["date"])
    return out


def build_entry(amount: Any, source: Any = None, date: Optional[str] = None, notes: Any = None,
                row_id: Optional[str] = None) -> Dict[str, Any]:
    row: Dict[str, Any] = {"id": row_id or new_id(), "date": date or clock.today_str(),
                           "amount": clean_amount(amount), "source": clean_source(source)}
    if isinstance(notes, str) and notes.strip():
        row["notes"] = notes.strip()[:MAX_NOTES]
    return row


def log_income(amount: Any, source: Any = None, date: Optional[str] = None, notes: Any = None,
               row_id: Optional[str] = None) -> Dict[str, Any]:
    row = build_entry(amount, source, date, notes, row_id)
    rows = _load()
    if len(rows) >= MAX_ROWS:
        raise ValueError(f"income.json already holds {MAX_ROWS} entries - export and prune old ones first.")
    rows.append(row)
    _storage().save_income(rows)
    return row


def describe(row: Dict[str, Any]) -> str:
    amount = row.get("amount")
    shown = fmt(amount) if isinstance(amount, (int, float)) else "?"
    return f"Income {shown} ({row.get('source') or DEFAULT_SOURCE})"


def journal_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"content": describe(row), "amount": row.get("amount"), "source": row.get("source")}


# ------------------------------------------------------------------ analysis

def _month_back(month: str, back: int) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    index = year * 12 + (mon - 1) - back
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_totals(month: str) -> Dict[str, Any]:
    """{"month", "income", "spent", "net", "savings_rate" (percent or None
    without income), "sources": {source: total}} for one YYYY-MM."""
    income = 0.0
    sources: Dict[str, float] = defaultdict(float)
    for r in entries():
        if r["date"].startswith(month):
            income += r["amount"]
            sources[str(r.get("source") or DEFAULT_SOURCE).lower()] += r["amount"]
    spent = 0.0
    try:
        spending = _storage().load_spending()
    except Exception:  # noqa: BLE001
        spending = []
    for s in spending if isinstance(spending, list) else []:
        if isinstance(s, dict) and str(s.get("date", "")).startswith(month) \
                and isinstance(s.get("amount"), (int, float)) and not isinstance(s.get("amount"), bool):
            spent += s["amount"]
    income, spent = round(income, 2), round(spent, 2)
    net = round(income - spent, 2)
    return {"month": month, "income": income, "spent": spent, "net": net,
            "savings_rate": round(100 * net / income, 1) if income > 0 else None,
            "sources": {k: round(v, 2) for k, v in sources.items()}}


def cash_flow(months: Any = 3) -> List[Dict[str, Any]]:
    """The last `months` calendar months including the current one, newest first."""
    try:
        n = int(months)
    except (TypeError, ValueError):
        raise ValueError("months must be a whole number.") from None
    if not 1 <= n <= MAX_MONTHS:
        raise ValueError(f"months must be between 1 and {MAX_MONTHS}.")
    current = clock.month_str()
    return [month_totals(_month_back(current, i)) for i in range(n)]


def format_cash_flow(rows: List[Dict[str, Any]]) -> str:
    current = clock.month_str()
    if not any(r["income"] or r["spent"] for r in rows):
        return f"No income or spending logged in the last {len(rows)} month(s)."
    lines = [f"Cash flow, last {len(rows)} month(s):"]
    for r in rows:
        tag = " (so far)" if r["month"] == current else ""
        if not r["income"] and not r["spent"]:
            lines.append(f"- {r['month']}{tag}: nothing logged.")
            continue
        net = f"+{fmt(r['net'])}" if r["net"] > 0 else fmt(r["net"])
        rate = f", kept {r['savings_rate']:g}% of income" if r["savings_rate"] is not None else ", no income logged"
        lines.append(f"- {r['month']}{tag}: income {fmt(r['income'])}, spent {fmt(r['spent'])}, "
                     f"net {net}{rate}.")
    done = [r for r in rows if r["month"] != current and (r["income"] or r["spent"])]
    if len(done) >= 2:
        avg = sum(r["net"] for r in done) / len(done)
        lines.append(f"Average net of the {len(done)} finished month(s): {'+' if avg > 0 else ''}{fmt(round(avg, 2))}.")
    total: Dict[str, float] = defaultdict(float)
    for r in rows:
        for k, v in r["sources"].items():
            total[k] += v
    if total:
        top = sorted(total.items(), key=lambda kv: -kv[1])[:3]
        lines.append("Income sources: " + ", ".join(f"{k} {fmt(round(v, 2))}" for k, v in top) + ".")
    if rows[0]["spent"] > rows[0]["income"] > 0:
        lines.append(f"This month you have spent more than you earned so far ({fmt(rows[0]['spent'])} vs "
                     f"{fmt(rows[0]['income'])}).")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], log_date: Optional[str] = None,
             log_stamp: Optional[Dict[str, str]] = None, log_id: Optional[str] = None, **_ctx: Any) -> str:
    from storage import write_memory
    try:
        if name == "log_income":
            row = log_income(inp.get("amount"), inp.get("source"), log_date, inp.get("notes"), log_id)
            write_memory({**(log_stamp or {}), "log_id": row["id"], "type": "income", **journal_fields(row)})
            month = month_totals(row["date"][:7])
            so_far = " so far" if row["date"][:7] == clock.month_str() else ""
            return (f"Logged: {describe(row)} on {row['date']} [id={row['id']}]\n"
                    f"{row['date'][:7]}{so_far}: income {fmt(month['income'])}, spent {fmt(month['spent'])}, "
                    f"net {fmt(month['net'])}.")
        if name == "get_cash_flow":
            return format_cash_flow(cash_flow(inp.get("months", 3)))
    except (ValueError, TypeError) as e:
        return {"log_income": "Not logged", "get_cash_flow": "Cannot show cash flow"}.get(name, "Error") + f": {e}"
    return f"Unknown income tool: {name}"
