"""
Example Hermes Life OS plugin - screen time tracker.

A slightly more realistic example than dice.py: this one persists its
own data file and is profile-aware (each profile gets its own
screen-time log, exactly like the built-in trackers), by reusing
storage.HERMES_DIR - the same directory demo/storage.py writes to for
the active profile, which already flips automatically when someone
calls storage.set_active_profile(...).

Enable it the same way as any other plugin:

    mkdir -p ~/.hermes/life-os/plugins
    cp demo/plugins_examples/screen_time.py ~/.hermes/life-os/plugins/

Once installed, try: "I was on my phone for 3 hours today" or
"what's my screen time been like this week?"
"""

from __future__ import annotations

import json
import time
from pathlib import Path

PLUGIN_NAME = "screen_time"

TOOLS = [
    {"type": "function", "function": {
        "name": "log_screen_time",
        "description": "Log today's phone/computer screen time in hours.",
        "parameters": {"type": "object", "properties": {
            "hours": {"type": "number", "description": "Hours of screen time today."},
            "notes": {"type": "string"},
        }, "required": ["hours"]}}},
    {"type": "function", "function": {
        "name": "get_screen_time_summary",
        "description": "Get average screen time over the last N days (default 7).",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer"},
        }, "required": []}}},
]


def _data_file() -> Path:
    # Imported lazily (not at module import time) so this always reads
    # whichever profile is currently active, even if it was switched
    # after Hermes started.
    import storage
    return storage.HERMES_DIR / "plugin_screen_time.json"


def _load() -> list:
    path = _data_file()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list) -> None:
    path = _data_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def dispatch(name, inp):
    if name == "log_screen_time":
        hours = float(inp.get("hours", 0))
        entries = _load()
        entries.append({
            "date": time.strftime("%Y-%m-%d"),
            "hours": hours,
            "notes": inp.get("notes", ""),
        })
        _save(entries)
        return f"Logged {hours}h of screen time for today."

    if name == "get_screen_time_summary":
        days = int(inp.get("days") or 7)
        entries = _load()[-days:]
        if not entries:
            return "No screen time logged yet."
        avg = sum(e["hours"] for e in entries) / len(entries)
        return (f"Average screen time over last {len(entries)} day(s): "
                f"{avg:.1f}h/day (most recent: {entries[-1]['hours']}h)")

    return None
