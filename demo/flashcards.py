"""
Hermes Life OS - Flashcards
=============================
Spaced repetition with the Leitner system. Cards start in box 1. A correct
answer moves a card up one box (it comes back after 1, 3, 7, 16 and 35 days for
boxes 1 to 5); a wrong answer sends it back to box 1 for tomorrow. Hermes shows
the next due card (front only), reveals the back on request, records your
answer and reports how many cards are due, mastered and how often you were right.

Stored in cards.json as {"id", "front", "back", "deck", "box", "due", "added",
"reviews", "correct", "lapses", "last"} dicts. No network call is made by this
module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

INTERVALS = {1: 1, 2: 3, 3: 7, 4: 16, 5: 35}
MAX_CARDS = 3000
MAX_TEXT = 300
MAX_DECK = 40
MAX_BULK = 50
DEFAULT_DECK = "general"


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_cards(), lambda r: _storage().save_cards(r))


def _deck(value: Any) -> str:
    return kit.clean_text(value, "deck", MAX_DECK, required=False).lower() or DEFAULT_DECK


def _new(front: Any, back: Any, deck: str) -> Dict[str, Any]:
    today = clock.today_str()
    return {"id": kit.new_id(), "front": kit.clean_text(front, "front", MAX_TEXT), "back": kit.clean_text(back, "back", MAX_TEXT),
            "deck": deck, "box": 1, "due": today, "added": today, "reviews": 0, "correct": 0, "lapses": 0, "last": None}


def add_cards(cards: Any, deck: Any = None) -> List[Dict[str, Any]]:
    """Adds one or more {"front", "back"} cards (all or none). Duplicate
    fronts within a deck are rejected."""
    if not isinstance(cards, list) or not cards:
        raise ValueError("give at least one card as {front, back}.")
    if len(cards) > MAX_BULK:
        raise ValueError(f"at most {MAX_BULK} cards at a time.")
    d = _deck(deck)
    rows = _load()
    if len(rows) + len(cards) > MAX_CARDS:
        raise ValueError(f"that would pass the limit of {MAX_CARDS} cards.")
    made: List[Dict[str, Any]] = []
    seen = {(r.get("deck"), str(r.get("front", "")).lower()) for r in kit.only_dicts(rows)}
    for c in cards:
        if not isinstance(c, dict):
            raise ValueError("every card must be {front, back}.")
        card = _new(c.get("front"), c.get("back"), _deck(c.get("deck")) if c.get("deck") else d)
        key = (card["deck"], card["front"].lower())
        if key in seen:
            raise ValueError(f"'{card['front']}' is already a card in the {card['deck']} deck.")
        seen.add(key)
        made.append(card)
    rows.extend(made)
    _storage().save_cards(rows)
    return made


def _valid(r: Any) -> bool:
    return isinstance(r, dict) and isinstance(r.get("front"), str) and isinstance(r.get("back"), str) \
        and isinstance(r.get("box"), int) and not isinstance(r.get("box"), bool) and 1 <= r["box"] <= 5


def due_cards(deck: Optional[str] = None) -> List[Dict[str, Any]]:
    today = clock.today_str()
    rows = [r for r in _load() if _valid(r) and str(r.get("due") or "") <= today]
    if deck:
        rows = [r for r in rows if r.get("deck") == deck]
    return sorted(rows, key=lambda r: (str(r.get("due")), r["box"], str(r.get("added"))))


def next_card(deck: Any = None) -> Optional[Dict[str, Any]]:
    d = _deck(deck) if deck not in (None, "") else None
    got = due_cards(d)
    return got[0] if got else None


def _find(ref: Any) -> Dict[str, Any]:
    return kit.resolve([r for r in _load() if _valid(r)], ref, "flashcard", "front", "get_flashcard_stats")


def answer(ref: Any, correct: Any) -> Dict[str, Any]:
    if not isinstance(correct, bool):
        raise ValueError("correct must be true or false.")
    rows = _load()
    card = kit.resolve([r for r in rows if _valid(r)], ref, "flashcard", "front", "get_flashcard_stats")
    today = clock.today()
    if str(card.get("due") or "") > today.isoformat():
        raise ValueError(f"'{card['front']}' is not due until {card['due']}.")
    card["reviews"] = int(card.get("reviews") or 0) + 1
    if correct:
        card["correct"] = int(card.get("correct") or 0) + 1
        card["box"] = min(5, card["box"] + 1)
    else:
        card["lapses"] = int(card.get("lapses") or 0) + 1
        card["box"] = 1
    card["last"] = today.isoformat()
    card["due"] = (today + timedelta(days=INTERVALS[card["box"]])).isoformat()
    _storage().save_cards(rows)
    return card


def delete_card(ref: Any) -> Dict[str, Any]:
    rows = _load()
    card = kit.resolve([r for r in rows if _valid(r)], ref, "flashcard", "front", "get_flashcard_stats")
    _storage().save_cards([r for r in rows if r is not card])
    return card


def stats() -> Dict[str, Any]:
    rows = [r for r in _load() if _valid(r)]
    boxes = {b: sum(1 for r in rows if r["box"] == b) for b in INTERVALS}
    decks: Dict[str, int] = {}
    for r in rows:
        decks[r.get("deck", DEFAULT_DECK)] = decks.get(r.get("deck", DEFAULT_DECK), 0) + 1
    reviews = sum(int(r.get("reviews") or 0) for r in rows)
    right = sum(int(r.get("correct") or 0) for r in rows)
    return {"total": len(rows), "due": len(due_cards()), "boxes": boxes, "decks": decks, "reviews": reviews,
            "accuracy": (right / reviews) if reviews else None}


def nudges(max_items: int = 1) -> List[str]:
    n = len(due_cards())
    return [f"{kit.plural(n, 'flashcard')} due for review. Run review_flashcards."][:max_items] if n else []


def agenda_lines() -> List[str]:
    n = len(due_cards())
    return [f"{kit.plural(n, 'flashcard')} due"] if n else []


def format_stats(s: Dict[str, Any]) -> str:
    if not s["total"]:
        return "No flashcards yet. Add some with add_flashcards."
    lines = [f"Flashcards: {s['total']} in {kit.plural(len(s['decks']), 'deck')}, {s['due']} due today."]
    lines.append("Boxes: " + ", ".join(f"{b}: {n}" for b, n in s["boxes"].items()) + f" ({s['boxes'][5]} mastered).")
    if s["accuracy"] is not None:
        lines.append(f"Answered {kit.plural(s['reviews'], 'time')}, {s['accuracy'] * 100:.0f}% right.")
    lines.append("Decks: " + ", ".join(f"{d} ({n})" for d, n in sorted(s["decks"].items())) + ".")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "add_flashcards":
            made = add_cards(inp.get("cards"), inp.get("deck"))
            return f"Added {kit.plural(len(made), 'flashcard')} to the {made[0]['deck']} deck."
        if name == "review_flashcards":
            card = next_card(inp.get("deck"))
            left = len(due_cards(_deck(inp.get("deck")) if inp.get("deck") else None))
            if card is None:
                return "No flashcards are due. Come back tomorrow, or add more with add_flashcards."
            return (f"Card [id={card['id']}] from the {card['deck']} deck (box {card['box']}, {left} due):\n"
                    f"Q: {card['front']}\nThink of the answer, then call reveal_flashcard.")
        if name == "reveal_flashcard":
            card = _find(inp.get("card"))
            return f"Q: {card['front']}\nA: {card['back']}\nThen record it with answer_flashcard (correct true or false)."
        if name == "answer_flashcard":
            card = answer(inp.get("card"), inp.get("correct"))
            verdict = "Correct" if inp.get("correct") else "Missed"
            nxt = next_card(card["deck"])
            more = f" Next due card is waiting in {card['deck']}." if nxt else " Nothing else is due in this deck."
            return f"{verdict}. '{card['front']}' is in box {card['box']} and returns on {card['due']}.{more}"
        if name == "get_flashcard_stats":
            return format_stats(stats())
        if name == "delete_flashcard":
            return f"Deleted the flashcard '{delete_card(inp.get('card'))['front']}'."
    except (ValueError, TypeError) as e:
        verb = {"add_flashcards": "Flashcards not added", "review_flashcards": "Cannot review",
                "reveal_flashcard": "Cannot reveal", "answer_flashcard": "Answer not recorded"}.get(name, "Flashcard not deleted")
        return f"{verb}: {e}"
    return f"Unknown flashcard tool: {name}"
