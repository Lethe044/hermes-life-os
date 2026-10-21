"""
Hermes Life OS - Body Metrics
===============================
Weight, body fat, waist, hips, resting heart rate, blood pressure, blood
glucose, body temperature and SpO2: log a reading, see the trend, and
(for any of them) set a target and see how far away it is and, if the trend
points the right way, when it would be reached.

Until v1.42.0 Hermes tracked what you do (sleep, food, workouts) but not what
your body does in response. Readings are measurements, not behaviors, so they
are kept in their own store (body.json) instead of the memory journal's
mood/energy metrics - but every reading also writes a journal entry, so
"on this day", the day view and the entry tools (list/edit/delete/undo) see it.

Rows are {"id", "date", "metric", "value", "unit", "notes"} (+ "value2" for the
diastolic number of a blood pressure reading) and, for targets, {"id", "date",
"type": "goal", "metric", "target", "unit"}. Values are stored exactly as
typed, in the unit typed; analysis converts to one unit per metric and shows
the result in the unit of the most recent reading, so someone who logs
pounds sees pounds.

Readings outside a plausible range are refused (a weight of 700 kg is a typo,
not a reading). Nothing here is medical advice: the blood pressure category is
the usual public-health banding, shown for information only. No network call
is made by this module.
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import clock


def _storage():
    """The storage module as it is right now (looked up on every call, so a
    reloaded storage - another profile, a test's temp HOME - is never missed)."""
    import storage
    return storage


# metric -> {canonical unit, accepted units {unit: factor to canonical or fn}, plausible range in canonical}
METRICS: Dict[str, Dict[str, Any]] = {
    "weight":        {"unit": "kg", "units": {"kg": 1.0, "lb": 0.45359237, "lbs": 0.45359237, "st": 6.35029318},
                      "range": (20.0, 400.0), "stable": 0.1, "label": "Weight"},
    "body_fat":      {"unit": "%", "units": {"%": 1.0, "percent": 1.0}, "range": (2.0, 70.0),
                      "stable": 0.1, "label": "Body fat"},
    "waist":         {"unit": "cm", "units": {"cm": 1.0, "in": 2.54, "inch": 2.54, "inches": 2.54},
                      "range": (30.0, 250.0), "stable": 0.2, "label": "Waist"},
    "hips":          {"unit": "cm", "units": {"cm": 1.0, "in": 2.54, "inch": 2.54, "inches": 2.54},
                      "range": (40.0, 250.0), "stable": 0.2, "label": "Hips"},
    "resting_hr":    {"unit": "bpm", "units": {"bpm": 1.0}, "range": (25.0, 220.0), "stable": 0.5,
                      "label": "Resting heart rate"},
    "blood_pressure": {"unit": "mmHg", "units": {"mmhg": 1.0}, "range": (50.0, 280.0), "stable": 1.0,
                       "label": "Blood pressure"},
    "blood_glucose": {"unit": "mg/dL", "units": {"mg/dl": 1.0, "mmol/l": 18.0182},
                      "range": (20.0, 800.0), "stable": 2.0, "label": "Blood glucose"},
    "temperature":   {"unit": "C", "units": {"c": 1.0, "celsius": 1.0}, "range": (30.0, 45.0),
                      "stable": 0.05, "label": "Body temperature"},
    "spo2":          {"unit": "%", "units": {"%": 1.0, "percent": 1.0}, "range": (50.0, 100.0),
                      "stable": 0.2, "label": "Blood oxygen"},
}
_ALIASES = {"bodyweight": "weight", "body weight": "weight", "bodyfat": "body_fat", "body fat": "body_fat",
            "fat": "body_fat", "heart_rate": "resting_hr", "heart rate": "resting_hr", "hr": "resting_hr",
            "pulse": "resting_hr", "bp": "blood_pressure", "blood pressure": "blood_pressure",
            "glucose": "blood_glucose", "blood sugar": "blood_glucose", "sugar": "blood_glucose",
            "temp": "temperature", "oxygen": "spo2", "o2": "spo2"}
MAX_NOTES = 200
MAX_ROWS = 20000


def metric_names() -> List[str]:
    return list(METRICS)


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def parse_metric(value: Any) -> str:
    key = str(value or "").strip().lower().replace("-", "_")
    key = _ALIASES.get(key, key)
    if key not in METRICS:
        raise ValueError(f"unknown metric '{value}'. Choose one of: {', '.join(METRICS)}.")
    return key


def _unit_key(metric: str, unit: Any) -> str:
    if unit is None or (isinstance(unit, str) and not unit.strip()):
        return METRICS[metric]["unit"].lower()
    return str(unit).strip().lower()


def _display_unit(metric: str, unit: Any) -> str:
    """The unit as it is stored and shown (mg/dL, mmol/L, C, F, kg, lb...)."""
    key = _unit_key(metric, unit)
    canon = METRICS[metric]["unit"]
    if key == canon.lower():
        return canon
    return {"mmol/l": "mmol/L", "f": "F", "fahrenheit": "F", "celsius": "C", "lbs": "lb",
            "inches": "in", "inch": "in", "percent": "%"}.get(key, key)


def to_canonical(metric: str, value: float, unit: Any) -> float:
    """`value` in `unit` converted to the metric's canonical unit. Raises
    ValueError for an unknown unit. (Temperature also accepts F.)"""
    key = _unit_key(metric, unit)
    if metric == "temperature" and key in ("f", "fahrenheit"):
        return (value - 32.0) * 5.0 / 9.0
    factor = METRICS[metric]["units"].get(key)
    if factor is None:
        accepted = list(METRICS[metric]["units"]) + (["f"] if metric == "temperature" else [])
        raise ValueError(f"unit '{unit}' is not valid for {metric}. Use one of: {', '.join(accepted)}.")
    return value * factor


def from_canonical(metric: str, value: float, unit: Any) -> float:
    key = _unit_key(metric, unit)
    if metric == "temperature" and key in ("f", "fahrenheit"):
        return value * 9.0 / 5.0 + 32.0
    return value / METRICS[metric]["units"].get(key, 1.0)


def _number(label: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number, got {value!r}.") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number.")
    return number


def _check_range(metric: str, canonical: float, label: str = "value") -> None:
    lo, hi = METRICS[metric]["range"]
    if not lo <= canonical <= hi:
        raise ValueError(f"{label} looks wrong for {metric} (expected roughly {lo:g} to {hi:g} "
                         f"{METRICS[metric]['unit']}). Check the number and the unit.")


def _clean(number: float) -> Any:
    """Rounded to 4 places; a whole number stays an int, so 80 shows as 80 (not 80.0)."""
    rounded = round(number, 4)
    return int(rounded) if rounded == int(rounded) else rounded


# ------------------------------------------------------------------ storage

def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_body()
    if not isinstance(rows, list):
        return []
    seen = {r.get("id") for r in rows if isinstance(r, dict) and r.get("id")}
    changed = False
    for r in rows:
        if isinstance(r, dict) and not r.get("id"):
            new = new_id()
            while new in seen:
                new = new_id()
            seen.add(new)
            r["id"] = new
            changed = True
    if changed:
        _storage().save_body(rows)
    return rows


def readings(metric: Optional[str] = None) -> List[Dict[str, Any]]:
    """Readings (not targets), oldest first; optionally one metric only."""
    out = [r for r in _load() if isinstance(r, dict) and r.get("type") != "goal"
           and r.get("metric") in METRICS and isinstance(r.get("value"), (int, float))
           and isinstance(r.get("date"), str)]
    if metric:
        out = [r for r in out if r["metric"] == metric]
    out.sort(key=lambda r: r["date"])
    return out


def goals() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in _load():
        if isinstance(r, dict) and r.get("type") == "goal" and r.get("metric") in METRICS \
                and isinstance(r.get("target"), (int, float)):
            out[r["metric"]] = r
    return out


# ------------------------------------------------------------------ logging

def build_reading(metric: Any, value: Any, unit: Any = None, diastolic: Any = None,
                  date: Optional[str] = None, notes: Any = None,
                  row_id: Optional[str] = None) -> Dict[str, Any]:
    """Validates a reading and returns the row (not saved). Raises ValueError
    for an unknown metric/unit, a non-number, an implausible value, a blood
    pressure without a diastolic number (or diastolic above systolic), or a
    diastolic for any other metric."""
    m = parse_metric(metric)
    number = _number("value", value)
    _check_range(m, to_canonical(m, number, unit))
    row: Dict[str, Any] = {"id": row_id or new_id(), "date": date or clock.today_str(), "metric": m,
                           "value": _clean(number), "unit": _display_unit(m, unit)}
    if m == "blood_pressure":
        if diastolic is None:
            raise ValueError("a blood pressure reading needs both numbers: value is the systolic (top) "
                             "number and diastolic the bottom one, e.g. 120 over 80.")
        low = _number("diastolic", diastolic)
        _check_range(m, low, "diastolic")
        if low >= number:
            raise ValueError("the diastolic (bottom) number must be lower than the systolic (top) one.")
        row["value2"] = _clean(low)
    elif diastolic is not None:
        raise ValueError("diastolic only applies to blood pressure.")
    if isinstance(notes, str) and notes.strip():
        row["notes"] = notes.strip()[:MAX_NOTES]
    return row


def log_reading(metric: Any, value: Any, unit: Any = None, diastolic: Any = None,
                date: Optional[str] = None, notes: Any = None,
                row_id: Optional[str] = None) -> Dict[str, Any]:
    row = build_reading(metric, value, unit, diastolic, date, notes, row_id)
    rows = _load()
    if len(rows) >= MAX_ROWS:
        raise ValueError(f"body.json already holds {MAX_ROWS} rows - export and prune old readings first.")
    rows.append(row)
    _storage().save_body(rows)
    return row


def describe(row: Dict[str, Any]) -> str:
    m = row.get("metric", "?")
    if row.get("type") == "goal":
        return f"target {m} {row.get('target')} {row.get('unit', '')}".strip()
    label = METRICS.get(m, {}).get("label", m)
    if m == "blood_pressure":
        return f"{label} {row.get('value')}/{row.get('value2', '?')} mmHg"
    unit = row.get("unit", METRICS.get(m, {}).get("unit", ""))
    return f"{label} {row.get('value')} {unit}".strip()


def journal_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"content": describe(row), "metric": row.get("metric"), "value": row.get("value")}


