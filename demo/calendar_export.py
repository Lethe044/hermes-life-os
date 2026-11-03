"""
Hermes Life OS - Calendar Export
==================================
Writes your planner as a standard .ics file that Google Calendar, Apple
Calendar and Outlook can import: time blocks, task due dates, birthdays (a
yearly repeat), countdowns, trips, expiry dates, chores, subscription renewals
and decision reviews. Every event gets a stable id, so importing a newer export
updates the earlier events instead of duplicating them. Read-only for your
data: the file lands in the profile's exports folder and nothing is sent
anywhere.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional

import clock

SECTIONS = ("blocks", "tasks", "birthdays", "countdowns", "trips", "expiries", "chores", "renewals", "decisions")
DEFAULT_DAYS = 365
MAX_DAYS = 1100
PRODID = "-//Hermes Life OS//Calendar Export//EN"


# ------------------------------------------------------------------ ICS basics

def escape(text: Any) -> str:
    """RFC 5545 TEXT escaping."""
    s = str(text if text is not None else "")
    s = s.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,")
    return s.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def fold(line: str) -> str:
    """Lines are at most 75 octets; longer ones continue on a line starting
    with one space. Splits never cut a multi-byte character."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts: List[str] = []
    cur = b""
    limit = 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > limit:
            parts.append(cur.decode("utf-8"))
            cur, limit = b"", 74
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def _d(value: date) -> str:
    return value.strftime("%Y%m%d")


def _stamp() -> str:
    return clock.now().strftime("%Y%m%dT%H%M%S")


def _event(uid: str, summary: str, *, day: Optional[date] = None, end_day: Optional[date] = None,
           start: Optional[str] = None, end: Optional[str] = None, description: str = "",
           rrule: str = "", category: str = "") -> List[str]:
    lines = ["BEGIN:VEVENT", f"UID:{uid}@hermes-life-os", f"DTSTAMP:{_stamp()}"]
    if start and end and day:
        lines += [f"DTSTART:{_d(day)}T{start.replace(':', '')}00", f"DTEND:{_d(day)}T{end.replace(':', '')}00"]
    elif day:
        last = end_day or day
        lines += [f"DTSTART;VALUE=DATE:{_d(day)}", f"DTEND;VALUE=DATE:{_d(last + timedelta(days=1))}"]
    lines.append(f"SUMMARY:{escape(summary)}")
    if description:
        lines.append(f"DESCRIPTION:{escape(description)}")
    if category:
        lines.append(f"CATEGORIES:{escape(category)}")
    if rrule:
        lines.append(f"RRULE:{rrule}")
    lines.append("END:VEVENT")
    return lines


def _day(value: Any) -> Optional[date]:
    try:
        return clock.parse_day(value)
    except (ValueError, TypeError):
        return None


def _hhmm(value: Any) -> Optional[str]:
    try:
        h, m = str(value).split(":")
        if 0 <= int(h) <= 23 and 0 <= int(m) <= 59:
            return f"{int(h):02d}:{int(m):02d}"
    except (ValueError, TypeError):
        pass
    return None


def _rows(name: str) -> List[Dict[str, Any]]:
    import storage
    try:
        data = storage.load_store(name)
    except Exception:  # noqa: BLE001 - one unreadable store never stops the export
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


# ------------------------------------------------------------------ sections

def _blocks(lo: date, hi: date) -> List[List[str]]:
    out = []
    for b in _rows("timeblocks"):
        day, s, e = _day(b.get("date")), _hhmm(b.get("start")), _hhmm(b.get("end"))
        if day is None or not s or not e or e <= s or not lo <= day <= hi:
            continue
        mark = " (done)" if b.get("done") else ""
        out.append(_event(f"block-{b.get('id')}", f"{b.get('title', 'Time block')}{mark}", day=day, start=s, end=e,
                          description=str(b.get("notes") or ""), category=str(b.get("category") or "time block")))
    return out


def _tasks(lo: date, hi: date) -> List[List[str]]:
    out = []
    for t in _rows("tasks"):
        day = _day(t.get("due"))
        if t.get("done") or day is None or not lo <= day <= hi:
            continue
        flag = "! " if t.get("priority") == "high" else ""
        out.append(_event(f"task-{t.get('id')}", f"{flag}Task: {t.get('text', '?')}", day=day,
                          description=str(t.get("notes") or ""), category="task"))
    return out


def _birthdays(lo: date, hi: date) -> List[List[str]]:
    import people
    out = []
    for p in _rows("people"):
        nb = people.next_birthday(p, lo)
        if not nb:
            continue
        day = _day(nb["date"])
        if day is None or day > hi:
            continue
        turning = f" (turns {nb['turning']})" if nb.get("turning") else ""
        out.append(_event(f"birthday-{p.get('id')}", f"Birthday: {p.get('name', '?')}{turning}", day=day,
                          rrule="FREQ=YEARLY", category="birthday"))
    return out


def _dated(name: str, prefix: str, label: str, field: str, text: Callable[[Dict[str, Any]], str], lo: date, hi: date,
           category: str) -> List[List[str]]:
    out = []
    for r in _rows(name):
        day = _day(r.get(field))
        if day is None or not lo <= day <= hi:
            continue
        out.append(_event(f"{prefix}-{r.get('id')}", f"{label}{text(r)}", day=day, category=category))
    return out


