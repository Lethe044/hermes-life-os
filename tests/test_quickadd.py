"""Quick add."""

from __future__ import annotations

import pytest


def test_parses_every_piece(planner):
    import quickadd
    p = quickadd.parse("call Sam tomorrow #Work #home !urgent ~1h30m")
    assert p == {"text": "call Sam", "due": "2026-10-14", "priority": "high", "tags": ["work", "home"],
                 "repeat": None, "minutes": 90}


@pytest.mark.parametrize("line,due", [
    ("send invoice by fri", "2026-10-16"),
    ("pay rent on 2026-11-01 now", "2026-11-01"),
    ("plan trip next monday", "2026-10-19"),
    ("renew passport in 2 weeks", "2026-10-27"),
    ("do taxes due today", "2026-10-13"),
])
def test_due_phrases_drop_their_lead_word(planner, line, due):
    import quickadd
    got = quickadd.parse(line)
    assert got["due"] == due and " by" not in got["text"] and not got["text"].endswith((" on", " due", " in", " next"))


def test_repeat_and_estimates(planner):
    import quickadd
    assert quickadd.parse("water plants every week")["repeat"] == "weekly"
    assert quickadd.parse("stretch every weekday ~10")["minutes"] == 10
    assert quickadd.parse("backup daily")["repeat"] == "daily"
    assert quickadd.parse("read ~45m")["minutes"] == 45
    assert quickadd.parse("a ~2h")["minutes"] == 120


def test_first_due_wins_and_plain_text_stays(planner):
    import quickadd
    got = quickadd.parse("meet friday or monday")
    assert got["due"] == "2026-10-16" and got["text"] == "meet or monday"
    assert quickadd.parse("think about life")["due"] is None


@pytest.mark.parametrize("line", ["", "   ", "tomorrow #x", "x ~", "x ~abc", "x !nope", "x ~2", "a" * 301, None, 5])
def test_bad_lines_are_refused(planner, line):
    assert planner.dispatch_tool("quick_add", {"line": line}).startswith("Task not added:")


def test_creates_a_real_task_and_preview_does_not(planner):
    d = planner.dispatch_tool
    out = d("quick_add", {"line": "call Sam tomorrow #work !high ~30m", "preview": True})
    assert out.startswith("Preview, nothing saved: 'call Sam', due 2026-10-14, priority high, ~30 min, #work")
    assert d("list_tasks", {}).startswith("No open tasks") or "call Sam" not in d("list_tasks", {})
    out = d("quick_add", {"line": "call Sam tomorrow #work !high ~30m"})
    assert out.startswith("Task added:") and "call Sam" in d("list_tasks", {})
    assert d("quick_add", {"line": "x", "preview": "yes"}).startswith("Task not added:")