# ------------------------------------------------------------------ analysis

def bp_category(systolic: float, diastolic: float) -> str:
    """The usual adult banding (informational only)."""
    if systolic >= 180 or diastolic >= 120:
        return "very high - seek medical advice"
    if systolic >= 140 or diastolic >= 90:
        return "high (stage 2 range)"
    if systolic >= 130 or diastolic >= 80:
        return "high (stage 1 range)"
    if systolic >= 120:
        return "elevated"
    return "normal range"


def trend(metric: Any, days: int = 30) -> Dict[str, Any]:
    """Statistics over the readings of the last `days` days (0 = today only):
    count, first/last/min/max/average, the change, a least-squares weekly rate
    (needs 2+ readings on different days) and a label. Values are in the unit
    of the most recent reading. Returns {"metric", "count": 0} with no data."""
    m = parse_metric(metric)
    cutoff = clock.days_ago_str(max(0, int(days)))
    rows = [r for r in readings(m) if r["date"] >= cutoff]
    if not rows:
        return {"metric": m, "count": 0, "days": days}
    unit = rows[-1].get("unit") or METRICS[m]["unit"]
    vals = [to_canonical(m, r["value"], r.get("unit")) for r in rows]
    conv = lambda v: from_canonical(m, v, unit)  # noqa: E731
    first, last = vals[0], vals[-1]
    out: Dict[str, Any] = {
        "metric": m, "count": len(rows), "days": days, "unit": unit,
        "first": conv(first), "last": conv(last), "min": conv(min(vals)), "max": conv(max(vals)),
        "average": conv(sum(vals) / len(vals)), "change": conv(last) - conv(first),
        "first_date": rows[0]["date"], "last_date": rows[-1]["date"],
    }
    if m == "blood_pressure":
        lows = [r.get("value2") for r in rows if isinstance(r.get("value2"), (int, float))]
        if lows:
            out["last_diastolic"] = lows[-1]
            out["avg_diastolic"] = sum(lows) / len(lows)
    # least-squares slope per day over calendar days
    xs = [(clock.parse_day(r["date"]) - clock.parse_day(rows[0]["date"])).days for r in rows]
    if len(set(xs)) >= 2:
        mx, my = sum(xs) / len(xs), sum(vals) / len(vals)
        denom = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (v - my) for x, v in zip(xs, vals)) / denom if denom else 0.0
        out["per_week"] = conv(slope * 7 + vals[0]) - conv(vals[0]) if unit else slope * 7
        out["slope_canonical_per_day"] = slope
        threshold = METRICS[m]["stable"]
        out["direction"] = ("stable" if abs(slope * 7) < threshold
                            else "rising" if slope > 0 else "falling")
    return out


