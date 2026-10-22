"""
Hermes Life OS - Today's Agenda
=================================
One answer to "what do I have today?" that pulls from everything that has a
date attached: tasks (overdue and due today), reminders for today,
subscription renewals in the next few days, birthdays and people you are
overdue to contact, habit streaks that need a check-in today to survive,
budgets that are over or close to their limit, savings goals whose deadline
is within two weeks, debts that are due, countdowns in the next week and
supplies that are about to run out.

Read-only and network-free; a section with nothing to say is left out, and if
nothing at all is due the agenda says so. "Today" is the user's day (clock.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import clock

RENEWAL_DAYS = 3
BIRTHDAY_DAYS = 7
MAX_PER_SECTION = 5


def _section(title: str, lines: List[str]) -> List[str]:
    return [title] + [f"  {line}" for line in lines[:MAX_PER_SECTION]] + (
        [f"  ... and {len(lines) - MAX_PER_SECTION} more"] if len(lines) > MAX_PER_SECTION else [])


def build_agenda() -> str:
    import tasks
    import subscriptions
    import people
    from reminders import get_todays_reminders, normalize_time
    from storage import load_habits

    today = clock.today()
    out: List[str] = [f"Agenda for {today.isoformat()} ({today.strftime('%A')})"]
    sections: List[List[str]] = []

    s = tasks.summary()
    task_lines = [tasks.format_task(t) for t in s["overdue"]] + [tasks.format_task(t) for t in s["due_today"]]
    if task_lines:
        sections.append(_section(f"Tasks ({len(s['overdue'])} overdue, {len(s['due_today'])} due today):", task_lines))

    reminder_lines = []
    for r in get_todays_reminders(clock.now()):
        hhmm = normalize_time(r.get("time"))
        reminder_lines.append(f"{hhmm or 'any time'}: {r.get('text', '')}")
    if reminder_lines:
        sections.append(_section("Reminders:", reminder_lines))

    renew = subscriptions.upcoming(RENEWAL_DAYS)
    if renew:
        sections.append(_section(f"Renewals in the next {RENEWAL_DAYS} days:", [
            f"{r['date']} ({'today' if r['in_days'] == 0 else 'in ' + str(r['in_days']) + ' day(s)'}): "
            f"{r['sub']['name']} {r['sub']['amount']:g}" for r in renew]))

    people_lines = []
    for b in people.upcoming_birthdays(BIRTHDAY_DAYS):
        when = "TODAY" if b["in_days"] == 0 else f"in {b['in_days']} day(s)"
        turning = f", turning {b['turning']}" if b["turning"] else ""
        people_lines.append(f"{b['person']['name']}'s birthday {when}{turning}")
    for o in people.overdue(3):
        people_lines.append(f"Catch up with {o['person']['name']} ({o['days_since']} days, goal every {o['interval']})")
    if people_lines:
        sections.append(_section("People:", people_lines))

    yesterday = clock.days_ago_str(1)
    risk = [h for h in load_habits() if isinstance(h, dict) and h.get("streak", 0) > 0
            and h.get("last_done") == yesterday]
    if risk:
        sections.append(_section("Habits that need a check-in today to keep their streak:", [
            f"{h['name']} ({h['streak']} days)" for h in sorted(risk, key=lambda h: -h["streak"])]))

    try:
        from budgets import budget_alerts
        alerts = budget_alerts()
    except Exception:  # noqa: BLE001 - the agenda must never fail because of one section
        alerts = []
    if alerts:
        sections.append(_section("Budgets:", alerts))

    try:
        import savings
        close = savings.nudges(3)
    except Exception:  # noqa: BLE001
        close = []
    if close:
        sections.append(_section("Savings goals with a close deadline:", close))

    try:
        import debts
        due = [f"{('OVERDUE ' if x['in_days'] < 0 else '') + debts.describe(x['debt'])} "
               f"(due {x['debt']['due']})" for x in debts.due_soon(3)]
    except Exception:  # noqa: BLE001
        due = []
    if due:
        sections.append(_section("Debts due:", due))

    try:
        import countdowns
        coming = [countdowns.format_countdown(x).split(" [id=")[0] for x in countdowns.within(countdowns.AGENDA_DAYS)]
    except Exception:  # noqa: BLE001
        coming = []
    if coming:
        sections.append(_section("Countdowns:", coming))

    try:
        import supplies
        low = [supplies.format_supply(x).split(" [id=")[0] for x in supplies.running_low(supplies.AGENDA_DAYS)]
    except Exception:  # noqa: BLE001
        low = []
    if low:
        sections.append(_section("Supplies running out:", low))

    if not sections:
        return out[0] + "\nNothing due today: no tasks, reminders, renewals, birthdays or streaks at risk."
    for sec in sections:
        out.extend(sec)
    return "\n".join(out)


def run_tool(name: str, inp, **_ctx) -> str:
    if name == "get_today_agenda":
        return build_agenda()
    return f"Unknown agenda tool: {name}"
