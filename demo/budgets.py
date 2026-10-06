"""
Hermes Life OS - Budgets
=========================
Forward-looking monthly spending limits per category, distinct from the
existing retrospective spending tools (log_expense, get_spending_summary,
get_spending_trends) which only report what already happened. A budget
is a per-category monthly limit (e.g. "groceries: 400") that is compared
against the current calendar month's actual spending (via load_spending)
to answer "am I on track, over, or under for this category this month?"

Stored in budgets.json (via load_budgets/save_budgets) as a list of
{"category", "limit"} dicts, one per category (case-insensitive, unique
per category - setting a budget for an existing category overwrites its
limit rather than adding a duplicate). Pure local arithmetic, no network
call.

On top of the basic status check this module also offers a month-end
forecast (compute_budget_forecast), a history of completed months
(compute_budget_history), a view of spending that has no budget at all
(compute_unbudgeted_spending) and one-line alerts for the proactive
nudge check (budget_alerts). Spending categories are matched to budgets
case-insensitively, so "Groceries" logged by the agent still counts
against a "groceries" budget.
"""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Any, Dict, List, Optional

from storage import load_budgets, save_budgets, load_spending


def set_budget(category: str, limit: float) -> Dict[str, Any]:
    """Creates or updates the monthly limit for `category` (case
    preserved from the first time it's set, matched case-insensitively
    on later calls). Returns the saved {"category", "limit"} entry."""
    budgets = load_budgets()
    for b in budgets:
        if b.get("category", "").lower() == category.lower():
            b["limit"] = limit
            save_budgets(budgets)
            return b
    entry = {"category": category, "limit": limit}
    budgets.append(entry)
    save_budgets(budgets)
    return entry


def delete_budget(category: str) -> bool:
    """Removes the budget for `category` (case-insensitive). Returns
    True if one was found and removed, False otherwise."""
    budgets = load_budgets()
    remaining = [b for b in budgets if b.get("category", "").lower() != category.lower()]
    if len(remaining) == len(budgets):
        return False
    save_budgets(remaining)
    return True


def list_budgets() -> List[Dict[str, Any]]:
    """Returns every saved budget as a list of {"category", "limit"},
    sorted alphabetically by category."""
    return sorted(load_budgets(), key=lambda b: b.get("category", "").lower())


def _spent_by_category(month_prefix: str) -> Dict[str, float]:
    """Total spending per category (keyed by lower-cased category name,
    so "Groceries" and "groceries" are one bucket) for the calendar
    month identified by `month_prefix` ("YYYY-MM")."""
    spent: Dict[str, float] = {}
    for s in load_spending():
        date = s.get("date", "")
        if not date.startswith(month_prefix):
            continue
        category = str(s.get("category") or "uncategorized").lower()
        spent[category] = spent.get(category, 0.0) + s.get("amount", 0)
    return spent


def _current_month_spent_by_category() -> Dict[str, float]:
    return _spent_by_category(datetime.utcnow().strftime("%Y-%m"))


