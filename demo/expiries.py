"""
Hermes Life OS - Expiry Dates
===============================
Things that run out on a date and are easy to forget: a passport, a driving
licence, car insurance, a warranty, a gym membership. Each has an expiry date
and a reminder window (30 days by default); Hermes nudges about the most urgent
one once it is inside its window and shows it in the agenda. Renewing moves
the date forward and keeps a short history.

Stored in expiries.json as {"id", "name", "date", "remind_days", "category",
"notes", "created", "history"} dicts; `date` is "YYYY-MM-DD" (the last valid
day), `category` one of document, insurance, license, warranty, membership or
other, and `history` the last 20 renewals as {"renewed_on", "from", "to"}.
No network call is made by this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

MAX_ITEMS = 200
MAX_NAME = 60
MAX_NOTES = 160
MAX_HISTORY = 20
DEFAULT_REMIND = 30
MAX_REMIND = 365
CATEGORIES = ("document", "insurance", "license", "warranty", "membership", "other")
BACK_DAYS = 3650
AHEAD_DAYS = 3650
AGENDA_DAYS = 14
STALE_DAYS = 60          # an item expired longer ago than this is no longer nudged or shown in the agenda
MAX_EXTEND_MONTHS = 120


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_expiries(), lambda r: _storage().save_expiries(r))


def _date(value: Any, what: str = "expiry date") -> str:
    day = clock.parse_day(value)
    today = clock.today()
    if day < today - timedelta(days=BACK_DAYS) or day > today + timedelta(days=AHEAD_DAYS):
        raise ValueError(f"the {what} must be within {BACK_DAYS // 365} years of today.")
    return day.isoformat()


def _remind(value: Any) -> int:
    if value is None or value == "":
        return DEFAULT_REMIND
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not 1 <= value <= MAX_REMIND:
        raise ValueError(f"remind_days must be a whole number from 1 to {MAX_REMIND}.")
    return int(value)


def _category(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "other"
    key = str(value).strip().lower()
    key = {"licence": "license", "id": "document", "passport": "document", "warranties": "warranty"}.get(key, key)
    if key not in CATEGORIES:
        raise ValueError(f"category must be one of {', '.join(CATEGORIES)}.")
    return key


def status(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """{"date", "in_days", "state"} with state expired / soon / ok, or None
    when the date cannot be read."""
    try:
        day = clock.parse_day(item.get("date"))
    except ValueError:
        return None
    left = (day - clock.today()).days
    remind = item.get("remind_days")
    remind = remind if isinstance(remind, int) and not isinstance(remind, bool) and remind >= 1 else DEFAULT_REMIND
    state = "expired" if left < 0 else ("soon" if left <= remind else "ok")
    return {"date": day.isoformat(), "in_days": left, "state": state}


# ------------------------------------------------------------------ operations

def add_expiry(name: Any, date: Any, remind_days: Any = None, category: Any = None, notes: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(name, "name", MAX_NAME)
    day = _date(date)
    remind = _remind(remind_days)
    cat = _category(category)
    rows = _load()
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"you already have {MAX_ITEMS} expiry dates.")
    if any(str(r.get("name", "")).lower() == clean.lower() for r in kit.only_dicts(rows)):
        raise ValueError(f"there is already an expiry date called '{clean}'.")
    item = {"id": kit.new_id(), "name": clean, "date": day, "remind_days": remind, "category": cat,
            "notes": kit.clean_text(notes, "notes", MAX_NOTES, required=False), "created": clock.today_str(), "history": []}
    rows.append(item)
    _storage().save_expiries(rows)
    return item


def renew_expiry(ref: Any, new_date: Any = None, extend_months: Any = None) -> Dict[str, Any]:
    """Move the expiry date forward: to `new_date`, or by `extend_months`
    counted from the current date (from today when it has already passed)."""
    if (new_date in (None, "")) == (extend_months in (None, "")):
        raise ValueError("give either new_date (YYYY-MM-DD) or extend_months (a number of months), not both and not neither.")
    rows = _load()
    item = kit.resolve(rows, ref, "expiry date", "name", "get_expiries")
    old = item.get("date")
    try:
        base = clock.parse_day(old)
    except ValueError:
        base = clock.today()
    if new_date not in (None, ""):
        target = clock.parse_day(_date(new_date, "new expiry date"))
    else:
        if isinstance(extend_months, bool) or not isinstance(extend_months, (int, float)) \
                or extend_months != int(extend_months) or not 1 <= extend_months <= MAX_EXTEND_MONTHS:
            raise ValueError(f"extend_months must be a whole number from 1 to {MAX_EXTEND_MONTHS}.")
        target = clock.add_months(max(base, clock.today()), int(extend_months))
    if target <= base:
        raise ValueError(f"the new date must be later than the current expiry ({old}).")
    item["date"] = target.isoformat()
    hist = item.get("history") if isinstance(item.get("history"), list) else []
    item["history"] = (hist + [{"renewed_on": clock.today_str(), "from": old, "to": item["date"]}])[-MAX_HISTORY:]
    _storage().save_expiries(rows)
    return item


def update_expiry(ref: Any, fields: Any) -> Dict[str, Any]:
    kit.check_fields(fields, ("name", "date", "remind_days", "category", "notes"))
    rows = _load()
    item = kit.resolve(rows, ref, "expiry date", "name", "get_expiries")
    changes: Dict[str, Any] = {}
    if "name" in fields:
        n = kit.clean_text(fields["name"], "name", MAX_NAME)
        if any(r is not item and str(r.get("name", "")).lower() == n.lower() for r in kit.only_dicts(rows)):
            raise ValueError(f"there is already an expiry date called '{n}'.")
        changes["name"] = n
    if "date" in fields:
        changes["date"] = _date(fields["date"])
    if "remind_days" in fields:
        changes["remind_days"] = _remind(fields["remind_days"])
    if "category" in fields:
        changes["category"] = _category(fields["category"])
    if "notes" in fields:
        changes["notes"] = kit.clean_text(fields["notes"], "notes", MAX_NOTES, required=False)
    item.update(changes)
    _storage().save_expiries(rows)
    return item


def delete_expiry(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "expiry date", "name", "get_expiries")
    _storage().save_expiries([r for r in rows if r is not item])
    return item


def listing(only_soon: bool = False) -> List[Dict[str, Any]]:
    """[{"item", "date", "in_days", "state"}], the earliest date first
    (expired ones first). `only_soon` keeps expired and soon-to-expire ones."""
    out = []
    for r in kit.only_dicts(_load()):
        st = status(r)
        if st is None or (only_soon and st["state"] == "ok"):
            continue
        out.append({"item": r, **st})
    out.sort(key=lambda x: (x["date"], str(x["item"].get("name", "")).lower()))
    return out


def attention(max_age: int = STALE_DAYS) -> List[Dict[str, Any]]:
    """Items inside their reminder window, or expired at most `max_age` days ago."""
    return [x for x in listing(True) if x["in_days"] >= -max_age]


def nudges(max_items: int = 1) -> List[str]:
    return [f"{x['item']['name']} {_phrase(x)}." for x in attention()[:max_items]]


def agenda_lines() -> List[str]:
    return [f"{x['item']['name']} {_phrase(x)}" for x in attention() if x["in_days"] <= AGENDA_DAYS]


# ------------------------------------------------------------------ formatting

def _phrase(x: Dict[str, Any]) -> str:
    d = x["in_days"]
    if d < 0:
        return f"expired {kit.when_text(d)} ({x['date']})"
    if d == 0:
        return f"expires today ({x['date']})"
    return f"expires {kit.when_text(d)} ({x['date']})"


def format_expiry(x: Dict[str, Any]) -> str:
    item = x["item"]
    cat = f" [{item['category']}]" if item.get("category") not in (None, "other") else ""
    flag = {"expired": " - renew now", "soon": " - renew soon"}.get(x["state"], "")
    return f"{item['name']}{cat}: {_phrase(x)}{flag} [id={item.get('id', '?')}]"


def format_all(rows: List[Dict[str, Any]], only_soon: bool = False) -> str:
    if not rows:
        return ("Nothing is expiring soon." if only_soon
                else "No expiry dates yet. Add one with add_expiry, for example 'passport expires 2027-03-01'.")
    head = kit.plural(len(rows), "expiry date") + (" expired or expiring soon" if only_soon else "")
    return head + ":\n" + "\n".join(f"- {format_expiry(x)}" for x in rows)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_expiry":
            item = add_expiry(inp.get("name"), inp.get("date"), inp.get("remind_days"), inp.get("category"), inp.get("notes"))
            return "Expiry date added: " + format_expiry({"item": item, **status(item)})
        if name == "get_expiries":
            mode = str(inp.get("filter") or "all").strip().lower()
            if mode not in ("all", "soon"):
                raise ValueError("filter must be all or soon.")
            return format_all(listing(mode == "soon"), mode == "soon")
        if name == "renew_expiry":
            item = renew_expiry(inp.get("item"), inp.get("new_date"), inp.get("extend_months"))
            return "Renewed: " + format_expiry({"item": item, **status(item)})
        if name == "update_expiry":
            item = update_expiry(inp.get("item"), inp.get("fields"))
            st = status(item)
            return "Expiry date updated: " + (format_expiry({"item": item, **st}) if st else item["name"])
        if name == "delete_expiry":
            return f"Deleted expiry date {delete_expiry(inp.get('item'))['name']}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_expiry": "Expiry date not added", "get_expiries": "Cannot show expiry dates",
                "renew_expiry": "Not renewed"}.get(name, "Expiry date not changed")
        return f"{verb}: {e}"
    return f"Unknown expiry tool: {name}"