def goal_progress(metric: str) -> Optional[Dict[str, Any]]:
    """Distance to the target of `metric` and an ETA from the last 30 days'
    trend; None when no target is set or there are no readings."""
    g = goals().get(metric)
    rows = readings(metric)
    if not g or not rows:
        return None
    unit = g.get("unit") or METRICS[metric]["unit"]
    last = to_canonical(metric, rows[-1]["value"], rows[-1].get("unit"))
    target = to_canonical(metric, g["target"], unit)
    remaining = target - last
    out = {"metric": metric, "target": g["target"], "unit": unit,
           "current": from_canonical(metric, last, unit), "remaining": from_canonical(metric, last + remaining, unit)
           - from_canonical(metric, last, unit), "reached": abs(remaining) < METRICS[metric]["stable"],
           "eta": None, "moving_toward": None}
    t = trend(metric, 30)
    slope = t.get("slope_canonical_per_day")
    if slope is not None and not out["reached"]:
        toward = (slope > 0) == (remaining > 0) and slope != 0
        out["moving_toward"] = toward
        if toward:
            days_needed = math.ceil(abs(remaining / slope))
            if days_needed <= 3650:
                out["eta"] = (clock.today() + timedelta(days=days_needed)).isoformat()
                out["eta_days"] = days_needed
    return out


