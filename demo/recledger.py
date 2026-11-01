"""
Hermes Life OS - Recommendation Ledger
========================================
`get_recommendations` shows what the rules see right now and forgets it. The
ledger keeps each recommendation that was given: when it first and last
appeared, how often, and what you did about it. Mark one followed or skipped
and, for the suggestions that rest on a daily average (sleep, hydration,
stress), the ledger later compares that metric in the week before with the
days after, so a suggestion can be judged by what followed it instead of by
how it sounded.

Stored in recs.json as {"id", "key", "type", "metric", "message", "value",
"first_seen", "last_seen", "times_seen", "status", "note", "resolved_on"}
dicts; `status` is open, followed, skipped or expired (an open one that has
not appeared for 30 days closes itself). The comparison is arithmetic on your
own logs, not proof that the suggestion caused the change, and not medical
advice. No network call is made by this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

MAX_ENTRIES = 200
EXPIRE_DAYS = 30
WINDOW_DAYS = 7
MIN_POINTS = 3
MAX_NOTE = 160
STATUSES = ("open", "followed", "skipped", "expired")
SAME_BAND = 0.03
HISTORY_DAYS = 90


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_recs(), lambda r: _storage().save_recs(r))


def make_key(s: Dict[str, Any]) -> str:
    ident = s.get("metric") or s.get("habit") or " ".join(str(s.get("message", "")).lower().split())[:80]
    return f"{s.get('type', 'other')}:{ident}"


def record(suggestions: Any) -> int:
    """Files the suggestions of today. A suggestion that is already open is
    only marked as seen again (once per day). Returns how many entries are new."""
    if not isinstance(suggestions, list):
        return 0
    rows = _load()
    today = clock.today()
    changed, new = False, 0
    for r in kit.only_dicts(rows):
        if r.get("status") == "open":
            try:
                if (today - clock.parse_day(r.get("last_seen"))).days > EXPIRE_DAYS:
                    r["status"], r["resolved_on"], changed = "expired", today.isoformat(), True
            except ValueError:
                pass
    for s in suggestions:
        if not isinstance(s, dict) or not isinstance(s.get("message"), str) or not s["message"].strip():
            continue
        key = make_key(s)
        open_one = next((r for r in kit.only_dicts(rows) if r.get("key") == key and r.get("status") == "open"), None)
        value = s.get("value") if isinstance(s.get("value"), (int, float)) and not isinstance(s.get("value"), bool) else None
        if open_one:
            open_one["message"] = s["message"].strip()
            if value is not None:
                open_one["value"] = value
            if open_one.get("last_seen") != today.isoformat():
                open_one["last_seen"] = today.isoformat()
                open_one["times_seen"] = int(open_one.get("times_seen") or 1) + 1
            changed = True
            continue
        rows.append({"id": kit.new_id(), "key": key, "type": str(s.get("type", "other")), "metric": s.get("metric") if isinstance(s.get("metric"), str) else None,
                     "message": s["message"].strip(), "value": value, "first_seen": today.isoformat(),
                     "last_seen": today.isoformat(), "times_seen": 1, "status": "open", "note": "", "resolved_on": None})
        new += 1
        changed = True
    if len(rows) > MAX_ENTRIES:
        rows.sort(key=lambda r: (0 if isinstance(r, dict) and r.get("status") != "open" else 1, str(r.get("last_seen")) if isinstance(r, dict) else ""))
        rows = rows[len(rows) - MAX_ENTRIES:]
        rows.sort(key=lambda r: str(r.get("first_seen")) if isinstance(r, dict) else "")
    if changed:
        _storage().save_recs(rows)
    return new


def mark(ref: Any, status: Any, note: Any = None) -> Dict[str, Any]:
    key = str(status).strip().lower() if isinstance(status, str) else ""
    if key not in ("followed", "skipped", "open"):
        raise ValueError("status must be followed, skipped or open.")
    rows = _load()
    row = kit.resolve(rows, ref, "recommendation", "message", "get_recommendation_history")
    row["status"] = key
    row["resolved_on"] = None if key == "open" else clock.today_str()
    if note is not None:
        row["note"] = kit.clean_text(note, "note", MAX_NOTE, required=False)
    _storage().save_recs(rows)
    return row


def listing(status: Any = "open") -> List[Dict[str, Any]]:
    key = "open" if status in (None, "") else str(status).strip().lower()
    if key != "all" and key not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)} or all.")
    rows = kit.only_dicts(_load())
    if key != "all":
        rows = [r for r in rows if r.get("status") == key]
    return sorted(rows, key=lambda r: (str(r.get("last_seen")), str(r.get("id"))), reverse=True)


# ------------------------------------------------------------------ outcomes

def _daily(days: int = HISTORY_DAYS) -> Dict[str, Dict[str, float]]:
    from analytics import daily_averages
    from storage import get_recent_memory
    return daily_averages(get_recent_memory(days))


def outcome(row: Dict[str, Any], daily: Optional[Dict[str, Dict[str, float]]] = None) -> Optional[str]:
    """One sentence comparing the metric behind a followed suggestion in the
    7 days before and the days after. None when the entry has no metric, was
    not followed, or the data is too thin (said so when only the after-part is)."""
    metric = row.get("metric")
    if row.get("status") != "followed" or not isinstance(metric, str):
        return None
    try:
        resolved = clock.parse_day(row.get("resolved_on"))
    except ValueError:
        return None
    if daily is None:
        try:
            daily = _daily()
        except Exception:  # noqa: BLE001
            return None
    today = clock.today()
    before = [daily[d.isoformat()][metric] for d in (resolved - timedelta(days=i) for i in range(1, WINDOW_DAYS + 1))
              if d.isoformat() in daily and metric in daily[d.isoformat()]]
    after_days = [resolved + timedelta(days=i) for i in range(1, WINDOW_DAYS + 1) if resolved + timedelta(days=i) <= today]
    after = [daily[d.isoformat()][metric] for d in after_days if d.isoformat() in daily and metric in daily[d.isoformat()]]
    if len(before) < MIN_POINTS:
        return f"Not enough {metric} logs in the week before to compare."
    if len(after) < MIN_POINTS:
        return f"Too early to compare: {MIN_POINTS - len(after)} more day(s) with {metric} logged are needed."
    b, a = sum(before) / len(before), sum(after) / len(after)
    diff = a - b
    if abs(diff) <= SAME_BAND * max(abs(b), 1.0):
        verdict = "about the same"
    else:
        from recommendations import THRESHOLDS
        direction = THRESHOLDS.get(metric, (0, "below", ""))[1]
        better = diff > 0 if direction == "below" else diff < 0
        verdict = "moving the right way" if better else "not moving the right way"
    return f"{metric} averaged {b:.1f} in the week before and {a:.1f} in the {kit.plural(len(after), 'day')} after ({diff:+.1f}, {verdict})"


# ------------------------------------------------------------------ formatting

def format_row(r: Dict[str, Any], daily: Optional[Dict[str, Dict[str, float]]] = None) -> str:
    seen = f"seen {kit.plural(int(r.get('times_seen') or 1), 'time')}, since {r.get('first_seen')}"
    line = f"{r.get('message', '?')} [{r.get('status', '?')}; {seen}] [id={r.get('id', '?')}]"
    if r.get("resolved_on") and r.get("status") in ("followed", "skipped"):
        line += f"\n    {r['status']} on {r['resolved_on']}" + (f": {r['note']}" if r.get("note") else "")
    elif r.get("note"):
        line += f"\n    note: {r['note']}"
    o = outcome(r, daily)
    if o:
        line += f"\n    {o}"
    return line


def format_all(rows: List[Dict[str, Any]], status: str) -> str:
    if not rows:
        if status == "open":
            return "No open recommendations in the ledger. Ask for get_recommendations first; every suggestion it gives is filed here."
        return f"No {status if status != 'all' else ''} recommendations in the ledger.".replace("  ", " ")
    try:
        daily = _daily() if any(r.get("status") == "followed" and r.get("metric") for r in rows) else None
    except Exception:  # noqa: BLE001
        daily = None
    shown = rows[:15]
    out = [f"{kit.plural(len(rows), 'recommendation')} ({status}):"] + [f"- {format_row(r, daily)}" for r in shown]
    if len(rows) > len(shown):
        out.append(f"... and {len(rows) - len(shown)} more")
    return "\n".join(out)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "get_recommendation_history":
            status = "open" if inp.get("status") in (None, "") else str(inp["status"]).strip().lower()
            return format_all(listing(status), status)
        if name == "mark_recommendation":
            r = mark(inp.get("recommendation"), inp.get("status"), inp.get("note"))
            return "Recommendation updated: " + format_row(r)
    except (ValueError, TypeError) as e:
        verb = {"get_recommendation_history": "Cannot show the ledger"}.get(name, "Recommendation not changed")
        return f"{verb}: {e}"
    return f"Unknown recommendation tool: {name}"
