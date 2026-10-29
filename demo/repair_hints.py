"""
Hermes Life OS - Repair Suggestions
=====================================
The doctor (doctor.py) counts the problems in the planner data: "3 task(s)
have a due date that cannot be read". This module says WHICH entries, and what
to do about each: the id, what is wrong and the tool call that would fix or
remove it ("update_task(task='ab12cd34', fields={'due': ''})"). Hand-edited
files, imports and old versions are where such entries come from.

Strictly read-only: it never changes, repairs or assigns anything. Applying a
suggestion is a normal tool call you (or Hermes, when you ask) make
afterwards. No network call is made by this module.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

import clock

MAX_LINES = 30
_CYCLES = ("weekly", "monthly", "quarterly", "yearly")
_SLOTS = ("breakfast", "lunch", "dinner", "snack")


def _day_ok(value: Any) -> bool:
    try:
        clock.parse_day(value)
        return True
    except (ValueError, TypeError):
        return False


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def label(row: Dict[str, Any]) -> str:
    for key in ("text", "name", "title", "who", "symptom", "source"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            text = " ".join(v.split())
            return f"'{text[:40]}'" + ("..." if len(text) > 40 else "")
    return "(no name)"


def _q(value: Any) -> str:
    return repr(str(value))[:40]


Check = Callable[[Dict[str, Any]], Optional[Tuple[str, str]]]


def _tasks(r):
    if not r.get("done") and r.get("due") and not _day_ok(r.get("due")):
        return (f"the due date {_q(r.get('due'))} cannot be read",
                f"update_task(task={r['id']!r}, fields={{'due': 'YYYY-MM-DD'}}) or fields={{'due': ''}} to clear it")


def _subscriptions(r):
    if not r.get("active", True):
        return None
    if not _day_ok(r.get("next_date")):
        return ("no readable renewal date", f"update_subscription(subscription={r['id']!r}, fields={{'next_date': 'YYYY-MM-DD'}})")
    if r.get("cycle") not in _CYCLES:
        return (f"the cycle {_q(r.get('cycle'))} is not one of {', '.join(_CYCLES)}",
                f"update_subscription(subscription={r['id']!r}, fields={{'cycle': 'monthly'}})")
    if not _num(r.get("amount")) or r["amount"] <= 0:
        return ("the amount is not a positive number", f"update_subscription(subscription={r['id']!r}, fields={{'amount': 9.99}})")


def _people(r):
    b = r.get("birthday")
    if b and not (_day_ok(b) if len(str(b).split("-")) == 3 else _day_ok(f"2024-{b}")):
        return (f"the birthday {_q(b)} cannot be read", f"update_person(person={r['id']!r}, fields={{'birthday': 'MM-DD'}}) or fields={{'birthday': ''}}")


def _savings(r):
    if not _num(r.get("target")) or r["target"] <= 0:
        return ("the target is not a positive number", f"update_savings_goal(goal={r['id']!r}, fields={{'target': 1000}})")
    if r.get("deadline") and not _day_ok(r.get("deadline")):
        return (f"the deadline {_q(r.get('deadline'))} cannot be read",
                f"update_savings_goal(goal={r['id']!r}, fields={{'deadline': 'YYYY-MM-DD'}}) or fields={{'deadline': ''}}")


def _symptoms(r):
    if not isinstance(r.get("symptom"), str) or not _num(r.get("severity")) or not 1 <= r["severity"] <= 10 \
            or not _day_ok(r.get("date")):
        return ("a missing name, a severity outside 1-10 or an unreadable date",
                f"edit_log(tracker='symptoms', log_id={r['id']!r}, fields={{'severity': 5, 'date': 'YYYY-MM-DD'}}) "
                f"or delete_log(tracker='symptoms', log_id={r['id']!r})")


def _income(r):
    if not _num(r.get("amount")) or r["amount"] <= 0 or not _day_ok(r.get("date")):
        return ("an amount that is not positive or an unreadable date",
                f"edit_log(tracker='income', log_id={r['id']!r}, fields={{'amount': 100, 'date': 'YYYY-MM-DD'}}) "
                f"or delete_log(tracker='income', log_id={r['id']!r})")


def _body(r):
    from body import METRICS
    if r.get("type") == "goal":
        return None
    if r.get("metric") not in METRICS or not _num(r.get("value")) or not _day_ok(r.get("date")):
        return ("an unknown metric, a non-numeric value or no date",
                f"edit_log(tracker='body', log_id={r['id']!r}, fields={{'value': 70, 'date': 'YYYY-MM-DD'}}) "
                f"or delete_log(tracker='body', log_id={r['id']!r})")


def _lists(r):
    if not isinstance(r.get("text"), str) or not r["text"].strip():
        return ("an item without text", f"remove_list_items(item={r['id']!r})")


def _notes(r):
    if not isinstance(r.get("text"), str) or not r["text"].strip():
        return ("a note without text", f"delete_note(note={r['id']!r})")


def _debts(r):
    if not _num(r.get("amount")) or r["amount"] <= 0 or r.get("direction") not in ("owe", "owed"):
        return ("an unusable amount or direction", f"update_debt(debt={r['id']!r}, fields={{'amount': 50}}) or delete_debt(debt={r['id']!r})")
    if r.get("due") and not _day_ok(r.get("due")):
        return (f"the due date {_q(r.get('due'))} cannot be read",
                f"update_debt(debt={r['id']!r}, fields={{'due': 'YYYY-MM-DD'}}) or fields={{'due': ''}}")


def _countdowns(r):
    if not _day_ok(r.get("date")):
        return ("the date cannot be read", f"update_countdown(countdown={r['id']!r}, fields={{'date': 'YYYY-MM-DD'}})")


def _supplies(r):
    if not _num(r.get("quantity")) or r["quantity"] < 0 or not _day_ok(r.get("as_of")):
        return ("a count or count date that cannot be read",
                f"refill_supply(supply={r['id']!r}, quantity=10, mode='set') (sets the count today)")
    if not _num(r.get("per_day")) or r["per_day"] < 0:
        return ("a daily use that cannot be read", f"update_supply(supply={r['id']!r}, fields={{'per_day': 1}})")


def _timeblocks(r):
    import timeblocks
    if timeblocks.span(r) is None:
        return ("an unreadable date, start or end (or an end before the start)",
                f"update_time_block(block={r['id']!r}, fields={{'date': 'YYYY-MM-DD', 'start': '09:00', 'end': '10:00'}}) "
                f"or delete_time_block(block={r['id']!r})")


def _okrs(r):
    if not _day_ok(r.get("start")) or not _day_ok(r.get("end")) or str(r.get("end")) < str(r.get("start")):
        return ("an unreadable period", f"update_okr(objective={r['id']!r}, fields={{'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}})")
    for k in r.get("key_results") if isinstance(r.get("key_results"), list) else []:
        if not isinstance(k, dict) or not all(_num(k.get(f)) for f in ("start_value", "target", "current")) \
                or k.get("start_value") == k.get("target"):
            name = k.get("name") if isinstance(k, dict) else "?"
            kid = k.get("id") if isinstance(k, dict) else "?"
            return (f"the key result {_q(name)} has numbers that cannot be used",
                    f"update_okr(objective={r['id']!r}, key_result={kid!r}, fields={{'target': 100, 'start_value': 0, 'current': 0}}) "
                    f"or delete_okr(objective={r['id']!r}, key_result={kid!r})")


def _recipes(r):
    ings = r.get("ingredients")
    if not isinstance(ings, list) or not any(isinstance(i, dict) and isinstance(i.get("name"), str) and i["name"].strip() for i in ings):
        return ("no usable ingredients", f"update_recipe(recipe={r['id']!r}, fields={{'ingredients': ['200 g flour']}}) or delete_recipe(recipe={r['id']!r})")
    if not _num(r.get("servings")) or r["servings"] < 1:
        return ("servings that are not a positive number", f"update_recipe(recipe={r['id']!r}, fields={{'servings': 2}})")


def _mealplan(r):
    if not _day_ok(r.get("date")) or r.get("slot") not in _SLOTS:
        return ("an unreadable date or an unknown slot", f"clear_meals(meal={r['id']!r}) and plan it again with plan_meal")


def _trips(r):
    if not _day_ok(r.get("start")) or not _day_ok(r.get("end")) or str(r.get("end")) < str(r.get("start")):
        return ("unreadable or reversed dates", f"update_trip(trip={r['id']!r}, fields={{'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}})")


def _chores(r):
    import chores
    if chores.due_date(r) is None:
        return ("an interval or date that cannot be read",
                f"update_chore(chore={r['id']!r}, fields={{'every': 'weekly', 'start': 'YYYY-MM-DD'}}) or delete_chore(chore={r['id']!r})")


def _expiries(r):
    if not _day_ok(r.get("date")):
        return ("the expiry date cannot be read", f"update_expiry(item={r['id']!r}, fields={{'date': 'YYYY-MM-DD'}})")


def _routines(r):
    import routines
    if not routines.steps_of(r):
        return ("no usable steps", f"update_routine(routine={r['id']!r}, fields={{'steps': ['first step']}}) or delete_routine(routine={r['id']!r})")
    days = r.get("days")
    if days is not None and not (isinstance(days, list) and all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days)):
        return ("a schedule that cannot be read", f"update_routine(routine={r['id']!r}, fields={{'days': 'daily'}})")


def _gifts(r):
    if not isinstance(r.get("idea"), str) or not r["idea"].strip() or not isinstance(r.get("person"), str) or not r["person"].strip():
        return ("no person or idea text", f"delete_gift_idea(gift={r['id']!r})")
    if r.get("status") not in ("idea", "bought", "given"):
        return ("an unknown status", f"update_gift_idea(gift={r['id']!r}, fields={{'status': 'idea'}})")


def _decisions(r):
    if not isinstance(r.get("title"), str) or not r["title"].strip():
        return ("no title", f"delete_decision(decision={r['id']!r})")
    if r.get("status") not in ("open", "reviewed"):
        return ("an unknown status", f"delete_decision(decision={r['id']!r}) and add it again with add_decision")
    if r.get("status") != "reviewed" and not _day_ok(r.get("review")):
        return ("the review date cannot be read", f"update_decision(decision={r['id']!r}, fields={{'review': 'in 7 days'}})")


CHECKS: List[Tuple[str, Check]] = [
    ("tasks", _tasks), ("subscriptions", _subscriptions), ("people", _people), ("savings", _savings),
    ("symptoms", _symptoms), ("income", _income), ("body", _body), ("lists", _lists), ("notes", _notes),
    ("debts", _debts), ("countdowns", _countdowns), ("supplies", _supplies), ("timeblocks", _timeblocks),
    ("okrs", _okrs), ("recipes", _recipes), ("mealplan", _mealplan), ("trips", _trips), ("chores", _chores),
    ("expiries", _expiries), ("routines", _routines), ("gifts", _gifts), ("decisions", _decisions),
]


def _rows(name: str) -> List[Dict[str, Any]]:
    import storage
    try:
        data = storage.load_store(name)
    except Exception:  # noqa: BLE001 - unreadable stores are the doctor's business
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def find_problems() -> List[Dict[str, str]]:
    """[{"area", "id", "label", "problem", "fix"}] for every entry the checks
    object to, plus shared ids. Entries without an id are described as such.
    Never writes anything (no ids are assigned either)."""
    out: List[Dict[str, str]] = []
    for area, check in CHECKS:
        rows = _rows(area)
        ids = [r["id"] for r in rows if isinstance(r.get("id"), str) and r["id"]]
        for r in rows:
            rid = r.get("id") if isinstance(r.get("id"), str) and r.get("id") else None
            probe = dict(r) if rid else {**r, "id": "(no id yet)"}
            try:
                found = check(probe)
            except Exception:  # noqa: BLE001 - a hand-edited row never breaks the report
                found = ("an entry that cannot be read at all", "export your data, then fix or remove it in the file")
            if found:
                problem, fix = found
                if not rid:
                    fix = "this entry has no id yet; the next normal use of its tools assigns one. Then: " + fix
                out.append({"area": area, "id": rid or "-", "label": label(r), "problem": problem, "fix": fix})
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            out.append({"area": area, "id": dup, "label": "(shared id)",
                        "problem": f"{ids.count(dup)} entries share this id, so editing or deleting by id only reaches the first",
                        "fix": "refer to these entries by some words from their text or name instead of the id"})
    return out


def format_suggestions(problems: List[Dict[str, str]]) -> str:
    if not problems:
        return "No problems found in the planner data, so there is nothing to repair."
    lines = [f"{len(problems)} problem{'s' if len(problems) != 1 else ''} found in your planner data. "
             f"Nothing was changed; each fix is a normal tool call:"]
    for p in problems[:MAX_LINES]:
        lines.append(f"- {p['area']} [id={p['id']}] {p['label']}: {p['problem']}.\n    Fix: {p['fix']}")
    if len(problems) > MAX_LINES:
        lines.append(f"... and {len(problems) - MAX_LINES} more.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name == "get_repair_suggestions":
        return format_suggestions(find_problems())
    return f"Unknown repair tool: {name}"
