"""Flashcards (Leitner spaced repetition)."""

from __future__ import annotations

from datetime import datetime


def add(d, deck=None, n=2):
    cards = [{"front": f"Q{i}", "back": f"A{i}"} for i in range(n)]
    args = {"cards": cards}
    if deck:
        args["deck"] = deck
    return d("add_flashcards", args)


def first_id(d):
    return d("review_flashcards", {}).split("id=")[1].split("]")[0]


def test_add_and_validation(planner):
    d = planner.dispatch_tool
    assert add(d, "Spanish") == "Added 2 flashcards to the spanish deck."
    assert "already a card" in add(d, "spanish", 1)
    assert d("add_flashcards", {}).startswith("Flashcards not added:")
    assert d("add_flashcards", {"cards": ["x"]}).startswith("Flashcards not added:")
    assert d("add_flashcards", {"cards": [{"front": "", "back": "x"}]}).startswith("Flashcards not added:")
    assert "at most 50" in d("add_flashcards", {"cards": [{"front": str(i), "back": "b"} for i in range(51)]})


def test_bulk_add_is_all_or_nothing(planner):
    import flashcards
    d = planner.dispatch_tool
    out = d("add_flashcards", {"cards": [{"front": "ok", "back": "1"}, {"front": "bad"}]})
    assert out.startswith("Flashcards not added:") and flashcards._load() == []


def test_leitner_progression_and_reset(planner):
    import flashcards
    d = planner.dispatch_tool
    add(d, n=1)
    cid = first_id(d)
    assert "box 2 and returns on 2026-10-16" in d("answer_flashcard", {"card": cid, "correct": True})
    assert "not due until 2026-10-16" in d("answer_flashcard", {"card": cid, "correct": True})
    for day, box, back in ((16, 3, "2026-10-23"), (23, 4, "2026-11-08"), (11, 5, None)):
        planner.set_now(datetime(2026, 10 if day != 11 else 11, day if day != 11 else 8, 9, 0))
        out = d("answer_flashcard", {"card": cid, "correct": True})
        assert f"box {box}" in out
    planner.set_now(datetime(2026, 12, 20, 9, 0))
    out = d("answer_flashcard", {"card": cid, "correct": False})
    assert "box 1 and returns on 2026-12-21" in out
    card = flashcards._load()[0]
    assert card["lapses"] == 1 and card["reviews"] == 5 and card["correct"] == 4


def test_review_reveal_and_nothing_due(planner):
    d = planner.dispatch_tool
    assert d("review_flashcards", {}).startswith("No flashcards are due")
    add(d, n=1)
    out = d("review_flashcards", {})
    assert "Q: Q0" in out and "A0" not in out
    assert "A: A0" in d("reveal_flashcard", {"card": "Q0"})
    assert d("review_flashcards", {"deck": "nothing"}).startswith("No flashcards are due")


def test_answer_needs_a_real_bool_and_card(planner):
    d = planner.dispatch_tool
    add(d, n=1)
    assert d("answer_flashcard", {"card": "Q0", "correct": "yes"}).startswith("Answer not recorded:")
    assert d("answer_flashcard", {"card": "zzz", "correct": True}).startswith("Answer not recorded:")


def test_stats_nudge_agenda_delete(planner):
    import flashcards
    d = planner.dispatch_tool
    assert d("get_flashcard_stats", {}).startswith("No flashcards yet")
    add(d, "a", 3)
    out = d("get_flashcard_stats", {})
    assert "3 in 1 deck, 3 due today" in out and "Decks: a (3)" in out
    assert "3 flashcards due" in flashcards.nudges()[0] and flashcards.agenda_lines() == ["3 flashcards due"]
    cid = first_id(d)
    d("answer_flashcard", {"card": cid, "correct": True})
    assert "Answered 1 time, 100% right" in d("get_flashcard_stats", {})
    assert "Deleted the flashcard" in d("delete_flashcard", {"card": cid})
    assert d("delete_flashcard", {"card": cid}).startswith("Flashcard not deleted:")


def test_damaged_rows_are_ignored(planner):
    import flashcards, storage
    storage.save_cards([{"front": "x", "back": "y", "box": 9, "due": "2026-10-01"}, "junk", {"front": 1}])
    assert flashcards.due_cards() == [] and flashcards.stats()["total"] == 0
