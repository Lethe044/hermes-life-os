"""
Hermes Life OS - Closing Summary
==================================
The counterpart of the morning agenda: a wrap-up to read at the end of the
day or the week. For a day it lists what got done (finished tasks, time
blocks, habit check-ins), what was logged, what was spent and earned, what is
still open (overdue tasks, today's unfinished blocks, habit streaks that need a
check-in) and a preview of tomorrow. For a week it counts the same things over
the last seven days and previews the next seven.

Read-only and network-free. Every section is gathered on its own, so one
unreadable store leaves only that section out. "Today" is the user's day
(clock.py).
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

import clock

MAX_ITEMS = 5
PERIODS = ("day", "week")


def _section(title: str, lines: List[str]) -> List[str]:
    if not lines:
        return []
    out = [title] + [f"  {line}" for line in lines[:MAX_ITEMS]]
    if len(lines) > MAX_ITEMS:
        out.append(f"  ... and {len(lines) - MAX_ITEMS} more")
    return out


def _safe(fn: Callable[[], List[str]]) -> List[str]:
    try:
        return fn()
    except Exception:  # noqa: BLE001 - one broken store must not blank the whole summary
        return []


def _rows(loader: str) -> List[Dict[str, Any]]:
    import storage
    rows = getattr(storage, loader)()
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _amount(r: Dict[str, Any]) -> float:
    a = r.get("amount")
    return float(a) if isinstance(a, (int, float)) and not isinstance(a, bool) else 0.0


def _money(x: float) -> str:
    return f"{x:,.2f}".replace(".00", "")


def _logged_counts(first: str, last: str) -> Counter:
    import entries
    counts: Counter = Counter()
    for tracker, row, _label in entries._all_rows():
        if first <= str(row.get("date", "")) <= last:
            counts[tracker] += 1
    return counts


def _days_logged(first: str, last: str) -> int:
    import entries
    return len({str(r.get("date")) for _t, r, _l in entries._all_rows() if first <= str(r.get("date", "")) <= last})


def _money_lines(first: str, last: str) -> List[str]:
    spent = sum(_amount(r) for r in _rows("load_spending") if first <= str(r.get("date", "")) <= last)
    earned = sum(_amount(r) for r in _rows("load_income") if first <= str(r.get("date", "")) <= last)
    if not spent and not earned:
        return []
    line = f"spent {_money(spent)}, earned {_money(earned)}"
    if spent and earned:
        line += f", net {_money(earned - spent)}"
    return [line]


def _tasks_done(first: str, last: str) -> List[str]:
    return [str(t.get("text", "?")) for t in _rows("load_tasks")
            if t.get("done") and first <= str(t.get("done_date") or "") <= last]


def _blocks(first: str, last: str) -> List[Dict[str, Any]]:
    import timeblocks
    return [r for r in _rows("load_timeblocks") if first <= str(r.get("date", "")) <= last and timeblocks.span(r)]


def _minutes(rows: List[Dict[str, Any]]) -> int:
    import timeblocks
    return sum(timeblocks.span(r)[1] - timeblocks.span(r)[0] for r in rows)


def _habits_done(day: str) -> List[str]:
    return [str(h.get("name")) for h in _rows("load_habits") if h.get("last_done") == day]


def _reminders_on(day) -> List[str]:
    from reminders import get_todays_reminders, normalize_time
    when = clock.now().replace(year=day.year, month=day.month, day=day.day)
    return [f"{normalize_time(r.get('time')) or 'any time'}: {r.get('text', '')}" for r in get_todays_reminders(when)]


# ------------------------------------------------------------------ day

def _day_lines() -> List[str]:
    import tasks
    today = clock.today()
    d, tomorrow = today.isoformat(), (today + timedelta(days=1)).isoformat()
    out: List[str] = [f"Closing summary for {today.strftime('%A')} {d}"]
    done_tasks = _safe(lambda: _tasks_done(d, d))
    blocks_done = _safe(lambda: [f"time block: {r['title']}" for r in _blocks(d, d) if r.get("done")])
    habits = _safe(lambda: [f"habit: {n}" for n in _habits_done(d)])
    out += _section(f"Done today ({len(done_tasks)} task(s), {len(blocks_done)} block(s), {len(habits)} habit(s)):",
                    [f"task: {t}" for t in done_tasks] + blocks_done + habits)

    def logged() -> List[str]:
        c = _logged_counts(d, d)
        return [", ".join(f"{k} {v}" for k, v in sorted(c.items()))] if c else []
    out += _section("Logged today:", _safe(logged) + _safe(lambda: _money_lines(d, d)))

    def open_items() -> List[str]:
        s = tasks.summary()
        lines = [f"{len(s['overdue'])} overdue task(s)"] if s["overdue"] else []
        lines += [f"due today, not done: {t.get('text')}" for t in s["due_today"]]
        lines += [f"unfinished block: {r['start']}-{r['end']} {r['title']}" for r in sorted(
            _blocks(d, d), key=lambda r: r["start"]) if not r.get("done")]
        lines += [f"habit streak at risk: {h['name']} ({h['streak']} days)" for h in _rows("load_habits")
                  if isinstance(h.get("streak"), int) and h["streak"] > 0 and h.get("last_done") != d]
        return lines
    out += _section("Still open:", _safe(open_items))

    def tomorrow_items() -> List[str]:
        import subscriptions
        import people
        import countdowns
        import trips
        import recipes
        lines = [f"task: {t.get('text')}" for t in tasks._rows(tasks._load())
                 if not t.get("done") and t.get("due") == tomorrow]
        bl = sorted(_blocks(tomorrow, tomorrow), key=lambda r: r["start"])
        if bl:
            lines.append(f"{len(bl)} time block(s), first {bl[0]['start']} {bl[0]['title']}")
        lines += [f"reminder {x}" for x in _safe(lambda: _reminders_on(today + timedelta(days=1)))]
        lines += [f"meal {m.get('slot')}: {m.get('name')}" for m in _safe_list(lambda: recipes.meals_between(tomorrow, tomorrow))]
        lines += [f"renewal: {x['sub']['name']}" for x in _safe_list(lambda: subscriptions.upcoming(1)) if x["in_days"] == 1]
        lines += [f"birthday: {x['person']['name']}" for x in _safe_list(lambda: people.upcoming_birthdays(1)) if x["in_days"] == 1]
        lines += [countdowns.format_countdown(x).split(" [id=")[0] for x in _safe_list(lambda: countdowns.within(1))
                  if x["in_days"] == 1]
        lines += [f"trip starts: {t['name']}" for t in _safe_list(trips.listing) if t.get("start") == tomorrow]
        return lines
    out += _section("Tomorrow:", _safe(tomorrow_items))
    if len(out) == 1:
        out.append("Nothing recorded for today and nothing coming up tomorrow.")
    return out


def _safe_list(fn: Callable[[], Any]) -> List[Any]:
    try:
        return list(fn())
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------ week

def _week_lines() -> List[str]:
    import tasks
    today = clock.today()
    last = today.isoformat()
    first = (today - timedelta(days=6)).isoformat()
    ahead_first, ahead_last = (today + timedelta(days=1)).isoformat(), (today + timedelta(days=7)).isoformat()
    out: List[str] = [f"Closing summary for the week {first} to {last}"]

    def done() -> List[str]:
        t = _tasks_done(first, last)
        b = [r for r in _blocks(first, last) if r.get("done")]
        lines = [f"{len(t)} task(s) finished"] if t else []
        if b:
            lines.append(f"{len(b)} time block(s) done, {_minutes(b) / 60:.1f} h")
        return lines
    out += _section("Done:", _safe(done))

    def logged() -> List[str]:
        c = _logged_counts(first, last)
        if not c:
            return []
        return [f"entries on {_days_logged(first, last)} of 7 days: " + ", ".join(f"{k} {v}" for k, v in c.most_common(8))]
    out += _section("Logged:", _safe(logged))
    out += _section("Money:", _safe(lambda: _money_lines(first, last)))

    def symptoms() -> List[str]:
        rows = [r for r in _rows("load_symptoms") if first <= str(r.get("date", "")) <= last]
        c = Counter(str(r.get("symptom")) for r in rows)
        return [", ".join(f"{k} {v}x" for k, v in c.most_common(4))] if c else []
    out += _section("Symptoms (a personal log, not medical advice):", _safe(symptoms))

    def objectives() -> List[str]:
        import okrs
        return [f"{r['name']}: {round(okrs.progress(r) * 100)}% done, {okrs.pace(r)}" for r in okrs.listing("active")]
    out += _section("Objectives:", _safe(objectives))

    def open_items() -> List[str]:
        s = tasks.summary()
        return [f"{len(s['overdue'])} overdue task(s)"] if s["overdue"] else []
    out += _section("Still open:", _safe(open_items))

    def ahead() -> List[str]:
        import subscriptions
        import people
        import countdowns
        import trips
        import recipes
        lines = []
        due = [t for t in tasks._rows(tasks._load()) if not t.get("done") and ahead_first <= str(t.get("due") or "") <= ahead_last]
        if due:
            lines.append(f"{len(due)} task(s) due")
        b = _blocks(ahead_first, ahead_last)
        if b:
            lines.append(f"{len(b)} time block(s), {_minutes(b) / 60:.1f} h planned")
        m = _safe_list(lambda: recipes.meals_between(ahead_first, ahead_last))
        if m:
            lines.append(f"{len(m)} meal(s) planned")
        lines += [f"trip: {t['name']} starts {t['start']}" for t in _safe_list(trips.listing)
                  if ahead_first <= str(t.get("start")) <= ahead_last]
        subs = _safe_list(lambda: subscriptions.upcoming(7))
        if subs:
            lines.append(f"{len(subs)} subscription renewal(s)")
        bd = _safe_list(lambda: people.upcoming_birthdays(7))
        if bd:
            lines.append("birthdays: " + ", ".join(x["person"]["name"] for x in bd[:4]))
        cd = _safe_list(lambda: countdowns.within(7))
        if cd:
            lines.append("countdowns: " + ", ".join(x["item"]["name"] for x in cd[:4]))
        return lines
    out += _section("Next 7 days:", _safe(ahead))
    if len(out) == 1:
        out.append("Nothing recorded this week and nothing coming up.")
    return out


def build_closing(period: Any = "day") -> str:
    key = "day" if period in (None, "") else period
    if not isinstance(key, str) or key.strip().lower() not in PERIODS:
        raise ValueError("period must be day or week.")
    return "\n".join(_day_lines() if key.strip().lower() == "day" else _week_lines())


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name == "get_closing_summary":
        try:
            return build_closing(inp.get("period"))
        except ValueError as e:
            return f"Cannot summarize: {e}"
    return f"Unknown closing tool: {name}"
