"""
Hermes Life OS - Week Ahead
=============================
One calendar over everything with a date: tasks that are due, time blocks,
planned meals, birthdays, subscription renewals, debts, countdowns, chores,
expiry dates, trips, decisions to review and gift deadlines. Overdue items come
first, then each day of the window with what falls on it; days with nothing are
summed up in one line. Read-only; a source that cannot be read is left out,
never an error, and no network call is made.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Dict, List, Tuple

import clock
import plannerkit as kit

DEFAULT_DAYS = 7
MAX_DAYS = 14
MAX_PER_DAY = 8
MAX_OVERDUE = 8

Item = Tuple[str, str]   # (YYYY-MM-DD, text); a date before today means overdue


def _tasks(days: int) -> List[Item]:
    import tasks
    return [(t["due"], f"Task: {t.get('text', '?')}") for t in tasks.list_tasks("open", due_within=days, limit=200)]


def _blocks(days: int) -> List[Item]:
    import timeblocks
    out = []
    for i in range(days + 1):
        d = clock.today() + timedelta(days=i)
        for b in timeblocks.day_plan(d.isoformat())["blocks"]:
            if not b.get("done"):
                out.append((d.isoformat(), f"{b.get('start')}-{b.get('end')} {b.get('title', '?')}"))
    return out


def _meals(days: int) -> List[Item]:
    import storage
    end = (clock.today() + timedelta(days=days)).isoformat()
    return [(m["date"], f"{m.get('slot', 'meal').capitalize()}: {m.get('name', '?')}")
            for m in kit.only_dicts(storage.load_mealplan())
            if isinstance(m.get("date"), str) and clock.today_str() <= m["date"] <= end and not m.get("eaten")]


def _birthdays(days: int) -> List[Item]:
    import people
    return [(b["date"], f"Birthday: {b['person'].get('name', '?')}" + (f" (turning {b['turning']})" if b.get("turning") else ""))
            for b in people.upcoming_birthdays(days)]


def _subscriptions(days: int) -> List[Item]:
    import subscriptions
    out = []
    for r in subscriptions.upcoming(days):
        amount = r["sub"].get("amount")
        amount = f"{amount:g}" if isinstance(amount, (int, float)) and not isinstance(amount, bool) else amount
        out.append((r["date"], f"Renews: {r['sub'].get('name', '?')} ({amount} {r['sub'].get('cycle', '')})".replace(" )", ")")))
    return out


def _debts(days: int) -> List[Item]:
    import debts
    return [(x["debt"]["due"], f"Debt due: {debts.describe(x['debt'])}") for x in debts.due_soon(days)]


def _countdowns(days: int) -> List[Item]:
    import countdowns
    return [(x["date"], f"Countdown: {x['item'].get('name', '?')}") for x in countdowns.within(days)]


def _chores(days: int) -> List[Item]:
    import chores
    return [(x["due"], f"Chore: {x['item'].get('name', '?')}") for x in chores.listing(days)]


def _expiries(days: int) -> List[Item]:
    import expiries
    return [(x["date"], f"Expires: {x['item'].get('name', '?')}") for x in expiries.listing()
            if -expiries.STALE_DAYS <= x["in_days"] <= days]


def _trips(days: int) -> List[Item]:
    import trips
    out = []
    horizon = clock.today() + timedelta(days=days)
    for t in trips.listing(False):
        try:
            first, last = clock.parse_day(t["start"]), clock.parse_day(t["end"])
        except (ValueError, KeyError):
            continue
        if clock.today() <= first <= horizon:
            out.append((first.isoformat(), f"Trip starts: {t.get('name', '?')}"))
        if clock.today() <= last <= horizon:
            out.append((last.isoformat(), f"Trip ends: {t.get('name', '?')}"))
    return out


def _decisions(days: int) -> List[Item]:
    import decisions
    return [((clock.today() + timedelta(days=x["in_days"])).isoformat(), f"Review decision: {x['item'].get('title', '?')}")
            for x in decisions.due_for_review(days)]


SOURCES: List[Callable[[int], List[Item]]] = [_tasks, _blocks, _meals, _birthdays, _subscriptions, _debts, _countdowns,
                                              _chores, _expiries, _trips, _decisions]


def parse_days(value: Any) -> int:
    if value is None or value == "":
        return DEFAULT_DAYS
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not 1 <= value <= MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {MAX_DAYS}.")
    return int(value)


def build(days: int = DEFAULT_DAYS) -> Dict[str, Any]:
    """{"start", "end", "overdue": [text], "days": {date: [text]}}."""
    today = clock.today()
    horizon = (today + timedelta(days=days - 1)).isoformat()
    overdue: List[Item] = []
    by_day: Dict[str, List[str]] = {}
    for source in SOURCES:
        try:
            items = source(days - 1)
        except Exception:  # noqa: BLE001 - a broken store never breaks the overview
            continue
        for date, text in items:
            if not isinstance(date, str) or not isinstance(text, str):
                continue
            if date < today.isoformat():
                overdue.append((date, text))
            elif date <= horizon:
                by_day.setdefault(date, []).append(text)
    overdue.sort()
    return {"start": today.isoformat(), "end": horizon, "overdue": [f"{t} (was due {d})" for d, t in overdue],
            "days": dict(sorted(by_day.items()))}


def format_week(data: Dict[str, Any]) -> str:
    start, end = clock.parse_day(data["start"]), clock.parse_day(data["end"])
    n = (end - start).days + 1
    lines = [f"{'Week' if n == 7 else ('Day' if n == 1 else str(n) + ' days')} ahead: {start.strftime('%a %Y-%m-%d')} to {end.strftime('%a %Y-%m-%d')}"]
    if data["overdue"]:
        lines.append("Overdue:")
        lines += [f"  - {t}" for t in data["overdue"][:MAX_OVERDUE]]
        if len(data["overdue"]) > MAX_OVERDUE:
            lines.append(f"  ... and {len(data['overdue']) - MAX_OVERDUE} more")
    free = []
    for i in range(n):
        d = start + timedelta(days=i)
        items = data["days"].get(d.isoformat(), [])
        label = d.strftime("%a %d %b") + (" (today)" if i == 0 else "")
        if not items:
            free.append(d.strftime("%a %d"))
            continue
        lines.append(f"{label}:")
        lines += [f"  - {t}" for t in items[:MAX_PER_DAY]]
        if len(items) > MAX_PER_DAY:
            lines.append(f"  ... and {len(items) - MAX_PER_DAY} more")
    if not data["overdue"] and not data["days"]:
        return lines[0] + f"\nNothing planned for the next {kit.plural(n, 'day')}."
    if free:
        lines.append("Nothing planned: " + ", ".join(free))
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "get_week_ahead":
            return format_week(build(parse_days(inp.get("days"))))
    except (ValueError, TypeError) as e:
        return f"Cannot show the week ahead: {e}"
    return f"Unknown week tool: {name}"
