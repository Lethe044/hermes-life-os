"""
Hermes Life OS - Symptoms
===========================
A log of recurring complaints: headaches, back pain, migraines, heartburn,
anxiety attacks. Each entry has a severity (1-10), optionally a duration, the
suspected triggers ("stress", "coffee", "bad sleep") and notes. The summary
shows how often and how badly, how long since the last one, which triggers
come up most, whether it is getting more or less frequent and which weekday is
the worst. Where sleep was logged, it also compares the average sleep before
symptom days with the average before the other days.

Stored in symptoms.json as {"id", "date", "symptom", "severity", "duration_minutes",
"triggers", "time", "notes"} dicts. Entries are logged with log_symptom and
can be listed, edited, deleted and backdated like the other trackers. The trigger
report compares symptom days with other days using the sleep, stress, water,
caffeine, alcohol, nicotine and workout logs. This is
a personal log, not a diagnosis: nothing here is medical advice. No network
call is made by this module.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import clock

MAX_ROWS = 20000
MAX_NAME = 40
MAX_NOTES = 300
MAX_TRIGGERS = 8
MAX_TRIGGER_LEN = 30
MAX_DURATION = 7 * 24 * 60
_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _storage():
    import storage
    return storage


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def clean_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("say which symptom (for example headache).")
    name = " ".join(value.strip().lower().split())
    if len(name) > MAX_NAME:
        raise ValueError(f"the symptom name can be at most {MAX_NAME} characters.")
    return name


def clean_severity(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("severity must be a whole number from 1 to 10.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("severity must be a whole number from 1 to 10.") from None
    if number != int(number) or not 1 <= number <= 10:
        raise ValueError("severity must be a whole number from 1 to 10.")
    return int(number)


def clean_duration(value: Any) -> Optional[int]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("duration_minutes must be a whole number of minutes.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("duration_minutes must be a whole number of minutes.") from None
    if number != int(number) or not 1 <= number <= MAX_DURATION:
        raise ValueError(f"duration_minutes must be a whole number from 1 to {MAX_DURATION}.")
    return int(number)


def clean_triggers(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.replace(";", ",").split(",")
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise ValueError("triggers must be a list of short phrases.")
    out: List[str] = []
    for t in value:
        t = " ".join(t.strip().lower().split())
        if not t:
            continue
        if len(t) > MAX_TRIGGER_LEN:
            raise ValueError(f"a trigger can be at most {MAX_TRIGGER_LEN} characters.")
        if t not in out:
            out.append(t)
    if len(out) > MAX_TRIGGERS:
        raise ValueError(f"at most {MAX_TRIGGERS} triggers per entry.")
    return out


def clean_time(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError("time must be written as HH:MM.")
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts) or not (0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59):
        raise ValueError("time must be written as HH:MM, for example 14:30.")
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"


# ------------------------------------------------------------------ storage

def _load() -> List[Dict[str, Any]]:
    rows = _storage().load_symptoms()
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
        _storage().save_symptoms(rows)
    return rows


def entries(symptom: Optional[str] = None) -> List[Dict[str, Any]]:
    """Usable entries (known date and severity), oldest first."""
    out = [r for r in _load() if isinstance(r, dict) and isinstance(r.get("date"), str)
           and isinstance(r.get("severity"), (int, float)) and isinstance(r.get("symptom"), str)]
    if symptom:
        out = [r for r in out if r["symptom"] == symptom]
    out.sort(key=lambda r: (r["date"], str(r.get("time") or "")))
    return out


def build_entry(symptom: Any, severity: Any, date: Optional[str] = None, duration_minutes: Any = None,
                triggers: Any = None, notes: Any = None, time: Any = None,
                row_id: Optional[str] = None) -> Dict[str, Any]:
    row: Dict[str, Any] = {"id": row_id or new_id(), "date": date or clock.today_str(),
                           "symptom": clean_name(symptom), "severity": clean_severity(severity),
                           "duration_minutes": clean_duration(duration_minutes),
                           "triggers": clean_triggers(triggers), "time": clean_time(time)}
    if isinstance(notes, str) and notes.strip():
        row["notes"] = notes.strip()[:MAX_NOTES]
    return row


def log_symptom(symptom: Any, severity: Any, date: Optional[str] = None, duration_minutes: Any = None,
                triggers: Any = None, notes: Any = None, time: Any = None,
                row_id: Optional[str] = None) -> Dict[str, Any]:
    row = build_entry(symptom, severity, date, duration_minutes, triggers, notes, time, row_id)
    rows = _load()
    if len(rows) >= MAX_ROWS:
        raise ValueError(f"symptoms.json already holds {MAX_ROWS} entries - export and prune old ones first.")
    rows.append(row)
    _storage().save_symptoms(rows)
    return row


def describe(row: Dict[str, Any]) -> str:
    extra = f", {row['duration_minutes']} min" if row.get("duration_minutes") else ""
    trig = f" (triggers: {', '.join(row['triggers'])})" if row.get("triggers") else ""
    return f"{row.get('symptom', '?').capitalize()} {row.get('severity', '?')}/10{extra}{trig}"


def journal_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"content": describe(row), "symptom": row.get("symptom"), "severity": row.get("severity")}


# ------------------------------------------------------------------ analysis

def _sleep_by_day() -> Dict[str, float]:
    out: Dict[str, float] = {}
    try:
        rows = _storage().load_sleep()
    except Exception:  # noqa: BLE001
        return out
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and isinstance(r.get("date"), str) and isinstance(r.get("hours"), (int, float)):
            out[r["date"]] = float(r["hours"])
    return out


def summarize_symptom(symptom: str, days: int) -> Optional[Dict[str, Any]]:
    """Statistics for one symptom over the last `days` days (today included)."""
    today = clock.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    rows = [r for r in entries(symptom) if start <= r["date"] <= today.isoformat()]
    if not rows:
        return None
    sev = [r["severity"] for r in rows]
    day_set = {r["date"] for r in rows}
    last = entries(symptom)[-1]["date"]
    out: Dict[str, Any] = {
        "symptom": symptom, "count": len(rows), "days_affected": len(day_set),
        "avg_severity": round(sum(sev) / len(sev), 1), "max_severity": max(sev),
        "per_week": round(len(rows) / (days / 7), 1), "last": last,
        "days_since_last": (today - clock.parse_day(last)).days,
    }
    durations = [r["duration_minutes"] for r in rows if r.get("duration_minutes")]
    if durations:
        out["avg_duration"] = round(sum(durations) / len(durations))
    counted = Counter(t for r in rows for t in (r.get("triggers") or []))
    out["triggers"] = counted.most_common(3)
    if len(rows) >= 5:
        ranked = Counter(clock.parse_day(r["date"]).weekday() for r in rows).most_common(2)
        (top, n), runner_up = ranked[0], (ranked[1][1] if len(ranked) > 1 else 0)
        if n >= 2 and n > runner_up and n / len(rows) >= 0.3:
            out["worst_weekday"] = _WEEKDAYS[top]
    if days >= 14 and len(rows) >= 4:
        mid = (today - timedelta(days=days // 2 - 1)).isoformat()
        first = sum(1 for r in rows if r["date"] < mid)
        second = len(rows) - first
        if first:  # with nothing in the first half there is no baseline to compare with
            if second >= first * 1.5 and second - first >= 1:
                out["trend"] = "more frequent"
            elif first >= second * 1.5 and first - second >= 1:
                out["trend"] = "less frequent"
            else:
                out["trend"] = "about the same"
    sleep = _sleep_by_day()
    if sleep:
        before = []
        for d in day_set:
            prior = sleep.get(d)
            if prior is not None:
                before.append(prior)
        others = [h for d, h in sleep.items() if d not in day_set and start <= d <= today.isoformat()]
        if len(before) >= 3 and len(others) >= 3:
            out["sleep"] = {"on_symptom_days": round(sum(before) / len(before), 1),
                            "other_days": round(sum(others) / len(others), 1)}
    return out


def summary(days: Any = 30, symptom: Any = None) -> List[Dict[str, Any]]:
    try:
        n = int(days)
    except (TypeError, ValueError):
        raise ValueError("days must be a whole number.") from None
    if not 1 <= n <= 365:
        raise ValueError("days must be between 1 and 365.")
    if symptom:
        names = [clean_name(symptom)]
    else:
        names = sorted({r["symptom"] for r in entries()})
    out = [s for s in (summarize_symptom(name, n) for name in names) if s]
    out.sort(key=lambda s: (-s["count"], s["symptom"]))
    return out


def format_summary(stats: List[Dict[str, Any]], days: int, symptom: Optional[str] = None) -> str:
    if not stats:
        what = f"'{clean_name(symptom)}' " if symptom else ""
        return f"No {what}symptoms logged in the last {days} days."
    lines = [f"Symptoms in the last {days} days (a personal log, not medical advice):"]
    for s in stats:
        bits = [f"{s['count']} entr{'ies' if s['count'] != 1 else 'y'} on {s['days_affected']} day(s)",
                f"average severity {s['avg_severity']:g}/10 (worst {s['max_severity']})",
                f"{s['per_week']:g} per week"]
        if "avg_duration" in s:
            bits.append(f"about {s['avg_duration']} min each")
        lines.append(f"- {s['symptom'].capitalize()}: " + ", ".join(bits) + ".")
        since = "today" if s["days_since_last"] == 0 else f"{s['days_since_last']} day(s) ago"
        extra = [f"last one {since} ({s['last']})"]
        if s.get("trend"):
            extra.append(f"{s['trend']} than in the first half of the window")
        if s.get("worst_weekday"):
            extra.append(f"most often on {s['worst_weekday']}s")
        lines.append("    " + "; ".join(extra) + ".")
        if s["triggers"]:
            lines.append("    Common triggers: " + ", ".join(f"{t} ({n}x)" for t, n in s["triggers"]) + ".")
        if s.get("sleep"):
            sl = s["sleep"]
            lines.append(f"    Average logged sleep: {sl['on_symptom_days']:g}h on symptom days vs "
                         f"{sl['other_days']:g}h on other days (a pattern in your data, not a cause).")
    if any(s["max_severity"] >= 9 for s in stats):
        lines.append("A severity of 9-10 or anything new or getting worse is worth mentioning to a doctor.")
    return "\n".join(lines)

# ------------------------------------------------------------------ trigger report

MIN_SYMPTOM_DAYS = 4
MIN_OTHER_DAYS = 4
MIN_DAYS, MAX_DAYS, DEFAULT_DAYS = 14, 365, 90
_GROUPS = {
    "caffeine": ("caffeine", "coffee", "tea", "espresso", "energy drink", "cola"),
    "alcohol": ("alcohol", "beer", "wine", "vodka", "whiskey", "whisky", "rum", "gin", "spirits", "cocktail"),
    "nicotine": ("nicotine", "cigarette", "smoking", "vape", "tobacco"),
}
# numeric factor -> (label, minimum difference worth mentioning, unit)
_NUMERIC = {
    "sleep_hours": ("Sleep the night before", 0.5, "h"),
    "sleep_quality": ("Sleep quality the night before", 0.7, "/10"),
    "stress": ("Stress the day before", 0.7, "/10"),
    "water": ("Water the day before", 1.0, " glasses"),
}


def _num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _day_before(day: str) -> str:
    return (clock.parse_day(day) - timedelta(days=1)).isoformat()


def _list_rows(loader: str) -> List[Dict[str, Any]]:
    try:
        rows = getattr(_storage(), loader)()
    except Exception:  # noqa: BLE001 - one unreadable store must not break the report
        return []
    return [r for r in rows if isinstance(r, dict) and isinstance(r.get("date"), str)] if isinstance(rows, list) else []


def _factor_data() -> Dict[str, Any]:
    """Per-day values of every factor, from the other trackers."""
    sleep_h: Dict[str, float] = {}
    sleep_q: Dict[str, float] = {}
    for r in _list_rows("load_sleep"):
        if _num(r.get("hours")) is not None:
            sleep_h[r["date"]] = float(r["hours"])
        if _num(r.get("quality")) is not None:
            sleep_q[r["date"]] = float(r["quality"])
    stress: Dict[str, List[float]] = {}
    for r in _list_rows("load_mental"):
        if _num(r.get("score")) is not None and r.get("type") in (None, "stress"):
            stress.setdefault(r["date"], []).append(float(r["score"]))
    water: Dict[str, float] = {}
    try:
        hyd = _storage().load_hydration()
    except Exception:  # noqa: BLE001
        hyd = {}
    for r in hyd.get("log", []) if isinstance(hyd, dict) and isinstance(hyd.get("log"), list) else []:
        if isinstance(r, dict) and isinstance(r.get("date"), str) and _num(r.get("glasses")) is not None:
            water[r["date"]] = water.get(r["date"], 0.0) + float(r["glasses"])
    groups: Dict[str, set] = {g: set() for g in _GROUPS}
    subs = _list_rows("load_substance")
    for r in subs:
        name = str(r.get("substance", "")).lower()
        for g, words in _GROUPS.items():
            if any(w in name for w in words):
                groups[g].add(r["date"])
    workouts = {r["date"] for r in _list_rows("load_fitness")}
    logged = set(sleep_h) | set(sleep_q) | set(stress) | set(water) | workouts | {r["date"] for r in subs}
    logged |= {r["date"] for r in _list_rows("load_nutrition")}
    return {"sleep_hours": sleep_h, "sleep_quality": sleep_q,
            "stress": {d: sum(v) / len(v) for d, v in stress.items()}, "water": water,
            "groups": groups, "workouts": workouts, "logged": logged}


def _mean_sd(values: List[float]) -> Tuple[float, float]:
    m = sum(values) / len(values)
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1) if len(values) > 1 else 0.0
    return m, var ** 0.5


def trigger_report(symptom: Any = None, days: Any = DEFAULT_DAYS) -> Dict[str, Any]:
    """Compares the days a symptom happened with the other days over the last
    `days` days: numeric factors (sleep, stress, water) by their averages,
    habits (caffeine, alcohol, nicotine, a workout) by how often they came the
    day before, plus how often each trigger you named came up. Only differences
    that are large enough and backed by enough days are reported."""
    if isinstance(days, bool):
        raise ValueError(f"days must be a whole number from {MIN_DAYS} to {MAX_DAYS}.")
    try:
        n = int(days)
    except (TypeError, ValueError):
        raise ValueError(f"days must be a whole number from {MIN_DAYS} to {MAX_DAYS}.") from None
    if not MIN_DAYS <= n <= MAX_DAYS:
        raise ValueError(f"days must be between {MIN_DAYS} and {MAX_DAYS}.")
    today = clock.today()
    start = (today - timedelta(days=n - 1)).isoformat()
    window = [r for r in entries() if start <= r["date"] <= today.isoformat()]
    if symptom:
        name = clean_name(symptom)
    elif window:
        name = Counter(r["symptom"] for r in window).most_common(1)[0][0]
    else:
        return {"symptom": None, "days": n, "enough": False, "symptom_days": 0, "other_days": 0,
                "findings": [], "self_reported": []}
    rows = [r for r in window if r["symptom"] == name]
    sdays = {r["date"] for r in rows}
    all_days = {(today - timedelta(days=i)).isoformat() for i in range(n)}
    odays = all_days - sdays
    out: Dict[str, Any] = {"symptom": name, "days": n, "symptom_days": len(sdays), "other_days": len(odays),
                           "enough": len(sdays) >= MIN_SYMPTOM_DAYS, "findings": [], "self_reported": []}
    counted = Counter(t for r in rows for t in (r.get("triggers") or []) if isinstance(t, str))
    out["self_reported"] = [(t, c) for t, c in counted.most_common(5)]
    out["entries"] = len(rows)
    if not out["enough"]:
        return out
    data = _factor_data()
    findings: List[Dict[str, Any]] = []
    for key, (label, min_diff, unit) in _NUMERIC.items():
        source = data[key]
        shift = key in ("stress", "water")           # these look at the day BEFORE
        def val(d: str, source=source, shift=shift):
            return source.get(_day_before(d) if shift else d)
        a = [v for v in (val(d) for d in sdays) if v is not None]
        b = [v for v in (val(d) for d in odays) if v is not None]
        if len(a) < MIN_SYMPTOM_DAYS or len(b) < MIN_OTHER_DAYS:
            continue
        ma, sa = _mean_sd(a)
        mb, sb = _mean_sd(b)
        diff = ma - mb
        if abs(diff) < min_diff:
            continue
        pooled = (((len(a) - 1) * sa ** 2 + (len(b) - 1) * sb ** 2) / max(1, len(a) + len(b) - 2)) ** 0.5
        effect = abs(diff) / max(pooled, min_diff / 2)
        if effect < 0.5:
            continue
        findings.append({"factor": key, "kind": "numeric", "effect": round(effect, 2),
                         "text": f"{label}: {ma:.1f}{unit} on {name} days vs {mb:.1f}{unit} on other days "
                                 f"({len(a)} vs {len(b)} days with data)."})
    logged = data["logged"]
    base_other = odays & logged
    presence = [(g, f"{g.capitalize()} the day before", data["groups"][g]) for g in _GROUPS]
    presence.append(("workout", "A workout the day before", data["workouts"]))
    for key, label, days_with in presence:
        if not days_with or len(base_other) < MIN_OTHER_DAYS:
            continue
        hit_s = sum(1 for d in sdays if _day_before(d) in days_with)
        hit_o = sum(1 for d in base_other if _day_before(d) in days_with)
        share_s, share_o = hit_s / len(sdays), hit_o / len(base_other)
        if abs(share_s - share_o) < 0.25:
            continue
        findings.append({"factor": key, "kind": "presence", "effect": round(abs(share_s - share_o) * 4, 2),
                         "text": f"{label}: before {hit_s} of {len(sdays)} {name} days ({share_s:.0%}) vs "
                                 f"{hit_o} of {len(base_other)} other logged days ({share_o:.0%})."})
    findings.sort(key=lambda f: (-f["effect"], f["factor"]))
    out["findings"] = findings[:5]
    return out


def format_trigger_report(rep: Dict[str, Any]) -> str:
    if rep["symptom"] is None:
        return f"No symptoms logged in the last {rep['days']} days, so there is nothing to compare."
    name = rep["symptom"]
    if not rep["enough"]:
        return (f"Only {rep['symptom_days']} day(s) with {name} in the last {rep['days']} days - at least "
                f"{MIN_SYMPTOM_DAYS} are needed to compare them with the other days.")
    lines = [f"What differs on {name} days (last {rep['days']} days: {rep['symptom_days']} {name} days, "
             f"{rep['other_days']} other days):"]
    if rep["findings"]:
        lines += [f"- {f['text']}" for f in rep["findings"]]
    else:
        lines.append("- No clear difference in sleep, stress, water, caffeine, alcohol, nicotine or workouts "
                     "(or too little logged to tell).")
    if rep["self_reported"]:
        lines.append("Triggers you named: " + ", ".join(f"{t} ({c}x)" for t, c in rep["self_reported"]) + ".")
    lines.append("These are patterns in your own data, not causes, and not medical advice.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], log_date: Optional[str] = None,
             log_stamp: Optional[Dict[str, str]] = None, log_id: Optional[str] = None, **_ctx: Any) -> str:
    from storage import write_memory
    try:
        if name == "log_symptom":
            row = log_symptom(inp.get("symptom"), inp.get("severity"), log_date, inp.get("duration_minutes"),
                              inp.get("triggers"), inp.get("notes"), inp.get("time"), log_id)
            write_memory({**(log_stamp or {}), "log_id": row["id"], "type": "symptom", **journal_fields(row)})
            msg = f"Logged: {describe(row)} on {row['date']} [id={row['id']}]"
            s = summarize_symptom(row["symptom"], 30)
            if s and s["count"] >= 2:
                msg += f"\n{s['count']} {row['symptom']} entries in the last 30 days, average severity {s['avg_severity']:g}/10."
            return msg
        if name == "get_symptom_summary":
            days = int(inp.get("days", 30))
            return format_summary(summary(days, inp.get("symptom")), days, inp.get("symptom"))
        if name == "get_symptom_triggers":
            return format_trigger_report(trigger_report(inp.get("symptom"), inp.get("days", DEFAULT_DAYS)))
    except (ValueError, TypeError) as e:
        return {"log_symptom": "Not logged", "get_symptom_summary": "Cannot summarize symptoms",
                                                                      "get_symptom_triggers": "Cannot compare symptom days"}.get(name, "Error") + f": {e}"
    return f"Unknown symptom tool: {name}"