def _fmt(v: float) -> str:
    return f"{v:.1f}"


def format_trend(t: Dict[str, Any]) -> str:
    m = t["metric"]
    label = METRICS[m]["label"]
    if not t["count"]:
        return f"No {m.replace('_', ' ')} readings in the last {t['days']} days."
    unit = t["unit"]
    if m == "blood_pressure":
        lines = [f"{label}, last {t['days']} days ({t['count']} reading(s)): latest {_fmt(t['last'])}/"
                 f"{_fmt(t.get('last_diastolic', 0))} mmHg, average {_fmt(t['average'])}/"
                 f"{_fmt(t.get('avg_diastolic', 0))}.",
                 f"Latest reading is in the {bp_category(t['last'], t.get('last_diastolic', 0))} (for information, "
                 f"not medical advice)."]
        return "\n".join(lines)
    lines = [f"{label}, last {t['days']} days ({t['count']} reading(s)): latest {_fmt(t['last'])} {unit}, "
             f"average {_fmt(t['average'])}, range {_fmt(t['min'])} to {_fmt(t['max'])}."]
    if t["count"] >= 2:
        sign = "+" if t["change"] >= 0 else ""
        lines.append(f"Change since {t['first_date']}: {sign}{_fmt(t['change'])} {unit}.")
    if "direction" in t:
        if t["direction"] == "stable":
            lines.append("Trend: stable.")
        else:
            sign = "+" if t["per_week"] >= 0 else ""
            lines.append(f"Trend: {t['direction']}, about {sign}{t['per_week']:.2f} {unit} per week.")
    else:
        lines.append("Log on more than one day to see a trend.")
    gp = goal_progress(m)
    if gp:
        if gp["reached"]:
            lines.append(f"Target {gp['target']:g} {gp['unit']}: reached.")
        else:
            line = f"Target {gp['target']:g} {gp['unit']}: {abs(gp['remaining']):.1f} {gp['unit']} to go"
            if gp["eta"]:
                line += f", at the current pace around {gp['eta']} (in {gp['eta_days']} days)."
            elif gp["moving_toward"] is False:
                line += ", but the trend is moving away from it."
            else:
                line += "."
            lines.append(line)
    return "\n".join(lines)


