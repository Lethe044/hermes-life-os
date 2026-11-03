"""
Hermes Life OS - Life Wheel
=============================
A quick self-check across eight areas of life (health, career, money,
relationships, growth, fun, environment, purpose), each rated 1 to 10. Hermes
keeps every check-in, shows the latest as bars, how each area moved since the
previous check-in and which areas are lowest, and nudges you when it has been
about five weeks since the last one.

Stored in wheel.json as {"id", "date", "scores", "note"} dicts where `scores`
maps area names to whole numbers 1 to 10 (an area can be left out). One
check-in per day: logging again on the same day replaces it. No network call
is made by this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

AREAS = ("health", "career", "money", "relationships", "growth", "fun", "environment", "purpose")
MAX_CHECKINS = 400
MAX_NOTE = 300
NUDGE_AFTER_DAYS = 35
LOW_SCORE = 5
BAR = 10


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_wheel(), lambda r: _storage().save_wheel(r))


def _area(value: Any) -> str:
    key = str(value).strip().lower() if isinstance(value, str) else ""
    if key not in AREAS:
        raise ValueError(f"'{value}' is not one of the areas: {', '.join(AREAS)}.")
    return key


def _scores(value: Any) -> Dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"give some scores as {{area: 1-10}} for: {', '.join(AREAS)}.")
    out: Dict[str, int] = {}
    for k, v in value.items():
        area = _area(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) or not 1 <= v <= 10:
            raise ValueError(f"the score for {area} must be a whole number from 1 to 10.")
        out[area] = int(v)
    return out


def _valid(r: Any) -> bool:
    return (isinstance(r, dict) and isinstance(r.get("scores"), dict) and bool(r["scores"])
            and isinstance(r.get("date"), str))


def checkins() -> List[Dict[str, Any]]:
    """Readable check-ins, oldest first."""
    return sorted((r for r in _load() if _valid(r)), key=lambda r: str(r.get("date")))


# ------------------------------------------------------------------ operations

def log_checkin(scores: Any, note: Any = None) -> Dict[str, Any]:
    """Saves today's check-in (replacing an earlier one from today)."""
    clean = _scores(scores)
    text = kit.clean_text(note, "note", MAX_NOTE, required=False)
    rows = _load()
    today = clock.today_str()
    same = next((r for r in rows if isinstance(r, dict) and r.get("date") == today), None)
    if same is not None:
        merged = dict(same.get("scores") if isinstance(same.get("scores"), dict) else {})
        merged.update(clean)
        same["scores"] = merged
        if text:
            same["note"] = text
        item = same
    else:
        if len(rows) >= MAX_CHECKINS:
            raise ValueError(f"you already have {MAX_CHECKINS} check-ins.")
        item = {"id": kit.new_id(), "date": today, "scores": clean, "note": text}
        rows.append(item)
    _storage().save_wheel(rows)
    return item


def delete_checkin(ref: Any) -> Dict[str, Any]:
    rows = _load()
    key = str(ref).strip().lower() if isinstance(ref, str) else ""
    if not key:
        raise ValueError("say which check-in (its id or its date).")
    hit = next((r for r in kit.only_dicts(rows) if str(r.get("id", "")).lower() == key or r.get("date") == key), None)
    if hit is None:
        raise ValueError(f"no check-in matches '{ref}'. Use get_life_wheel with history to see them.")
    _storage().save_wheel([r for r in rows if r is not hit])
    return hit


def days_since_last() -> Optional[int]:
    got = checkins()
    if not got:
        return None
    try:
        return (clock.today() - clock.parse_day(got[-1]["date"])).days
    except ValueError:
        return None


def changes(latest: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, int]:
    if not previous:
        return {}
    return {a: s - previous["scores"][a] for a, s in latest["scores"].items()
            if isinstance(previous["scores"].get(a), int)}


def lowest(row: Dict[str, Any], count: int = 2) -> List[str]:
    ranked = sorted(row["scores"].items(), key=lambda kv: (kv[1], AREAS.index(kv[0]) if kv[0] in AREAS else 99))
    return [a for a, s in ranked[:count] if s <= LOW_SCORE]


def average(row: Dict[str, Any]) -> float:
    vals = [v for v in row["scores"].values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


def nudges(max_items: int = 1) -> List[str]:
    gap = days_since_last()
    if gap is None or gap < NUDGE_AFTER_DAYS:
        return []
    return [f"It has been {gap} days since your last life wheel check-in. Rate your eight areas with "
            f"log_life_wheel."][:max_items]


# ------------------------------------------------------------------ formatting

def _bar(score: Optional[int]) -> str:
    if not isinstance(score, int):
        return "." * BAR
    return "#" * score + "." * (BAR - score)


def format_wheel(history: bool = False) -> str:
    got = checkins()
    if not got:
        return ("No life wheel check-in yet. Rate any of these areas from 1 to 10 with log_life_wheel: "
                + ", ".join(AREAS) + ".")
    latest = got[-1]
    prev = got[-2] if len(got) > 1 else None
    diff = changes(latest, prev)
    lines = [f"Life wheel on {latest['date']} (average {average(latest):.1f}/10):"]
    for a in AREAS:
        s = latest["scores"].get(a)
        if not isinstance(s, int):
            lines.append(f"- {a:<13} {_bar(None)} not rated")
            continue
        d = diff.get(a)
        mark = "" if not d else f"  ({'+' if d > 0 else ''}{d} since {prev['date']})"
        lines.append(f"- {a:<13} {_bar(s)} {s}/10{mark}")
    low = lowest(latest)
    if low:
        lines.append(f"Needs attention: {', '.join(low)}. Add a goal, task or routine for the lowest one.")
    elif prev is None:
        lines.append("Nothing is low right now. Check in again in a month to see how each area moves.")
    if prev is not None:
        trend = average(latest) - average(prev)
        word = "up" if trend > 0.05 else "down" if trend < -0.05 else "flat"
        lines.append(f"Overall {word} versus {prev['date']} ({average(prev):.1f} to {average(latest):.1f}).")
    if history:
        lines.append(f"History ({kit.plural(len(got), 'check-in')}, newest first):")
        for r in reversed(got[-12:]):
            note = f" - {r['note']}" if r.get("note") else ""
            lines.append(f"- {r['date']}: average {average(r):.1f}, {len(r['scores'])} areas [id={r.get('id', '?')}]{note}")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "log_life_wheel":
            row = log_checkin(inp.get("scores"), inp.get("note"))
            return "Check-in saved.\n" + format_wheel()
        if name == "get_life_wheel":
            return format_wheel(bool(inp.get("history")))
        if name == "delete_wheel_checkin":
            return f"Deleted the check-in from {delete_checkin(inp.get('checkin'))['date']}."
    except (ValueError, TypeError) as e:
        verb = {"log_life_wheel": "Check-in not saved", "get_life_wheel": "Cannot show the life wheel"}.get(
            name, "Check-in not deleted")
        return f"{verb}: {e}"
    return f"Unknown life wheel tool: {name}"
