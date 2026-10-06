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
"""

from __future__ import annotations

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


def _current_month_spent_by_category() -> Dict[str, float]:
    month_prefix = datetime.utcnow().strftime("%Y-%m")
    spent: Dict[str, float] = {}
    for s in load_spending():
        date = s.get("date", "")
        if not date.startswith(month_prefix):
            continue
        category = s.get("category", "uncategorized")
        spent[category] = spent.get(category, 0.0) + s.get("amount", 0)
    return spent


def compute_budget_status(category: Optional[str] = None) -> List[Dict[str, Any]]:
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
    spent_by_category = _current_month_spent_by_category()

    results = []
    for b in sorted(budgets, key=lambda b: b.get("category", "").lower()):
        cat = b.get("category", "")
        limit = b.get("limit", 0)
        spent = round(spent_by_category.get(cat, 0.0), 2)
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
