"""
Hermes Life OS - Estimate Accuracy
====================================
Compares the `minutes` estimate of finished tasks with the time you really
spent, taken from the focus sessions you logged with log_focus_session under
the same task name. Hermes tells you whether you tend to under- or
overestimate ("you take 1.4 times what you plan") and, once at least three
finished tasks have both an estimate and focus time, the workload forecast
scales its numbers by that factor. Read-only; it keeps no data of its own and
makes no network call.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import plannerkit as kit

MIN_TASKS = 3
FACTOR_RANGE = (0.5, 3.0)


def _norm(text: Any) -> str:
    return " ".join(str(text or "").lower().split())


def _sessions() -> List[Dict[str, Any]]:
    import storage
    return kit.only_dicts(storage.load_focus())


def accuracy() -> Dict[str, Any]:
    """{"tasks": [{"text", "estimate", "actual"}], "factor", "enough"} for
    finished tasks with an estimate and at least one focus session of the same
    task name."""
    import tasks
    actual: Dict[str, int] = {}
    for s in _sessions():
        mins = s.get("duration")
        if isinstance(mins, (int, float)) and not isinstance(mins, bool) and mins > 0 and s.get("task"):
            key = _norm(s["task"])
            actual[key] = actual.get(key, 0) + int(mins)
    rows: List[Dict[str, Any]] = []
    seen = set()
    for t in tasks._rows(tasks._load()):
        m = t.get("minutes")
        key = _norm(t.get("text"))
        if t.get("done") and isinstance(m, int) and not isinstance(m, bool) and m > 0 and key in actual and key not in seen:
            seen.add(key)
            rows.append({"text": t.get("text", "?"), "estimate": m, "actual": actual[key]})
    est = sum(r["estimate"] for r in rows)
    factor = (sum(r["actual"] for r in rows) / est) if est else None
    if factor is not None:
        factor = min(max(factor, FACTOR_RANGE[0]), FACTOR_RANGE[1])
    return {"tasks": rows, "factor": factor, "enough": len(rows) >= MIN_TASKS}


def calibration_factor() -> Optional[float]:
    """The factor to scale estimates by, or None without enough data."""
    try:
        got = accuracy()
    except Exception:  # noqa: BLE001
        return None
    return got["factor"] if got["enough"] else None


def _hm(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}" if h and m else f"{h}h" if h else f"{m}m"


def format_accuracy(a: Dict[str, Any]) -> str:
    if not a["tasks"]:
        return ("No finished task has both an estimate and logged focus time yet. Give a task minutes with add_task, "
                "log a focus session with the same task name using log_focus_session and finish the task.")
    f = a["factor"]
    lines = [f"Estimate accuracy over {kit.plural(len(a['tasks']), 'finished task')}:"]
    for r in sorted(a["tasks"], key=lambda r: _norm(r["text"]))[:10]:
        lines.append(f"- {r['text']}: planned {_hm(r['estimate'])}, took {_hm(r['actual'])}")
    word = "right on" if 0.9 <= f <= 1.1 else "underestimating" if f > 1.1 else "overestimating"
    lines.append(f"Overall you take {f:.2f}x your estimate ({word}).")
    if a["enough"]:
        lines.append("The workload forecast scales its numbers by this factor.")
    else:
        lines.append(f"Hermes needs {MIN_TASKS} such tasks before it uses this in the forecast.")
    return "\n".join(lines)


def run_tool(name: str, inp: Dict[str, Any], **_ctx: Any) -> str:
    if name != "get_estimate_accuracy":
        return f"Unknown estimate tool: {name}"
    try:
        return format_accuracy(accuracy())
    except (ValueError, TypeError) as e:
        return f"Cannot compare estimates: {e}"