def compute_budget_status(category: Optional[str] = None,
                          today: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Returns a list of {"category", "limit", "spent", "remaining",
    "pct_used", "over"} for every saved budget (or just the one named
    `category`, case-insensitive, if given), comparing each against
    actual spending logged so far in the current calendar month. A
    budget with no spending at all this month still appears, with
    spent=0, so a quiet category is visible rather than silently
    dropped.
    """
    budgets = load_budgets()
    if category is not None:
        budgets = [b for b in budgets if b.get("category", "").lower() == category.lower()]
    spent_by_category = _spent_by_category(_now(today).strftime("%Y-%m"))

    results = []
    for b in sorted(budgets, key=lambda b: b.get("category", "").lower()):
        cat = b.get("category", "")
        limit = b.get("limit", 0)
        spent = round(spent_by_category.get(cat.lower(), 0.0), 2)
        remaining = round(limit - spent, 2)
        pct_used = round((spent / limit * 100.0), 1) if limit else (100.0 if spent else 0.0)
        results.append({
            "category": cat, "limit": limit, "spent": spent,
            "remaining": remaining, "pct_used": pct_used, "over": spent > limit,
        })
    return results


def format_budget_status(results: List[Dict[str, Any]]) -> str:
    """Turns compute_budget_status()'s output into a friendly
    multi-line summary, most-over-budget first."""
    if not results:
        return "No budgets set yet."

    lines = ["Budget status for this month:"]
    ordered = sorted(results, key=lambda r: -r["pct_used"])
    for r in ordered:
        flag = " OVER BUDGET" if r["over"] else ""
        lines.append(
            f"- {r['category']}: {r['spent']} / {r['limit']} spent "
            f"({r['pct_used']}%, {r['remaining']} remaining){flag}"
        )
    return "\n".join(lines)


def format_budget_list(budgets: List[Dict[str, Any]]) -> str:
    """Turns list_budgets()'s output into a friendly multi-line
    summary of the raw limits (no spending data)."""
    if not budgets:
        return "No budgets set yet."
    lines = ["Monthly budgets:"]
    for b in budgets:
        lines.append(f"- {b.get('category', '?')}: {b.get('limit', 0)} / month")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Forecast, history and unbudgeted spending
# ---------------------------------------------------------------------------

EARLY_MONTH_DAYS = 5  # projections made before this day of the month are flagged as rough


def _now(today: Optional[datetime]) -> datetime:
    return today if today is not None else datetime.utcnow()


def compute_budget_forecast(category: Optional[str] = None,
                            today: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Projects each budget's month-end spending from the pace so far
    this calendar month (spent / day-of-month * days-in-month) and says
    how much can still be spent per remaining day to stay within the
    limit. Returns a list of {"category", "limit", "spent", "projected",
    "remaining", "days_left", "daily_allowance", "status",
    "low_confidence"} where status is "over" (already past the limit),
    "will_exceed" (on pace to pass it) or "on_track". `today` is
    injectable for deterministic tests. `low_confidence` is True in the
    first few days of the month, when a pace estimate is mostly noise.
    """
    now = _now(today)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day = max(now.day, 1)
    days_left = days_in_month - day

    budgets = load_budgets()
    if category is not None:
        budgets = [b for b in budgets if b.get("category", "").lower() == category.lower()]
    spent_by_category = _spent_by_category(now.strftime("%Y-%m"))

    results = []
    for b in sorted(budgets, key=lambda b: b.get("category", "").lower()):
        cat = b.get("category", "")
        limit = b.get("limit", 0)
        spent = round(spent_by_category.get(cat.lower(), 0.0), 2)
        remaining = round(limit - spent, 2)
        projected = round(spent / day * days_in_month, 2)
        if spent > limit:
            status = "over"
        elif projected > limit:
            status = "will_exceed"
        else:
            status = "on_track"
        if remaining > 0 and days_left > 0:
            daily_allowance = round(remaining / days_left, 2)
        elif remaining > 0:
            daily_allowance = remaining
        else:
            daily_allowance = 0.0
        results.append({
            "category": cat, "limit": limit, "spent": spent, "projected": projected,
            "remaining": remaining, "days_left": days_left,
            "daily_allowance": daily_allowance, "status": status,
            "low_confidence": now.day < EARLY_MONTH_DAYS,
        })
    return results


_STATUS_RANK = {"over": 0, "will_exceed": 1, "on_track": 2}


def format_budget_forecast(results: List[Dict[str, Any]]) -> str:
    """Turns compute_budget_forecast()'s output into a friendly
    multi-line summary, worst status first."""
    if not results:
        return "No budgets set yet."

    lines = ["Budget forecast for this month:"]
    ordered = sorted(results, key=lambda r: (_STATUS_RANK.get(r["status"], 9), r["category"].lower()))
    for r in ordered:
        if r["status"] == "over":
            tail = f"already OVER by {abs(r['remaining'])}"
        elif r["status"] == "will_exceed":
            tail = (f"on pace for {r['projected']} (limit {r['limit']}) - "
                    f"keep under {r['daily_allowance']}/day to stay within it")
        else:
            tail = (f"on track, projected {r['projected']} of {r['limit']} "
                    f"({r['daily_allowance']}/day available)")
        lines.append(f"- {r['category']}: {r['spent']} spent so far, {tail}")
    if any(r.get("low_confidence") for r in results):
        lines.append("Note: it's early in the month, so these projections are rough.")
    return "\n".join(lines)


def _shift_month(year: int, month: int, delta: int) -> "tuple[int, int]":
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def compute_budget_history(months: int = 3,
                           today: Optional[datetime] = None) -> Dict[str, Any]:
    """How each budgeted category did in the last `months` COMPLETED
    calendar months (the current, unfinished month is covered by
    compute_budget_status instead). `months` is clamped to 1..24.
    Budgets are not versioned, so every month is measured against the
    CURRENT limit. Returns {"months": [labels oldest-first], "categories":
    [{"category", "limit", "history": [{"month", "spent", "over"}],
    "months_over", "avg_spent"}]}.
    """
    months = max(1, min(int(months), 24))
    now = _now(today)
    labels = []
    for back in range(months, 0, -1):
        y, m = _shift_month(now.year, now.month, -back)
        labels.append(f"{y:04d}-{m:02d}")
    spent_per_month = {label: _spent_by_category(label) for label in labels}

    categories = []
    for b in sorted(load_budgets(), key=lambda b: b.get("category", "").lower()):
        cat = b.get("category", "")
        limit = b.get("limit", 0)
        history = []
        for label in labels:
            spent = round(spent_per_month[label].get(cat.lower(), 0.0), 2)
            history.append({"month": label, "spent": spent, "over": spent > limit})
        categories.append({
            "category": cat, "limit": limit, "history": history,
            "months_over": sum(1 for h in history if h["over"]),
            "avg_spent": round(sum(h["spent"] for h in history) / months, 2),
        })
    return {"months": labels, "categories": categories}


def format_budget_history(result: Dict[str, Any]) -> str:
    """Turns compute_budget_history()'s output into a friendly summary."""
    if not result.get("categories"):
        return "No budgets set yet."

    n = len(result["months"])
    lines = [f"Budget history, last {n} completed month(s) (measured against current limits):"]
    for c in result["categories"]:
        per_month = ", ".join(
            f"{h['month']}: {h['spent']}{' (over)' if h['over'] else ''}" for h in c["history"]
        )
        lines.append(
            f"- {c['category']} (limit {c['limit']}): over in {c['months_over']}/{n} months, "
            f"avg {c['avg_spent']} - {per_month}"
        )
    return "\n".join(lines)


def compute_unbudgeted_spending(today: Optional[datetime] = None) -> Dict[str, Any]:
    """This month's spending in categories that have NO budget, so money
    leaking outside the plan is visible. Returns {"total", "categories":
    [{"category", "spent"}]} sorted biggest first. Category names are
    reported lower-cased (spending categories are matched
    case-insensitively)."""
    now = _now(today)
    budgeted = {b.get("category", "").lower() for b in load_budgets()}
    spent = _spent_by_category(now.strftime("%Y-%m"))
    rows = [
        {"category": cat, "spent": round(amount, 2)}
        for cat, amount in spent.items()
        if cat not in budgeted and amount
    ]
    rows.sort(key=lambda r: (-r["spent"], r["category"]))
    return {"total": round(sum(r["spent"] for r in rows), 2), "categories": rows}


def format_unbudgeted_spending(result: Dict[str, Any]) -> str:
    """Turns compute_unbudgeted_spending()'s output into a summary."""
    if not result.get("categories"):
        return "No spending outside your budgets this month."
    lines = [f"Spending outside any budget this month: {result['total']} total"]
    for r in result["categories"]:
        lines.append(f"- {r['category']}: {r['spent']}")
    return "\n".join(lines)


def budget_alerts(threshold_pct: float = 80.0,
                  today: Optional[datetime] = None) -> List[str]:
    """One-line warnings for budgets that are over their limit or have
    used at least `threshold_pct` of it so far this month. Empty list
    when everything is comfortable (used by nudges.generate_nudges)."""
    alerts = []
    forecast = {f["category"]: f for f in compute_budget_forecast(today=today)}
    for r in compute_budget_status(today=today):
        if r["over"]:
            alerts.append(
                f"Budget '{r['category']}' is over: {r['spent']} spent of {r['limit']} this month."
            )
        elif r["limit"] and r["pct_used"] >= threshold_pct:
            f = forecast.get(r["category"], {})
            alerts.append(
                f"Budget '{r['category']}' is {r['pct_used']}% used ({r['remaining']} left) "
                f"with {f.get('days_left', '?')} days to go."
            )
    return alerts
