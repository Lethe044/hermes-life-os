"""
Hermes Life OS - Task Batching
================================
Small tasks of the same kind are cheaper done together: all the calls, all the
errands, all the admin. `batch_tasks` groups your open tasks by tag, shows the
tags with at least two tasks and the time they would take together (15 minutes
for a task without an estimate), and with `tag` plus `apply=true` puts one
time block for the whole batch into the first gap of the day that fits it. The
block's notes list the tasks. Nothing is stored by this module itself and no
network call is made.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import clock
import plannerkit as kit

DEFAULT_MINUTES = 15
MIN_BATCH = 2
ROUND = 5
MAX_SHOWN = 8


def _minutes(t: Dict[str, Any]) -> int:
    m = t.get("minutes")
    return m if isinstance(m, int) and not isinstance(m, bool) and m > 0 else DEFAULT_MINUTES


def batches(tag: Any = None) -> List[Dict[str, Any]]:
    """[{"tag", "tasks": [...], "minutes"}], the largest batch first; with `tag`
    only that tag (any task count)."""
    import tasks
    want = None
    if tag not in (None, ""):
        got = tasks.parse_tags(tag)
        if len(got) != 1:
            raise ValueError("give one tag.")
        want = got[0]
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks._rows(tasks._load()):
        if t.get("done") or not isinstance(t.get("tags"), list):
            continue
        for g in t["tags"]:
            if isinstance(g, str) and (want is None or g == want):
                groups.setdefault(g, []).append(t)
    out = [{"tag": g, "tasks": rows, "minutes": sum(_minutes(t) for t in rows)} for g, rows in groups.items()
           if want or len(rows) >= MIN_BATCH]
    return sorted(out, key=lambda b: (-len(b["tasks"]), -b["minutes"], b["tag"]))


def _hm(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if h and m else f"{h}h" if h else f"{m}m"


def schedule(tag: Any, date: Any = None) -> Dict[str, Any]:
    """Creates the batch block for `tag`; raises ValueError when there is
    nothing to batch or no gap is long enough."""
    import planday
    import timeblocks
    got = batches(tag)
    if not got or not got[0]["tasks"]:
        raise ValueError("no open task has that tag.")
    b = got[0]
    day = timeblocks.parse_date(date)
    need = -(-b["minutes"] // ROUND) * ROUND
    if need > timeblocks.MAX_DURATION:
        raise ValueError("that batch is too long for one block. Split it by another tag.")
    gap = next((g for g in planday._gaps(day) if g[1] - g[0] >= need), None)
    if gap is None:
        raise ValueError(f"no free gap of {_hm(need)} on {day}. Try another date or batch a smaller tag.")
    names = "; ".join(str(t.get("text", "?")) for t in b["tasks"])
    notes = names if len(names) <= timeblocks.MAX_NOTES else names[:timeblocks.MAX_NOTES - 3] + "..."
    block = timeblocks.add_time_block(title=f"Batch: #{b['tag']}"[:timeblocks.MAX_TITLE], start=timeblocks.fmt_time(gap[0]),
                                      end=timeblocks.fmt_time(gap[0] + need), date=day, category="task", notes=notes)
    return {"batch": b, "block": block, "date": day, "minutes": need}


def format_batches(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ("No batches yet: give at least two open tasks the same tag (for example #calls) and Hermes will group them.")
    lines = [f"{len(rows)} {'batch' if len(rows) == 1 else 'batches'} of open tasks (15 min counted for a task without an estimate):"]
    for b in rows[:MAX_SHOWN]:
        names = ", ".join(str(t.get("text", "?")) for t in b["tasks"][:4])
        more = f" and {len(b['tasks']) - 4} more" if len(b["tasks"]) > 4 else ""
        lines.append(f"- #{b['tag']}: {kit.plural(len(b['tasks']), 'task')}, about {_hm(b['minutes'])}: {names}{more}")
    lines.append("Block one with batch_tasks tag=<tag> apply=true.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name != "batch_tasks":
        return f"Unknown batching tool: {name}"
    try:
        apply = inp.get("apply")
        if apply not in (None, True, False):
            raise ValueError("apply must be true or false.")
        if apply:
            if inp.get("tag") in (None, ""):
                raise ValueError("say which tag to batch (tag).")
            r = schedule(inp.get("tag"), inp.get("date"))
            return (f"Batch blocked: {r['block']['title']} on {r['date']} {r['block']['start']}-{r['block']['end']} "
                    f"({_hm(r['minutes'])}) for {kit.plural(len(r['batch']['tasks']), 'task')}.")
        return format_batches(batches(inp.get("tag")))
    except (ValueError, TypeError) as e:
        return f"Cannot batch: {e}"
