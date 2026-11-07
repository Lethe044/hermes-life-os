"""
Hermes Life OS - Weekly Review
================================
A guided end-of-week ritual. `start_weekly_review` shows the facts of the week
(finished tasks, priorities, time blocks, the life wheel, what is overdue, what
is waiting in the inbox) with three questions. `save_weekly_review` keeps your
answers (wins, lessons, focus for next week, a 1 to 5 rating of the week) and
can turn the focus items into tasks. Past reviews can be listed.

Stored in reviews.json as {"id", "week", "saved", "wins", "lessons", "focus",
"rating"} dicts; `week` is the Monday of the reviewed week. One review per
week: saving again replaces it. No network call is made by this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

MAX_REVIEWS = 300
MAX_TEXT = 400
MAX_FOCUS = 5
NUDGE_FROM_WEEKDAY = 4      # Friday, Saturday and Sunday ask for the review


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_reviews(), lambda r: _storage().save_reviews(r))


def week_start(day: Optional[Any] = None) -> str:
    d = clock.parse_day(day) if day else clock.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def reviews() -> List[Dict[str, Any]]:
    return sorted((r for r in kit.only_dicts(_load()) if isinstance(r.get("week"), str)),
                  key=lambda r: r["week"], reverse=True)


def facts() -> Dict[str, Any]:
    """The numbers of the last seven days, each section left out when it
    cannot be read."""
    out: Dict[str, Any] = {}
    today = clock.today()
    first = (today - timedelta(days=6)).isoformat()
    try:
        import tasks
        rows = tasks._rows(tasks._load())
        out["done"] = [str(t.get("text", "?")) for t in rows if t.get("done") and str(t.get("done_date") or "") >= first]
        out["overdue"] = [str(t.get("text", "?")) for t in tasks.summary()["overdue"]]
    except Exception:  # noqa: BLE001
        pass
    try:
        import priorities
        prs = [r for r in kit.only_dicts(priorities._load()) if str(r.get("date") or "") >= first]
        out["priorities"] = (sum(1 for r in prs if r.get("done")), len(prs))
    except Exception:  # noqa: BLE001
        pass
    try:
        import timeblocks
        blocks = [b for b in kit.only_dicts(timeblocks._load()) if first <= str(b.get("date") or "") <= today.isoformat() and b.get("done")]
        mins = sum((timeblocks.span(b) or (0, 0))[1] - (timeblocks.span(b) or (0, 0))[0] for b in blocks)
        out["blocks"] = (len(blocks), mins)
    except Exception:  # noqa: BLE001
        pass
    try:
        import wheel
        got = wheel.checkins()
        if got:
            out["wheel"] = (got[-1]["date"], wheel.lowest(got[-1]))
    except Exception:  # noqa: BLE001
        pass
    try:
        import inbox
        out["inbox"] = len(inbox.listing())
    except Exception:  # noqa: BLE001
        pass
    return out


def start_text() -> str:
    f = facts()
    week = week_start()
    lines = [f"Weekly review for the week of {week}"]
    done = f.get("done", [])
    lines.append(f"- Tasks finished: {len(done)}" + (f" (e.g. {', '.join(done[:3])})" if done else ""))
    if "priorities" in f and f["priorities"][1]:
        lines.append(f"- Priorities done: {f['priorities'][0]} of {f['priorities'][1]}")
    if "blocks" in f and f["blocks"][0]:
        lines.append(f"- Time blocks done: {f['blocks'][0]} ({f['blocks'][1] / 60:.1f} h)")
    if f.get("overdue"):
        lines.append(f"- Overdue: {len(f['overdue'])} (e.g. {', '.join(f['overdue'][:3])})")
    if f.get("inbox"):
        lines.append(f"- Inbox: {kit.plural(f['inbox'], 'unsorted item')}")
    if "wheel" in f:
        low = f"; lowest: {', '.join(f['wheel'][1])}" if f["wheel"][1] else ""
        lines.append(f"- Life wheel last checked {f['wheel'][0]}{low}")
    prev = next((r for r in reviews() if r["week"] < week), None)
    if prev and prev.get("focus"):
        lines.append(f"- Last week you wanted to focus on: {', '.join(prev['focus'])}")
    if any(r["week"] == week for r in reviews()):
        lines.append("A review for this week is already saved; saving again replaces it.")
    lines += ["Answer with save_weekly_review:",
              "1. What went well this week? (wins)", "2. What did you learn or want to change? (lessons)",
              "3. What are the up to five things to focus on next week? (focus)"]
    return "\n".join(lines)


def _list(value: Any, what: str, limit: int) -> List[str]:
    if value is None or value == []:
        return []
    if isinstance(value, str):
        value = [p for p in value.replace(";", "\n").split("\n")]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{what} must be a list of short texts.")
    out = [kit.clean_text(v, what, 100) for v in value if v.strip()]
    if len(out) > limit:
        raise ValueError(f"at most {limit} {what} items.")
    return out


def save_review(wins: Any = None, lessons: Any = None, focus: Any = None, rating: Any = None,
                create_tasks: Any = False) -> Dict[str, Any]:
    w = kit.clean_text(wins, "wins", MAX_TEXT, required=False)
    l = kit.clean_text(lessons, "lessons", MAX_TEXT, required=False)
    f = _list(focus, "focus", MAX_FOCUS)
    if rating in (None, ""):
        score = None
    elif isinstance(rating, bool) or not isinstance(rating, (int, float)) or rating != int(rating) or not 1 <= rating <= 5:
        raise ValueError("rating must be a whole number from 1 to 5.")
    else:
        score = int(rating)
    if create_tasks not in (None, True, False):
        raise ValueError("create_tasks must be true or false.")
    if not (w or l or f or score):
        raise ValueError("give at least wins, lessons, focus or a rating.")
    rows = _load()
    week = week_start()
    row = next((r for r in kit.only_dicts(rows) if r.get("week") == week), None)
    if row is None:
        if len(rows) >= MAX_REVIEWS:
            raise ValueError(f"you already have {MAX_REVIEWS} reviews.")
        row = {"id": kit.new_id()}
        rows.append(row)
    row.update({"week": week, "saved": clock.today_str(), "wins": w, "lessons": l, "focus": f, "rating": score})
    _storage().save_reviews(rows)
    made: List[str] = []
    if create_tasks and f:
        import tasks
        nxt = (clock.parse_day(week) + timedelta(days=7)).isoformat()
        for item in f:
            try:
                made.append(tasks.add_task(item, nxt)["text"])
            except ValueError:
                continue
    row = dict(row)
    row["_tasks"] = made
    return row


def delete_review(ref: Any) -> Dict[str, Any]:
    rows = _load()
    key = str(ref).strip().lower() if isinstance(ref, str) else ""
    hit = next((r for r in kit.only_dicts(rows) if key and (str(r.get("id", "")).lower() == key or r.get("week") == key)), None)
    if hit is None:
        raise ValueError("say which review (its id or the Monday date of its week). Use get_weekly_reviews to see them.")
    _storage().save_reviews([r for r in rows if r is not hit])
    return hit


def nudges(max_items: int = 1) -> List[str]:
    got = reviews()
    if not got or clock.today().weekday() < NUDGE_FROM_WEEKDAY:
        return []
    if got[0]["week"] == week_start():
        return []
    return ["Time for your weekly review. Run start_weekly_review."][:max_items]


def format_reviews(limit: int = 5) -> str:
    got = reviews()
    if not got:
        return "No weekly reviews saved yet. Start one with start_weekly_review."
    lines = [f"{kit.plural(len(got), 'weekly review')} (newest first):"]
    for r in got[:limit]:
        rate = f", rated {r['rating']}/5" if isinstance(r.get("rating"), int) else ""
        lines.append(f"- Week of {r['week']}{rate} [id={r.get('id', '?')}]")
        for label, key in (("Wins", "wins"), ("Lessons", "lessons")):
            if r.get(key):
                lines.append(f"    {label}: {r[key]}")
        if r.get("focus"):
            lines.append(f"    Focus: {', '.join(r['focus'])}")
    rated = [r["rating"] for r in got if isinstance(r.get("rating"), int)]
    if len(rated) >= 3:
        lines.append(f"Average rating across {len(rated)} weeks: {sum(rated) / len(rated):.1f}/5.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "start_weekly_review":
            return start_text()
        if name == "save_weekly_review":
            r = save_review(inp.get("wins"), inp.get("lessons"), inp.get("focus"), inp.get("rating"), inp.get("create_tasks"))
            text = f"Weekly review saved for the week of {r['week']}."
            if r["_tasks"]:
                text += f" Created {kit.plural(len(r['_tasks']), 'task')} due next Monday: {', '.join(r['_tasks'])}."
            return text
        if name == "get_weekly_reviews":
            lim = inp.get("limit", 5)
            if isinstance(lim, bool) or not isinstance(lim, int) or not 1 <= lim <= 52:
                raise ValueError("limit must be a whole number from 1 to 52.")
            return format_reviews(lim)
        if name == "delete_weekly_review":
            return f"Deleted the review for the week of {delete_review(inp.get('review'))['week']}."
    except (ValueError, TypeError) as e:
        verb = {"save_weekly_review": "Review not saved", "get_weekly_reviews": "Cannot show reviews",
                "start_weekly_review": "Cannot start the review"}.get(name, "Review not deleted")
        return f"{verb}: {e}"
    return f"Unknown weekly review tool: {name}"