def overview() -> str:
    """Latest reading of every metric that has any, with its date."""
    lines = []
    for m in METRICS:
        rows = readings(m)
        if rows:
            r = rows[-1]
            lines.append(f"- {describe(r)} ({r['date']})")
    if not lines:
        return "No body measurements yet. Log one with log_body_metric (weight, body_fat, waist, hips, " \
               "resting_hr, blood_pressure, blood_glucose, temperature, spo2)."
    return "Latest body measurements:\n" + "\n".join(lines)


# ------------------------------------------------------------------ goals

def set_goal(metric: Any, target: Any, unit: Any = None) -> Dict[str, Any]:
    m = parse_metric(metric)
    if m == "blood_pressure":
        raise ValueError("targets are not supported for blood pressure (it has two numbers).")
    number = _number("target", target)
    _check_range(m, to_canonical(m, number, unit), "target")
    rows = _load()
    rows = [r for r in rows if not (isinstance(r, dict) and r.get("type") == "goal" and r.get("metric") == m)]
    goal = {"id": new_id(), "date": clock.today_str(), "type": "goal", "metric": m,
            "target": _clean(number), "unit": _display_unit(m, unit)}
    rows.append(goal)
    _storage().save_body(rows)
    return goal


def clear_goal(metric: Any) -> bool:
    m = parse_metric(metric)
    rows = _load()
    keep = [r for r in rows if not (isinstance(r, dict) and r.get("type") == "goal" and r.get("metric") == m)]
    if len(keep) == len(rows):
        return False
    _storage().save_body(keep)
    return True


# ------------------------------------------------------------------ tool entry point

def run_tool(name: str, inp: Dict[str, Any], log_date: Optional[str] = None,
             log_stamp: Optional[Dict[str, str]] = None, log_id: Optional[str] = None, **_ctx: Any) -> str:
    from storage import write_memory
    try:
        if name == "log_body_metric":
            row = log_reading(inp.get("metric"), inp.get("value"), inp.get("unit"), inp.get("diastolic"),
                              log_date, inp.get("notes"), log_id)
            write_memory({**(log_stamp or {}), "log_id": row["id"], "type": "body", **journal_fields(row)})
            msg = f"Logged: {describe(row)} on {row['date']} [id={row['id']}]"
            if row["metric"] == "blood_pressure":
                msg += f"\n{bp_category(row['value'], row['value2']).capitalize()} (information only, not medical advice)."
            else:
                t = trend(row["metric"], 30)
                if t["count"] >= 2 and "direction" in t:
                    msg += f"\n{t['count']} readings in 30 days, trend: {t['direction']}."
            return msg
        if name == "get_body_trend":
            if not inp.get("metric"):
                return overview()
            return format_trend(trend(inp.get("metric"), int(inp.get("days", 30))))
        if name == "set_body_goal":
            if inp.get("clear"):
                m = parse_metric(inp.get("metric"))
                return f"Target for {m} removed." if clear_goal(m) else f"No target was set for {m}."
            g = set_goal(inp.get("metric"), inp.get("target"), inp.get("unit"))
            gp = goal_progress(g["metric"])
            msg = f"Target set: {g['metric']} {g['target']:g} {g['unit']}."
            if gp and not gp["reached"]:
                msg += f" Currently {gp['current']:.1f} {gp['unit']}, {abs(gp['remaining']):.1f} to go."
            return msg
    except (ValueError, TypeError) as e:
        return {"log_body_metric": "Not logged", "get_body_trend": "Cannot show trend",
                "set_body_goal": "Target not changed"}.get(name, "Error") + f": {e}"
    return f"Unknown body tool: {name}"
