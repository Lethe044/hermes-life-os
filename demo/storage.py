"""
Hermes Life OS - Storage
=========================
All local persistence: profile, habits, goals, nutrition, sleep,
hydration, fitness, focus, mental logs, and the append-only long-term
memory journal (memory.jsonl).

Extracted from the original monolithic demo_life_os.py so storage
concerns are testable and reusable independent of the CLI / chat loop.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HERMES_DIR   = Path.home() / ".hermes" / "life-os"
MEMORY_FILE  = HERMES_DIR / "memory.jsonl"
PROFILE_FILE = HERMES_DIR / "profile.json"
HABITS_FILE  = HERMES_DIR / "habits.json"
GOALS_FILE   = HERMES_DIR / "goals.json"
NUTRITION_FILE = HERMES_DIR / "nutrition.json"
SLEEP_FILE   = HERMES_DIR / "sleep.json"
HYDRATION_FILE = HERMES_DIR / "hydration.json"
FITNESS_FILE = HERMES_DIR / "fitness.json"
FOCUS_FILE   = HERMES_DIR / "focus.json"
MENTAL_FILE  = HERMES_DIR / "mental.json"

HERMES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load(path: Path, default=None):
    if default is None:
        default = {}
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def _save(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_profile() -> Dict:    return _load(PROFILE_FILE, {"name": "friend", "onboarded": False})
def save_profile(p):           _save(PROFILE_FILE, p)
def load_habits() -> List:     return _load(HABITS_FILE, [])
def save_habits(h):            _save(HABITS_FILE, h)
def load_goals() -> List:      return _load(GOALS_FILE, [])
def save_goals(g):             _save(GOALS_FILE, g)
def load_nutrition() -> List:  return _load(NUTRITION_FILE, [])
def save_nutrition(n):         _save(NUTRITION_FILE, n)
def load_sleep() -> List:      return _load(SLEEP_FILE, [])
def save_sleep(s):             _save(SLEEP_FILE, s)
def load_hydration() -> Dict:  return _load(HYDRATION_FILE, {"today": 0, "goal": 8, "log": []})
def save_hydration(h):         _save(HYDRATION_FILE, h)
def load_fitness() -> List:    return _load(FITNESS_FILE, [])
def save_fitness(f):           _save(FITNESS_FILE, f)
def load_focus() -> List:      return _load(FOCUS_FILE, [])
def save_focus(f):             _save(FOCUS_FILE, f)
def load_mental() -> List:     return _load(MENTAL_FILE, [])
def save_mental(m):            _save(MENTAL_FILE, m)

def write_memory(entry: Dict):
    entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def search_memory(query: str, limit: int = 10) -> List[Dict]:
    if not MEMORY_FILE.exists():
        return []
    q = query.lower()
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if q in json.dumps(entry, ensure_ascii=False).lower():
                    results.append(entry)
            except Exception:
                pass
    return results[-limit:]

def get_recent_memory(days: int = 7) -> List[Dict]:
    if not MEMORY_FILE.exists():
        return []
    cutoff = datetime.utcnow() - timedelta(days=days)
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")
                if ts:
                    try:
                        if datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") >= cutoff:
                            results.append(entry)
                    except Exception:
                        results.append(entry)
            except Exception:
                pass
    return results

def memory_count() -> int:
    if not MEMORY_FILE.exists():
        return 0
    try:
        return sum(1 for _ in open(MEMORY_FILE, encoding="utf-8"))
    except Exception:
        return 0

