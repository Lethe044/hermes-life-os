"""
Hermes Life OS - Search Everything
====================================
One search over all the planner data that is kept as lists of entries: tasks,
notes, lists, people, subscriptions, savings goals, debts, countdowns, supplies,
symptoms, recipes, the meal plan, trips (with their packing and itinerary),
objectives, time blocks, reminders, habits and goals. Every word of the query
has to appear somewhere in an entry (any case); results are grouped by area, an
entry whose main name matches comes first, and each line carries the id to use
with the tool of that area. Logged entries (meals, sleep, spending and so on)
have their own search (search_logs).

Read-only and network-free; a store that cannot be read is skipped, never an
error.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
MIN_QUERY = 2
MAX_QUERY = 100
MAX_WORDS = 8
MAX_LINE = 110


def _s(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _names(items: Any, key: str) -> List[str]:
    return [_s(i.get(key)) for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _tags(row: Dict[str, Any]) -> List[str]:
    t = row.get("tags")
    return [x for x in t if isinstance(x, str)] if isinstance(t, list) else []


# area -> (loader name, main text, [extra text], describe)
def _spec(loader: str, main: Callable[[Dict[str, Any]], str], extra: Callable[[Dict[str, Any]], List[str]],
          describe: Callable[[Dict[str, Any]], str]) -> Tuple[str, Callable, Callable, Callable]:
    return loader, main, extra, describe


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_LINE else text[:MAX_LINE - 3] + "..."


SOURCES: Dict[str, Tuple[str, Callable, Callable, Callable]] = {
    "tasks": _spec("load_tasks", lambda r: _s(r.get("text")), lambda r: [_s(r.get("notes"))] + _tags(r),
                   lambda r: f"[{'x' if r.get('done') else ' '}] {_s(r.get('text'))}"
                             + (f" (due {r['due']})" if r.get("due") else "")),
    "notes": _spec("load_notes", lambda r: _s(r.get("text")), lambda r: _tags(r),
                   lambda r: _s(r.get("text"))),
    "lists": _spec("load_lists", lambda r: _s(r.get("text")), lambda r: [_s(r.get("list"))],
                   lambda r: f"{_s(r.get('text'))} ({_s(r.get('list')) or 'shopping'}{', done' if r.get('done') else ''})"),
    "people": _spec("load_people", lambda r: _s(r.get("name")), lambda r: [_s(r.get("notes"))],
                    lambda r: _s(r.get("name")) + (f" - {_s(r.get('notes'))}" if _s(r.get("notes")) else "")),
    "subscriptions": _spec("load_subscriptions", lambda r: _s(r.get("name")), lambda r: [_s(r.get("notes")), _s(r.get("category"))],
                           lambda r: f"{_s(r.get('name'))} ({r.get('amount')} {_s(r.get('cycle'))})"),
    "savings": _spec("load_savings", lambda r: _s(r.get("name")), lambda r: [_s(r.get("notes"))],
                     lambda r: f"{_s(r.get('name'))} (target {r.get('target')})"),
    "debts": _spec("load_debts", lambda r: _s(r.get("who")), lambda r: [_s(r.get("notes"))],
                   lambda r: f"{_s(r.get('who'))} ({_s(r.get('direction'))} {r.get('amount')})"),
    "countdowns": _spec("load_countdowns", lambda r: _s(r.get("name")), lambda r: [_s(r.get("notes"))],
                        lambda r: f"{_s(r.get('name'))} ({_s(r.get('date'))})"),
    "supplies": _spec("load_supplies", lambda r: _s(r.get("name")), lambda r: [_s(r.get("notes")), _s(r.get("unit"))],
                      lambda r: f"{_s(r.get('name'))} ({r.get('quantity')} {_s(r.get('unit'))})".replace(" )", ")")),
    "symptoms": _spec("load_symptoms", lambda r: _s(r.get("symptom")),
                      lambda r: [_s(r.get("notes"))] + [t for t in (r.get("triggers") or []) if isinstance(t, str)],
                      lambda r: f"{_s(r.get('symptom'))} {r.get('severity')}/10 on {_s(r.get('date'))}"),
    "recipes": _spec("load_recipes", lambda r: _s(r.get("name")),
                     lambda r: _names(r.get("ingredients"), "name") + _tags(r) + [_s(r.get("notes"))],
                     lambda r: f"{_s(r.get('name'))} (serves {r.get('servings')})"),
    "mealplan": _spec("load_mealplan", lambda r: _s(r.get("name")), lambda r: [_s(r.get("slot"))],
                      lambda r: f"{_s(r.get('date'))} {_s(r.get('slot'))}: {_s(r.get('name'))}"),
    "trips": _spec("load_trips", lambda r: _s(r.get("name")),
                   lambda r: [_s(r.get("destination")), _s(r.get("notes"))] + _names(r.get("packing"), "text")
                   + _names(r.get("itinerary"), "text"),
                   lambda r: f"{_s(r.get('name'))} ({_s(r.get('start'))} to {_s(r.get('end'))})"),
    "okrs": _spec("load_okrs", lambda r: _s(r.get("name")), lambda r: [_s(r.get("notes"))] + _names(r.get("key_results"), "name"),
                  lambda r: f"{_s(r.get('name'))} ({_s(r.get('start'))} to {_s(r.get('end'))})"),
    "timeblocks": _spec("load_timeblocks", lambda r: _s(r.get("title")), lambda r: [_s(r.get("notes")), _s(r.get("category"))],
                        lambda r: f"{_s(r.get('date'))} {_s(r.get('start'))}-{_s(r.get('end'))} {_s(r.get('title'))}"),
    "reminders": _spec("load_reminders", lambda r: _s(r.get("text")), lambda r: [],
                       lambda r: f"{_s(r.get('text'))}" + (f" ({_s(r.get('time'))})" if _s(r.get("time")) else "")),
    "habits": _spec("load_habits", lambda r: _s(r.get("name")), lambda r: [],
                    lambda r: f"{_s(r.get('name'))} (streak {r.get('streak', 0)})"),
    "goals": _spec("load_goals", lambda r: _s(r.get("name")), lambda r: [_s(r.get("metric"))],
                   lambda r: _s(r.get("name"))),
}


def area_names() -> List[str]:
    return list(SOURCES)


def _storage():
    import storage
    return storage


def parse_query(query: Any) -> List[str]:
    if not isinstance(query, str) or len(query.strip()) < MIN_QUERY:
        raise ValueError(f"give at least {MIN_QUERY} characters to search for.")
    if len(query.strip()) > MAX_QUERY:
        raise ValueError(f"the search can be at most {MAX_QUERY} characters.")
    words = query.lower().split()
    if len(words) > MAX_WORDS:
        raise ValueError(f"use at most {MAX_WORDS} words.")
    return words


def _parse_areas(areas: Any) -> List[str]:
    if areas is None or areas == [] or areas == "":
        return area_names()
    if isinstance(areas, str):
        areas = [a for a in areas.replace(";", ",").split(",")]
    if not isinstance(areas, list) or not all(isinstance(a, str) for a in areas):
        raise ValueError("areas must be a list of area names.")
    out: List[str] = []
    for a in areas:
        key = a.strip().lower()
        if not key:
            continue
        if key not in SOURCES:
            raise ValueError(f"unknown area '{a.strip()}'. Areas: {', '.join(SOURCES)}.")
        if key not in out:
            out.append(key)
    return out or area_names()


def _limit(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"limit must be a whole number from 1 to {MAX_LIMIT}.")
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"limit must be a whole number from 1 to {MAX_LIMIT}.") from None
    if n != int(n) or not 1 <= n <= MAX_LIMIT:
        raise ValueError(f"limit must be a whole number from 1 to {MAX_LIMIT}.")
    return int(n)


def search(query: Any, areas: Any = None, limit: Any = DEFAULT_LIMIT) -> Dict[str, Any]:
    """{"query", "areas": {area: {"total", "hits": [{"id", "line"}]}}, "total"}
    for the areas that have at least one match. Raises ValueError for a bad
    query, area or limit."""
    words = parse_query(query)
    chosen = _parse_areas(areas)
    cap = _limit(limit)
    out: Dict[str, Any] = {}
    grand = 0
    for area in chosen:
        loader, main, extra, describe = SOURCES[area]
        try:
            rows = getattr(_storage(), loader)()
        except Exception:  # noqa: BLE001 - an unreadable store is skipped
            continue
        if not isinstance(rows, list):
            continue
        scored = []
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            try:
                head = main(r).lower()
                hay = " ".join([head] + [x.lower() for x in extra(r) if isinstance(x, str)])
                if all(w in hay for w in words):
                    scored.append((0 if all(w in head for w in words) else 1, i, r))
            except Exception:  # noqa: BLE001 - a hand-edited row never breaks the search
                continue
        if not scored:
            continue
        scored.sort(key=lambda t: (t[0], t[1]))
        hits = []
        for _rank, _i, r in scored[:cap]:
            try:
                line = _short(describe(r))
            except Exception:  # noqa: BLE001
                line = "(unreadable entry)"
            hits.append({"id": r.get("id") if isinstance(r.get("id"), str) else None, "line": line})
        out[area] = {"total": len(scored), "hits": hits}
        grand += len(scored)
    return {"query": query.strip(), "areas": out, "total": grand}


def format_results(res: Dict[str, Any]) -> str:
    if not res["total"]:
        return f"Nothing in your planner data matches '{res['query']}'. (Logged entries have their own search: search_logs.)"
    n_areas = len(res["areas"])
    lines = [f"{res['total']} match{'es' if res['total'] != 1 else ''} for '{res['query']}' in "
             f"{n_areas} area{'s' if n_areas != 1 else ''}:"]
    for area, block in res["areas"].items():
        lines.append(f"{area} ({block['total']}):")
        for h in block["hits"]:
            lines.append(f"  - {h['line']}" + (f" [id={h['id']}]" if h["id"] else ""))
        if block["total"] > len(block["hits"]):
            lines.append(f"  ... and {block['total'] - len(block['hits'])} more")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "search_everything":
            return format_results(search(inp.get("query"), inp.get("areas"), DEFAULT_LIMIT if inp.get("limit") is None else inp["limit"]))
    except (ValueError, TypeError) as e:
        return f"Cannot search: {e}"
    return f"Unknown search tool: {name}"
