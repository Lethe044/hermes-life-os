"""
Hermes Life OS - Quick Add
============================
Type a task the way you would say it and Hermes picks it apart: "call Sam
tomorrow #work !high ~30m", "water plants every week", "send invoice by fri
~15m". The pieces it understands are

- a due date: today, tomorrow, a weekday (also "next fri"), YYYY-MM-DD or
  "in 3 days" (a leading "by", "on" or "due" is dropped with it),
- #tags, a !priority (!high, !low, !normal, !urgent ...),
- an estimate with ~: ~30m, ~1h, ~1h30m or ~45 (minutes),
- a repeat: "every day", "every week", "every month", "every weekday" or
  daily, weekly, monthly, weekdays.

What is left is the task text. With preview=true nothing is saved. It creates
an ordinary task through the task module, so everything else (agenda, planning,
workload) sees it. No network call is made.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_MIN_RE = re.compile(r"^~(?:(\d{1,2})h)?(?:(\d{1,3})m(?:in)?)?$|^~(\d{1,3})$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPEAT_WORDS = {"day": "daily", "week": "weekly", "month": "monthly", "weekday": "weekdays", "weekdays": "weekdays"}
_REPEAT_SOLO = {"daily": "daily", "weekly": "weekly", "monthly": "monthly", "weekdays": "weekdays"}
_LEAD = {"by", "on", "due"}
MAX_LINE = 300


def _minutes(token: str) -> Optional[int]:
    m = _MIN_RE.match(token.lower())
    if not m or token == "~":
        return None
    if m.group(3):
        return int(m.group(3))
    h, mi = m.group(1), m.group(2)
    if h is None and mi is None:
        return None
    return int(h or 0) * 60 + int(mi or 0)


def parse(line: Any) -> Dict[str, Any]:
    """{"text", "due", "priority", "tags", "repeat", "minutes"} found in `line`.
    Raises ValueError when the line is empty, a ~estimate or !priority is not
    understood or nothing is left for the task text."""
    import tasks
    if not isinstance(line, str) or not line.strip():
        raise ValueError("say the task in one line, for example: call Sam tomorrow #work !high ~30m")
    if len(line) > MAX_LINE:
        raise ValueError(f"keep it under {MAX_LINE} characters.")
    toks = line.split()
    out: Dict[str, Any] = {"due": None, "priority": None, "tags": [], "repeat": None, "minutes": None}
    keep: List[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        low = t.lower()
        nxt = toks[i + 1].lower() if i + 1 < len(toks) else ""
        nxt2 = toks[i + 2].lower() if i + 2 < len(toks) else ""
        if t.startswith("#") and len(t) > 1:
            tag = tasks.parse_tags([t])
            out["tags"] += [x for x in tag if x not in out["tags"]]
        elif t.startswith("!") and len(t) > 1:
            out["priority"] = tasks.parse_priority(t[1:])
        elif t.startswith("~"):
            mins = _minutes(t)
            if mins is None:
                raise ValueError(f"I did not understand the estimate '{t}'. Use ~30m, ~1h or ~1h30m.")
            out["minutes"] = tasks.parse_minutes(mins)
        elif low == "every" and nxt in _REPEAT_WORDS and out["repeat"] is None:
            out["repeat"] = _REPEAT_WORDS[nxt]
            i += 1
        elif low in _REPEAT_SOLO and out["repeat"] is None:
            out["repeat"] = _REPEAT_SOLO[low]
        elif out["due"] is None and (low in ("today", "tomorrow") or low in tasks._WEEKDAYS or _ISO_RE.match(low)):
            out["due"] = tasks.parse_due(low)
            _drop_lead(keep)
        elif out["due"] is None and low == "next" and nxt in tasks._WEEKDAYS:
            out["due"] = tasks.parse_due(f"next {nxt}")
            _drop_lead(keep)
            i += 1
        elif out["due"] is None and low == "in" and nxt.isdigit() and nxt2 in ("day", "days", "week", "weeks"):
            out["due"] = tasks.parse_due(f"in {nxt} {nxt2}")
            _drop_lead(keep)
            i += 2
        else:
            keep.append(t)
        i += 1
    text = " ".join(keep).strip()
    if not text:
        raise ValueError("there is no task text left once the date, tags and estimate are taken out.")
    out["text"] = text
    return out


def _drop_lead(keep: List[str]) -> None:
    if keep and keep[-1].lower() in _LEAD:
        keep.pop()


def describe(p: Dict[str, Any]) -> str:
    bits = [f"'{p['text']}'"]
    if p["due"]:
        bits.append(f"due {p['due']}")
    if p["priority"]:
        bits.append(f"priority {p['priority']}")
    if p["minutes"]:
        bits.append(f"~{p['minutes']} min")
    if p["repeat"]:
        bits.append(f"repeats {p['repeat']}")
    if p["tags"]:
        bits.append(" ".join("#" + t for t in p["tags"]))
    return ", ".join(bits)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name != "quick_add":
        return f"Unknown quick add tool: {name}"
    try:
        import tasks
        p = parse(inp.get("line"))
        preview = inp.get("preview")
        if preview not in (None, True, False):
            raise ValueError("preview must be true or false.")
        if preview:
            return "Preview, nothing saved: " + describe(p)
        t = tasks.add_task(p["text"], p["due"], p["priority"], p["tags"], p["repeat"], None, p["minutes"])
        return "Task added: " + tasks.format_task(t)
    except (ValueError, TypeError) as e:
        return f"Task not added: {e}"
