"""
Hermes Life OS - Personal Experiments
=======================================
Run a small N-of-1 experiment on yourself: "no caffeine after 2pm", "walk after
dinner", "phone out of the bedroom". You pick one metric Hermes already tracks
(mood, sleep, stress, ...) and a length in days. Hermes compares the days
before the start with the days of the experiment, using the readings you
logged anyway, and reports the average on each side, the change and an effect
size, with a plain verdict (better, worse or no clear effect).

This is a self-experiment, not a clinical trial: the verdict says what the
numbers show, never why. Only one running experiment per metric is allowed so
two changes cannot be mixed up.

Stored in experiments.json as {"id", "name", "metric", "change", "start",
"days", "baseline_days", "status", "created", "concluded", "decision",
"result"} dicts. No network call is made by this module.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Dict, List, Optional

import clock
import metricseries as ms
import plannerkit as kit

STATUSES = ("running", "done")
DECISIONS = ("keep", "drop", "unsure")
MAX_ITEMS = 100
MAX_NAME = 80
MAX_CHANGE = 200
DEFAULT_DAYS = 14
MIN_DAYS, MAX_DAYS = 3, 60
MIN_READINGS = 3
MAX_START_AHEAD = 30
MAX_START_BACK = 60
SMALL = 0.3


def _storage():
    import storage
    return storage


def _load() -> List[Dict[str, Any]]:
    return kit.load_rows(lambda: _storage().load_experiments(), lambda r: _storage().save_experiments(r))


def _whole(value: Any, what: str, default: int) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) \
            or not MIN_DAYS <= value <= MAX_DAYS:
        raise ValueError(f"{what} must be a whole number from {MIN_DAYS} to {MAX_DAYS}.")
    return int(value)


def _start(value: Any) -> str:
    if value in (None, ""):
        return clock.today_str()
    import tasks
    day = tasks.parse_due(value)
    today = clock.today()
    got = clock.parse_day(day)
    if got < today - timedelta(days=MAX_START_BACK) or got > today + timedelta(days=MAX_START_AHEAD):
        raise ValueError(f"the start can be at most {MAX_START_BACK} days back or {MAX_START_AHEAD} days ahead.")
    return day


def _valid(r: Any) -> bool:
    try:
        return (isinstance(r, dict) and isinstance(r.get("name"), str) and bool(r["name"].strip()) and r.get("metric") in ms.METRICS
                and r.get("status") in STATUSES and isinstance(r.get("days"), int)
                and isinstance(r.get("baseline_days"), int) and bool(clock.parse_day(r.get("start"))))
    except (ValueError, TypeError):
        return False


def end_day(r: Dict[str, Any]) -> str:
    return (clock.parse_day(r["start"]) + timedelta(days=r["days"] - 1)).isoformat()


# ------------------------------------------------------------------ analysis

def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs)


def _sd(xs: List[float]) -> float:
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0.0


def _series(r: Dict[str, Any], daily: Dict[str, Dict[str, float]], upto: str) -> Dict[str, Any]:
    """The readings before and during the experiment, up to `upto`."""
    start = r["start"]
    before = ms.values(daily, r["metric"], ms.day_minus(start, r["baseline_days"]), ms.day_minus(start, 1))
    during = ms.values(daily, r["metric"], start, min(upto, end_day(r)))
    return {"before": before, "during": during}


def analyze(r: Dict[str, Any], daily: Optional[Dict[str, Dict[str, float]]] = None,
            upto: Optional[str] = None) -> Dict[str, Any]:
    """Numbers and verdict for one experiment: {"n_before", "n_during",
    "mean_before", "mean_during", "change", "percent", "effect", "verdict",
    "direction", "strength"}. `verdict` is one of better, worse, no clear
    effect, not enough data."""
    if r["metric"] in ms.STATE:
        return {"verdict": "not enough data", "n_before": 0, "n_during": 0, "state_metric": True}
    got = _series(r, daily if daily is not None else ms.load_daily(), upto or clock.today_str())
    b, d = list(got["before"].values()), list(got["during"].values())
    out: Dict[str, Any] = {"n_before": len(b), "n_during": len(d), "mean_before": None, "mean_during": None,
                           "change": None, "percent": None, "effect": None, "verdict": "not enough data",
                           "direction": None, "strength": None}
    if b:
        out["mean_before"] = _mean(b)
    if d:
        out["mean_during"] = _mean(d)
    if len(b) < MIN_READINGS or len(d) < MIN_READINGS:
        return out
    diff = out["mean_during"] - out["mean_before"]
    pooled = math.sqrt(((len(b) - 1) * _sd(b) ** 2 + (len(d) - 1) * _sd(d) ** 2) / (len(b) + len(d) - 2))
    effect = diff / pooled if pooled > 0 else (0.0 if diff == 0 else math.copysign(9.99, diff))
    out["change"] = diff
    out["percent"] = (diff / out["mean_before"] * 100.0) if out["mean_before"] else None
    out["effect"] = effect
    if abs(effect) < SMALL:
        out["verdict"] = "no clear effect"
        return out
    good_when_up = r["metric"] not in ms.LOWER_IS_BETTER
    better = (diff > 0) == good_when_up
    out["verdict"] = "better" if better else "worse"
    out["direction"] = "up" if diff > 0 else "down"
    size = abs(effect)
    out["strength"] = "small" if size < 0.5 else "moderate" if size < 0.8 else "large"
    return out


# ------------------------------------------------------------------ operations

def start_experiment(name: Any, metric: Any, change: Any = None, days: Any = None, baseline_days: Any = None,
                     start: Any = None) -> Dict[str, Any]:
    clean = kit.clean_text(name, "name", MAX_NAME)
    key = ms.check_metric(metric, allow_state=False)
    length = _whole(days, "days", DEFAULT_DAYS)
    base = _whole(baseline_days, "baseline_days", DEFAULT_DAYS)
    first = _start(start)
    rows = _load()
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"you already have {MAX_ITEMS} experiments.")
    for r in kit.only_dicts(rows):
        if r.get("status") != "running":
            continue
        if str(r.get("name", "")).lower() == clean.lower():
            raise ValueError(f"an experiment called '{r.get('name')}' is already running.")
        if r.get("metric") == key:
            raise ValueError(f"'{r.get('name')}' is still running on {key}. Conclude it first so two changes "
                             f"are not mixed up.")
    item = {"id": kit.new_id(), "name": clean, "metric": key,
            "change": kit.clean_text(change, "change", MAX_CHANGE, required=False), "start": first, "days": length,
            "baseline_days": base, "status": "running", "created": clock.today_str(), "concluded": None,
            "decision": None, "result": None}
    rows.append(item)
    _storage().save_experiments(rows)
    return item


def conclude_experiment(ref: Any, decision: Any = None) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve([r for r in rows if _valid(r)], ref, "experiment", "name", "get_experiments")
    if item.get("status") == "done":
        raise ValueError(f"'{item['name']}' is already concluded.")
    pick = None
    if decision not in (None, ""):
        pick = decision.strip().lower() if isinstance(decision, str) else ""
        if pick not in DECISIONS:
            raise ValueError(f"the decision must be one of {', '.join(DECISIONS)}.")
    res = analyze(item)
    keep = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.items()}
    keep["upto"] = min(clock.today_str(), end_day(item))
    item.update({"status": "done", "concluded": clock.today_str(), "decision": pick, "result": keep})
    _storage().save_experiments(rows)
    return item


def delete_experiment(ref: Any) -> Dict[str, Any]:
    rows = _load()
    item = kit.resolve(rows, ref, "experiment", "name", "get_experiments")
    _storage().save_experiments([r for r in rows if r is not item])
    return item


def listing(status: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = [r for r in _load() if _valid(r)]
    if status:
        rows = [r for r in rows if r["status"] == status]
    return sorted(rows, key=lambda r: (r["status"] != "running", str(r.get("start")), r["name"].lower()),
                  reverse=False)


def finished_waiting() -> List[Dict[str, Any]]:
    """Running experiments whose last day has passed and are not concluded."""
    today = clock.today_str()
    return [r for r in listing("running") if end_day(r) < today]


def nudges(max_items: int = 1) -> List[str]:
    out = []
    for r in finished_waiting():
        ago = (clock.today() - clock.parse_day(end_day(r))).days
        out.append(f"Experiment '{r['name']}' ended {kit.when_text(-ago)}. See the result and close it with "
                   f"conclude_experiment.")
    return out[:max_items]


def agenda_lines() -> List[str]:
    today = clock.today_str()
    return [f"'{r['name']}' ends today" for r in listing("running") if end_day(r) == today] + \
           [f"'{r['name']}' is over, conclude it" for r in finished_waiting()]


# ------------------------------------------------------------------ ideas

# What you can change (lever) and what you hope moves (outcome). For each lever
# the text of the change that raises ("up") or lowers ("down") it.
LEVERS: Dict[str, Dict[str, Optional[str]]] = {
    "hydration": {"up": "Drink more water through the day", "down": None},
    "meeting_hours": {"up": None, "down": "Cut back on meetings"},
    "caffeine": {"up": None, "down": "Cut back on caffeine (for example nothing after 2pm)"},
    "reading_min": {"up": "Read for a while every evening", "down": None},
    "social_quality": {"up": "Make time for people who lift you", "down": None},
    "sleep": {"up": "Go to bed earlier", "down": None},
}
OUTCOMES = ("mood", "energy", "stress", "sleep", "readiness")
IDEA_MIN_DAYS = 7
IDEA_MIN_R = 0.4


def _correlations() -> List[Dict[str, Any]]:
    import analytics
    import storage
    return analytics.compute_correlations(storage.get_recent_memory(days=ms.HISTORY_DAYS), min_days=IDEA_MIN_DAYS,
                                          min_abs_r=IDEA_MIN_R)


def ideas(limit: Any = None) -> List[Dict[str, Any]]:
    """Experiment ideas from your own correlations: {"name", "metric",
    "change", "lever", "r", "n_days"}. Only levers you can act on, only the
    direction that should help, and not for a metric that already has a
    running experiment."""
    cap = 3 if limit in (None, "") else limit
    if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= 10:
        raise ValueError("limit must be a whole number from 1 to 10.")
    busy = {r["metric"] for r in listing("running")}
    out: List[Dict[str, Any]] = []
    seen = set()
    for c in _correlations():
        for lever, outcome in ((c["metric_a"], c["metric_b"]), (c["metric_b"], c["metric_a"])):
            if lever not in LEVERS or outcome not in OUTCOMES or lever == outcome or outcome in busy:
                continue
            good_up = outcome not in ms.LOWER_IS_BETTER
            up = (c["r"] > 0) == good_up
            change = LEVERS[lever]["up" if up else "down"]
            if change is None or (lever, outcome) in seen:
                continue
            seen.add((lever, outcome))
            out.append({"name": f"{change.split(' (')[0]} and watch {outcome}", "metric": outcome, "change": change,
                        "lever": lever, "r": c["r"], "n_days": c["n_days"]})
    return out[:cap]


def format_ideas(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ("No clear pattern to test yet. Hermes needs a week or more of overlapping readings (for example sleep "
                "and mood) with a moderate or stronger link before it suggests an experiment.")
    lines = [f"{kit.plural(len(rows), 'experiment idea')} from your own data:"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['change']}, then watch {r['metric']}. Your {r['lever'].replace('_', ' ')} and "
                     f"{r['metric']} move together (r={r['r']}, {r['n_days']} days). A link is not proof of cause, "
                     f"which is why you test it.")
        lines.append(f"   Start it with start_experiment name='{r['name'][:60]}', metric='{r['metric']}', "
                     f"change='{r['change'][:70]}'.")
    return "\n".join(lines)


# ------------------------------------------------------------------ formatting

def _num(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.1f}"


def describe(res: Dict[str, Any], metric: str) -> List[str]:
    if res.get("state_metric"):
        return [f"{metric} is a live count, so there is no daily history to compare."]
    lines = [f"Before: {_num(res['mean_before'])} average over {kit.plural(res['n_before'], 'day')} with a reading.",
             f"During: {_num(res['mean_during'])} average over {kit.plural(res['n_during'], 'day')} with a reading."]
    v = res["verdict"]
    if v == "not enough data":
        lines.append(f"Not enough data yet: at least {MIN_READINGS} days with a {metric} reading are needed on each side.")
        return lines
    pct = f" ({res['percent']:+.0f}%)" if res.get("percent") is not None else ""
    lines.append(f"Change: {res['change']:+.1f}{pct}, effect size {res['effect']:+.2f}.")
    if v == "no clear effect":
        lines.append("Verdict: no clear effect. The two periods look about the same.")
    else:
        lines.append(f"Verdict: {v} ({res['strength']} effect, {metric} went {res['direction']}). "
                     f"Treat this as a hint, not proof: other things changed too.")
    return lines


def format_one(r: Dict[str, Any], daily: Optional[Dict[str, Dict[str, float]]] = None) -> str:
    end = end_day(r)
    head = f"{r['name']} [{r['metric']}] [id={r['id']}]"
    lines = [head]
    if r.get("change"):
        lines.append(f"Change: {r['change']}")
    if r["status"] == "done":
        lines.append(f"Concluded {r.get('concluded')}" + (f" - decision: {r['decision']}." if r.get("decision") else "."))
        lines += describe(r.get("result") or {"verdict": "not enough data", "n_before": 0, "n_during": 0,
                                              "mean_before": None, "mean_during": None}, r["metric"])
        return "\n".join(lines)
    today = clock.today_str()
    if r["start"] > today:
        lines.append(f"Starts {r['start']} ({kit.when_text((clock.parse_day(r['start']) - clock.today()).days)}), "
                     f"runs {kit.plural(r['days'], 'day')}.")
    else:
        done = min(r["days"], (clock.today() - clock.parse_day(r["start"])).days + 1)
        left = max(0, (clock.parse_day(end) - clock.today()).days)
        lines.append(f"Day {done} of {r['days']} (ends {end}" + (f", {kit.plural(left, 'day')} left" if left else "") + ").")
    lines += describe(analyze(r, daily), r["metric"])
    if end < today:
        lines.append("The experiment is over. Close it with conclude_experiment to keep the result.")
    return "\n".join(lines)


def format_all(status: Optional[str]) -> str:
    rows = listing(status)
    if not rows:
        return "No experiments yet. Try one with start_experiment, for example name='No caffeine after 2pm' on stress." \
            if not status else f"No {status} experiments."
    daily = ms.load_daily()
    blocks = []
    for r in rows:
        if r["status"] == "running":
            res = analyze(r, daily)
            blocks.append(f"- {r['name']} [{r['metric']}], {r['status']}: {res['verdict']} "
                          f"(ends {end_day(r)}) [id={r['id']}]")
        else:
            res = (r.get("result") or {}).get("verdict", "?")
            blocks.append(f"- {r['name']} [{r['metric']}], done {r.get('concluded')}: {res}"
                          + (f", {r['decision']}" if r.get("decision") else "") + f" [id={r['id']}]")
    return f"{kit.plural(len(rows), 'experiment')}:\n" + "\n".join(blocks)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    try:
        if name == "start_experiment":
            r = start_experiment(inp.get("name"), inp.get("metric"), inp.get("change"), inp.get("days"),
                                 inp.get("baseline_days"), inp.get("start"))
            return (f"Experiment started: {r['name']} on {r['metric']}, {kit.plural(r['days'], 'day')} from {r['start']} "
                    f"(compared with the {kit.plural(r['baseline_days'], 'day')} before). Keep logging {r['metric']}; "
                    f"check progress with get_experiment. [id={r['id']}]")
        if name == "suggest_experiment":
            return format_ideas(ideas(inp.get("limit")))
        if name == "get_experiments":
            status = inp.get("status")
            if status not in (None, "") and status not in STATUSES:
                raise ValueError(f"the status must be one of {', '.join(STATUSES)}.")
            return format_all(status or None)
        if name == "get_experiment":
            rows = [r for r in _load() if _valid(r)]
            return format_one(kit.resolve(rows, inp.get("experiment"), "experiment", "name", "get_experiments"))
        if name == "conclude_experiment":
            r = conclude_experiment(inp.get("experiment"), inp.get("decision"))
            return "Concluded.\n" + format_one(r)
        if name == "delete_experiment":
            return f"Deleted experiment '{delete_experiment(inp.get('experiment'))['name']}'."
    except (ValueError, TypeError) as e:
        verb = {"start_experiment": "Experiment not started", "get_experiments": "Cannot list experiments",
                "get_experiment": "Cannot show the experiment", "suggest_experiment": "No idea", "conclude_experiment": "Not concluded"}.get(
            name, "Experiment not deleted")
        return f"{verb}: {e}"
    return f"Unknown experiment tool: {name}"
