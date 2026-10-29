"""
Hermes Life OS - Decision Journal
===================================
Write down a decision while you still remember why: the options, what you
chose, your reasoning, what you expect and how sure you are. Hermes sets a
review date (30 days by default), nudges when it arrives and asks how it
turned out. Reviewed decisions show how your confidence compares with the
outcomes, so you can see whether your sure calls really went better.

Stored in decisions.json as {"id", "title", "options", "choice", "reasoning",
"expected", "confidence", "review", "status", "outcome", "rating", "lessons",
"created", "reviewed_on"} dicts; `status` is open or reviewed, `confidence`
1 to 10, `rating` 1 to 5 and `review` "YYYY-MM-DD". No network call is made by
this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

MAX_DECISIONS = 300
MAX_TITLE = 100
MAX_OPTIONS = 10
MAX_OPTION = 60
MAX_TEXT = 300
DEFAULT_REVIEW_DAYS = 30
MIN_FOR_CALIBRATION = 3
HIGH_CONFIDENCE = 8


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_decisions(), lambda r: _storage().save_decisions(r))


def _scale(value: Any, what: str, low: int, high: int) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not low <= value <= high:
        raise ValueError(f"{what} must be a whole number from {low} to {high}.")
    return int(value)


def _options(value: Any) -> List[str]:
    if value is None or value == []:
        return []
    if isinstance(value, str):
        value = [p for p in value.replace(";", ",").split(",")]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError("options must be a list of short texts.")
    out = [kit.clean_text(v, "option", MAX_OPTION) for v in value if v.strip()]
    if len(out) > MAX_OPTIONS:
        raise ValueError(f"at most {MAX_OPTIONS} options.")
    return out


def _review(value: Any) -> str:
    import tasks
    if value is None or (isinstance(value, str) and not value.strip()):
        return (clock.today() + timedelta(days=DEFAULT_REVIEW_DAYS)).isoformat()
    try:
        got = tasks.parse_due(value)
    except ValueError:
        raise ValueError("I couldn't understand the review date. Use YYYY-MM-DD, tomorrow, in 30 days or a weekday.") from None
    if got is not None and got < clock.today_str():
        raise ValueError("the review date cannot be in the past.")
    return got or _review(None)


# ------------------------------------------------------------------ operations

def add_decision(title: Any, options: Any = None, choice: Any = None, reasoning: Any = None, expected: Any = None,
                 confidence: Any = None, review: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(title, "decision", MAX_TITLE)
    opts = _options(options)
    pick = kit.clean_text(choice, "choice", MAX_OPTION, required=False)
    if pick and opts and pick.lower() not in [o.lower() for o in opts]:
        opts.append(pick)
        if len(opts) > MAX_OPTIONS:
            raise ValueError(f"at most {MAX_OPTIONS} options.")
    rows = _load()
    if len(rows) >= MAX_DECISIONS:
        raise ValueError(f"you already have {MAX_DECISIONS} decisions.")
    item = {"id": kit.new_id(), "title": clean, "options": opts, "choice": pick,
            "reasoning": kit.clean_text(reasoning, "reasoning", MAX_TEXT, required=False),
            "expected": kit.clean_text(expected, "expected outcome", MAX_TEXT, required=False),
            "confidence": _scale(confidence, "confidence", 1, 10), "review": _review(review), "status": "open",
            "outcome": "", "rating": None, "lessons": "", "created": clock.today_str(), "reviewed_on": None}
    rows.append(item)
    _storage().save_decisions(rows)
    return item


def review_decision(ref: Any, outcome: Any, rating: Any, lessons: Any = None) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "decision", "title", "get_decisions")
    if item.get("status") == "reviewed":
        raise ValueError(f"'{item['title']}' was already reviewed on {item.get('reviewed_on')}. "
                         f"Use update_decision to change the notes.")
    text = kit.clean_text(outcome, "outcome", MAX_TEXT)
    score = _scale(rating, "rating", 1, 5)
    if score is None:
        raise ValueError("rate how it turned out from 1 (bad) to 5 (great).")
    item.update({"status": "reviewed", "outcome": text, "rating": score,
                 "lessons": kit.clean_text(lessons, "lessons", MAX_TEXT, required=False), "reviewed_on": clock.today_str()})
    _storage().save_decisions(rows)
    return item


def update_decision(ref: Any, fields: Any) -> Dict[str, Any]:
    kit.check_fields(fields, ("title", "options", "choice", "reasoning", "expected", "confidence", "review", "outcome", "lessons"))
    rows = _load()
    item = kit.resolve(rows, ref, "decision", "title", "get_decisions")
    changes: Dict[str, Any] = {}
    if "title" in fields:
        changes["title"] = kit.clean_text(fields["title"], "decision", MAX_TITLE)
    if "options" in fields:
        changes["options"] = _options(fields["options"])
    if "choice" in fields:
        changes["choice"] = kit.clean_text(fields["choice"], "choice", MAX_OPTION, required=False)
    if "reasoning" in fields:
        changes["reasoning"] = kit.clean_text(fields["reasoning"], "reasoning", MAX_TEXT, required=False)
    if "expected" in fields:
        changes["expected"] = kit.clean_text(fields["expected"], "expected outcome", MAX_TEXT, required=False)
    if "confidence" in fields:
        changes["confidence"] = _scale(fields["confidence"], "confidence", 1, 10)
    if "review" in fields:
        changes["review"] = _review(fields["review"])
    if "outcome" in fields:
        changes["outcome"] = kit.clean_text(fields["outcome"], "outcome", MAX_TEXT, required=False)
    if "lessons" in fields:
        changes["lessons"] = kit.clean_text(fields["lessons"], "lessons", MAX_TEXT, required=False)
    item.update(changes)
    _storage().save_decisions(rows)
    return item


def delete_decision(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "decision", "title", "get_decisions")
    _storage().save_decisions([r for r in rows if r is not item])
    return item


def due_for_review(within: int = 0) -> List[Dict[str, Any]]:
    """Open decisions whose review date is within `within` days (or passed),
    the oldest first, as {"item", "in_days"}."""
    today = clock.today()
    out = []
    for r in kit.only_dicts(_load()):
        if r.get("status") == "reviewed":
            continue
        try:
            left = (clock.parse_day(r.get("review")) - today).days
        except ValueError:
            continue
        if left <= within:
            out.append({"item": r, "in_days": left})
    out.sort(key=lambda x: (x["in_days"], str(x["item"].get("title", "")).lower()))
    return out


def calibration(rows: List[Dict[str, Any]]) -> Optional[str]:
    """One sentence comparing outcomes with confidence for reviewed decisions,
    or None when there are fewer than three rated ones."""
    rated = [r for r in rows if r.get("status") == "reviewed" and isinstance(r.get("rating"), int)]
    if len(rated) < MIN_FOR_CALIBRATION:
        return None
    avg = sum(r["rating"] for r in rated) / len(rated)
    text = f"{len(rated)} reviewed decisions averaged {avg:.1f}/5"
    sure = [r["rating"] for r in rated if isinstance(r.get("confidence"), int) and r["confidence"] >= HIGH_CONFIDENCE]
    unsure = [r["rating"] for r in rated if isinstance(r.get("confidence"), int) and r["confidence"] < HIGH_CONFIDENCE]
    if sure and unsure:
        text += (f"; the ones you were sure about ({HIGH_CONFIDENCE}+ out of 10) averaged "
                 f"{sum(sure) / len(sure):.1f}/5, the others {sum(unsure) / len(unsure):.1f}/5")
    return text + "."


def nudges(max_items: int = 1) -> List[str]:
    return [f"Time to review your decision '{x['item']['title']}' ({kit.when_text(x['in_days'])})."
            if x["in_days"] < 0 else f"Time to review your decision '{x['item']['title']}'."
            for x in due_for_review()[:max_items]]


def agenda_lines() -> List[str]:
    return [f"{x['item']['title']} (review {'due today' if x['in_days'] == 0 else 'was due ' + kit.when_text(x['in_days'])})"
            for x in due_for_review()]


# ------------------------------------------------------------------ formatting

def format_decision(r: Dict[str, Any]) -> str:
    chosen = f": chose '{r['choice']}'" if r.get("choice") else ""
    conf = f" (confidence {r['confidence']}/10)" if isinstance(r.get("confidence"), int) else ""
    if r.get("status") == "reviewed":
        tail = f", turned out {r.get('rating')}/5: {r.get('outcome', '')}"
        if r.get("lessons"):
            tail += f"; lesson: {r['lessons']}"
    else:
        try:
            left = (clock.parse_day(r.get("review")) - clock.today()).days
            tail = f", review {r['review']} ({kit.when_text(left)})"
        except ValueError:
            tail = ""
    return f"{r.get('title', '?')}{chosen}{conf}{tail} [id={r.get('id', '?')}]"


def format_all(rows: List[Dict[str, Any]], mode: str) -> str:
    if not rows:
        return {"due": "No decision is waiting for a review.",
                "reviewed": "No reviewed decisions yet. Review one with review_decision."}.get(
            mode, "No decisions to show. Write one down with add_decision.")
    lines = [f"{kit.plural(len(rows), 'decision')} ({mode}):"] + [f"- {format_decision(r)}" for r in rows]
    cal = calibration(rows if mode != "all" else rows)
    if cal and mode in ("reviewed", "all"):
        lines.append(cal)
    return "\n".join(lines)


def listing(mode: str) -> List[Dict[str, Any]]:
    rows = kit.only_dicts(_load())
    if mode == "due":
        return [x["item"] for x in due_for_review()]
    if mode == "open":
        rows = [r for r in rows if r.get("status") != "reviewed"]
        return sorted(rows, key=lambda r: str(r.get("review") or "9999"))
    if mode == "reviewed":
        return sorted((r for r in rows if r.get("status") == "reviewed"), key=lambda r: str(r.get("reviewed_on") or ""), reverse=True)
    return sorted(rows, key=lambda r: str(r.get("created") or ""), reverse=True)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_decision":
            r = add_decision(inp.get("title"), inp.get("options"), inp.get("choice"), inp.get("reasoning"),
                             inp.get("expected"), inp.get("confidence"), inp.get("review"))
            return "Decision saved: " + format_decision(r)
        if name == "get_decisions":
            mode = str(inp.get("status") or "open").strip().lower()
            if mode not in ("open", "due", "reviewed", "all"):
                raise ValueError("status must be open, due, reviewed or all.")
            return format_all(listing(mode), mode)
        if name == "review_decision":
            return "Reviewed: " + format_decision(review_decision(inp.get("decision"), inp.get("outcome"),
                                                                  inp.get("rating"), inp.get("lessons")))
        if name == "update_decision":
            return "Decision updated: " + format_decision(update_decision(inp.get("decision"), inp.get("fields")))
        if name == "delete_decision":
            return f"Deleted decision {delete_decision(inp.get('decision'))['title']}. This can't be undone."
    except (ValueError, TypeError) as e:
        verb = {"add_decision": "Decision not saved", "get_decisions": "Cannot show decisions",
                "review_decision": "Decision not reviewed"}.get(name, "Decision not changed")
        return f"{verb}: {e}"
    return f"Unknown decision tool: {name}"