def _trips(lo: date, hi: date) -> List[List[str]]:
    out = []
    for t in _rows("trips"):
        a, b = _day(t.get("start")), _day(t.get("end"))
        if a is None or b is None or b < a or b < lo or a > hi:
            continue
        where = f" ({t.get('destination')})" if t.get("destination") else ""
        out.append(_event(f"trip-{t.get('id')}", f"Trip: {t.get('name', '?')}{where}", day=a, end_day=b,
                          description=str(t.get("notes") or ""), category="trip"))
    return out


def _chores(lo: date, hi: date) -> List[List[str]]:
    import chores
    out = []
    for c in _rows("chores"):
        day = chores.due_date(c)
        if day is None:
            continue
        day = max(day, lo)  # an overdue chore shows on the first day of the export
        if day > hi:
            continue
        out.append(_event(f"chore-{c.get('id')}", f"Chore: {c.get('name', '?')}", day=day, category="chore"))
    return out


def _renewals(lo: date, hi: date) -> List[List[str]]:
    import subscriptions
    out = []
    span = (hi - clock.today()).days
    for u in subscriptions.upcoming(max(0, span)):
        day = _day(u["date"])
        if day is None or not lo <= day <= hi:
            continue
        s = u["sub"]
        out.append(_event(f"renewal-{s.get('id')}-{u['date']}", f"Renewal: {s.get('name', '?')} ({s.get('amount', 0):g})",
                          day=day, category="renewal"))
    return out


def build(days: int = DEFAULT_DAYS, sections: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """The calendar text and counts per section: {"text", "counts", "total"}.
    Covers today through `days` days ahead (time blocks and tasks from the past
    seven days are kept so a fresh import still shows what just happened)."""
    chosen = list(sections) if sections else list(SECTIONS)
    unknown = [s for s in chosen if s not in SECTIONS]
    if unknown:
        raise ValueError(f"unknown section(s): {', '.join(unknown)}. Choose from {', '.join(SECTIONS)}.")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {MAX_DAYS}.")
    today = clock.today()
    lo, hi = today - timedelta(days=7), today + timedelta(days=days)
    builders: Dict[str, Callable[[], List[List[str]]]] = {
        "blocks": lambda: _blocks(lo, hi), "tasks": lambda: _tasks(lo, hi), "birthdays": lambda: _birthdays(today, hi),
        "countdowns": lambda: _dated("countdowns", "countdown", "", "date", lambda r: str(r.get("name", "Countdown")), today, hi, "countdown"),
        "trips": lambda: _trips(lo, hi),
        "expiries": lambda: _dated("expiries", "expiry", "Expires: ", "date", lambda r: str(r.get("name", "?")), today, hi, "expiry"),
        "chores": lambda: _chores(today, hi), "renewals": lambda: _renewals(today, hi),
        "decisions": lambda: [_event(f"decision-{r.get('id')}", f"Review decision: {r.get('title', '?')}",
                                     day=_day(r.get("review")), category="decision")
                              for r in _rows("decisions") if r.get("status") != "reviewed"
                              and _day(r.get("review")) is not None and today <= _day(r.get("review")) <= hi],
    }
    counts: Dict[str, int] = {}
    body: List[str] = []
    for name in chosen:
        try:
            events = builders[name]()
        except Exception:  # noqa: BLE001 - a broken section is skipped, the rest still export
            events = []
        counts[name] = len(events)
        for ev in events:
            body += ev
    head = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "X-WR-CALNAME:Hermes Life OS"]
    lines = head + body + ["END:VCALENDAR"]
    text = "\r\n".join(fold(line) for line in lines) + "\r\n"
    return {"text": text, "counts": counts, "total": sum(counts.values())}


def export(days: int = DEFAULT_DAYS, sections: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Writes the calendar to exports/calendar-<timestamp>.ics of the active
    profile. Returns {"path", "counts", "total"}."""
    import storage
    result = build(days, sections)
    directory = storage.HERMES_DIR / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"calendar-{clock.now().strftime('%Y-%m-%d-%H%M%S')}.ics"
    path.write_bytes(result["text"].encode("utf-8"))
    return {"path": str(path), "counts": result["counts"], "total": result["total"]}


def format_result(r: Dict[str, Any]) -> str:
    if not r["total"]:
        return f"The calendar file is empty (no dated items in range): {r['path']}"
    parts = ", ".join(f"{k}: {n}" for k, n in r["counts"].items() if n)
    return (f"Exported {r['total']} calendar event{'' if r['total'] == 1 else 's'} ({parts}) to {r['path']}. Import it in Google Calendar "
            f"(Settings > Import & export), Apple Calendar (File > Import) or Outlook.")


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name != "export_calendar":
        return f"Unknown calendar tool: {name}"
    try:
        days = DEFAULT_DAYS if inp.get("days") in (None, "") else inp.get("days")
        sections = inp.get("sections")
        if sections is not None and (not isinstance(sections, list) or not all(isinstance(s, str) for s in sections)):
            raise ValueError("sections must be a list of names.")
        return format_result(export(days, [s.strip().lower() for s in sections] if sections else None))
    except (ValueError, TypeError, OSError) as e:
        return f"Calendar not exported: {e}"
