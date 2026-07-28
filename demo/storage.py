"""
Hermes Life OS - Storage
=========================
All local persistence: profile, habits, goals, nutrition, sleep,
hydration, fitness, focus, mental logs, and the append-only long-term
memory journal (memory.jsonl).

Extracted from the original monolithic demo_life_os.py so storage
concerns are testable and reusable independent of the CLI / chat loop.

Multi-profile support: by default everything lives at
~/.hermes/life-os/ exactly as before (zero change for existing
single-profile installs). Calling set_active_profile("alex") switches
every path below to ~/.hermes/life-os/profiles/alex/ instead, so
multiple people can share one machine/install without mixing data.
Internal functions (load_profile, write_memory, etc.) always read the
current module-level path globals, so switching profiles takes effect
immediately for every subsequent call - no need to re-import anything.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HERMES_ROOT = Path.home() / ".hermes" / "life-os"
ACTIVE_PROFILE = "default"

# The rest of these are (re)assigned by set_active_profile() below - the
# names exist here too just so static analysis / autocomplete sees them.
HERMES_DIR = HERMES_ROOT
MEMORY_FILE = HERMES_DIR / "memory.jsonl"
PROFILE_FILE = HERMES_DIR / "profile.json"
HABITS_FILE = HERMES_DIR / "habits.json"
GOALS_FILE = HERMES_DIR / "goals.json"
NUTRITION_FILE = HERMES_DIR / "nutrition.json"
SLEEP_FILE = HERMES_DIR / "sleep.json"
HYDRATION_FILE = HERMES_DIR / "hydration.json"
FITNESS_FILE = HERMES_DIR / "fitness.json"
FOCUS_FILE = HERMES_DIR / "focus.json"
MENTAL_FILE = HERMES_DIR / "mental.json"


def _profile_dir(profile: Optional[str]) -> Path:
    if not profile or profile == "default":
        return HERMES_ROOT
    return HERMES_ROOT / "profiles" / profile


def set_active_profile(profile: Optional[str] = None) -> Path:
    """
    Switch every storage path to the given profile. Passing None (or
    "default") points everything back at ~/.hermes/life-os directly -
    the original, backward-compatible layout. Any other name points at
    ~/.hermes/life-os/profiles/<name>/, fully isolated from "default"
    and from every other profile.

    Safe to call at any time (e.g. right after argparse, before any
    storage function is used) - every load_*/save_*/write_memory/etc.
    function below reads these same module globals at call time, so
    the switch takes effect immediately.
    """
    global ACTIVE_PROFILE, HERMES_DIR, MEMORY_FILE, PROFILE_FILE, HABITS_FILE
    global GOALS_FILE, NUTRITION_FILE, SLEEP_FILE, HYDRATION_FILE, FITNESS_FILE
    global FOCUS_FILE, MENTAL_FILE

    ACTIVE_PROFILE = profile or "default"
    HERMES_DIR = _profile_dir(ACTIVE_PROFILE)
    MEMORY_FILE = HERMES_DIR / "memory.jsonl"
    PROFILE_FILE = HERMES_DIR / "profile.json"
    HABITS_FILE = HERMES_DIR / "habits.json"
    GOALS_FILE = HERMES_DIR / "goals.json"
    NUTRITION_FILE = HERMES_DIR / "nutrition.json"
    SLEEP_FILE = HERMES_DIR / "sleep.json"
    HYDRATION_FILE = HERMES_DIR / "hydration.json"
    FITNESS_FILE = HERMES_DIR / "fitness.json"
    FOCUS_FILE = HERMES_DIR / "focus.json"
    MENTAL_FILE = HERMES_DIR / "mental.json"

    HERMES_DIR.mkdir(parents=True, exist_ok=True)
    return HERMES_DIR


def list_profiles() -> List[str]:
    """Names of every profile that has data on this machine. 'default'
    is included first if ~/.hermes/life-os has any top-level data of
    its own (i.e. someone used the tool before profiles existed, or
    is using it without --profile)."""
    names: List[str] = []
    if HERMES_ROOT.exists() and (
        (HERMES_ROOT / "memory.jsonl").exists()
        or any(HERMES_ROOT.glob("*.json"))
    ):
        names.append("default")

    profiles_dir = HERMES_ROOT / "profiles"
    if profiles_dir.exists():
        names.extend(sorted(p.name for p in profiles_dir.iterdir() if p.is_dir()))
    return names


# Initialize module-level paths exactly as they were before profiles
# existed, so every existing single-profile install is unaffected.
set_active_profile(None)

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
#
# Encryption is entirely opt-in via LIFE_OS_ENCRYPTION_KEY (a passphrase).
# When unset, every function below behaves exactly as it always has -
# plain JSON/JSONL, no dependency on the `cryptography` package at all.

def _fernet():
    """Returns a Fernet instance for the *current* profile if
    LIFE_OS_ENCRYPTION_KEY is set, else None. Re-derives every call
    (cheap - PBKDF2 is intentionally slow but this isn't a hot path)
    so switching profiles or the env var mid-process is always honored."""
    passphrase = os.environ.get("LIFE_OS_ENCRYPTION_KEY")
    if not passphrase:
        return None
    import crypto_store
    return crypto_store.get_fernet(passphrase, HERMES_DIR)


def _load(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8")
    f = _fernet()
    if f is not None:
        try:
            raw = f.decrypt(raw.encode("ascii")).decode("utf-8")
        except Exception:
            pass  # not a valid token - probably still plaintext from before encryption was enabled
    try:
        return json.loads(raw)
    except Exception:
        if f is not None:
            print(f"[hermes-life-os] Warning: couldn't read {path.name} - "
                  f"wrong LIFE_OS_ENCRYPTION_KEY? Using defaults for this session.",
                  file=sys.stderr)
        return default

def _save(path: Path, data):
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    f = _fernet()
    if f is not None:
        raw = f.encrypt(raw.encode("utf-8")).decode("ascii")
    path.write_text(raw, encoding="utf-8")

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

# --- memory.jsonl: each line is independently encrypted, so the file
# stays append-only and line-readable even under encryption. ---------

def _encode_memory_line(entry: Dict, f) -> str:
    line = json.dumps(entry, ensure_ascii=False)
    if f is not None:
        line = f.encrypt(line.encode("utf-8")).decode("ascii")
    return line

def _decode_memory_line(line: str, f) -> Optional[Dict]:
    line = line.strip()
    if not line:
        return None
    if f is not None:
        try:
            line = f.decrypt(line.encode("ascii")).decode("utf-8")
        except Exception:
            pass  # not a valid token - probably a plaintext line from before encryption was enabled
    try:
        return json.loads(line)
    except Exception:
        return None

def write_memory(entry: Dict):
    entry.setdefault("id", uuid.uuid4().hex[:8])
    # Only stamp "now" if the caller didn't already provide a timestamp -
    # every real-time logging call site (remember/log_meal/log_sleep/etc,
    # driven by LLM tool calls) never passes one, so this is identical to
    # before for all normal usage. This only changes behavior for bulk
    # imports (see health_import.py) that need to preserve real historical
    # dates instead of everything landing on "today".
    entry.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with open(MEMORY_FILE, "a", encoding="utf-8") as fh:
        fh.write(_encode_memory_line(entry, _fernet()) + "\n")

def _read_all_memory_entries() -> List[Dict]:
    """Every entry in memory.jsonl, decoded, in file order. Entries from
    before entry ids existed (or that fail to decode/decrypt) are
    skipped for edit/delete purposes - they can still be read via
    search_memory/get_recent_memory, just can't be targeted by id."""
    if not MEMORY_FILE.exists():
        return []
    f = _fernet()
    entries = []
    with open(MEMORY_FILE, encoding="utf-8") as fh:
        for line in fh:
            entry = _decode_memory_line(line, f)
            if entry is not None:
                entries.append(entry)
    return entries

def _rewrite_all_memory_entries(entries: List[Dict]) -> None:
    """Atomically replace memory.jsonl with exactly these entries,
    re-encrypted under the currently active key (if any). Writes to a
    temp file first and replaces in one step, so a crash mid-write
    can't corrupt or truncate existing data."""
    f = _fernet()
    tmp_path = MEMORY_FILE.with_suffix(MEMORY_FILE.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(_encode_memory_line(entry, f) + "\n")
    tmp_path.replace(MEMORY_FILE)

def edit_memory_entry(entry_id: str, updates: Dict) -> bool:
    """Merge `updates` into the entry with this id (id/timestamp are
    preserved unless explicitly included in updates). Returns True if
    an entry was found and updated, False otherwise."""
    entries = _read_all_memory_entries()
    found = False
    for entry in entries:
        if entry.get("id") == entry_id:
            entry.update(updates)
            found = True
            break
    if found:
        _rewrite_all_memory_entries(entries)
    return found

def delete_memory_entry(entry_id: str) -> bool:
    """Permanently remove the entry with this id. Returns True if an
    entry was found and removed, False otherwise."""
    entries = _read_all_memory_entries()
    remaining = [e for e in entries if e.get("id") != entry_id]
    if len(remaining) == len(entries):
        return False
    _rewrite_all_memory_entries(remaining)
    return True

def search_memory(query: str, limit: int = 10) -> List[Dict]:
    if not MEMORY_FILE.exists():
        return []
    q = query.lower()
    f = _fernet()
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as fh:
        for line in fh:
            entry = _decode_memory_line(line, f)
            if entry is not None and q in json.dumps(entry, ensure_ascii=False).lower():
                results.append(entry)
    return results[-limit:]

def get_recent_memory(days: int = 7) -> List[Dict]:
    if not MEMORY_FILE.exists():
        return []
    cutoff = datetime.utcnow() - timedelta(days=days)
    f = _fernet()
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as fh:
        for line in fh:
            entry = _decode_memory_line(line, f)
            if entry is None:
                continue
            ts = entry.get("timestamp", "")
            if ts:
                try:
                    if datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") >= cutoff:
                        results.append(entry)
                except Exception:
                    results.append(entry)
    return results

def get_memory_window(days_ago_start: int, days_ago_end: int = 0) -> List[Dict]:
    """
    Entries timestamped between `days_ago_start` and `days_ago_end` days
    before now (inclusive of the newer bound, exclusive-ish of the older
    one via >=/< below). `days_ago_start` must be the larger (older)
    number. E.g. get_memory_window(14, 7) is "the week before last week" -
    useful for week-over-week / month-over-month comparisons where
    get_recent_memory()'s single "last N days" isn't enough.
    """
    if not MEMORY_FILE.exists():
        return []
    now = datetime.utcnow()
    older_cutoff = now - timedelta(days=days_ago_start)
    newer_cutoff = now - timedelta(days=days_ago_end)
    f = _fernet()
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as fh:
        for line in fh:
            entry = _decode_memory_line(line, f)
            if entry is None:
                continue
            ts = entry.get("timestamp", "")
            if not ts:
                continue
            try:
                ts_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                continue
            if older_cutoff <= ts_dt < newer_cutoff:
                results.append(entry)
    return results

def get_memory_by_date_range(start_date: str, end_date: str) -> List[Dict]:
    """
    Entries with a date (YYYY-MM-DD, inclusive on both ends) between
    start_date and end_date. Unlike get_recent_memory()/get_memory_window()
    (both relative to "now"), this takes absolute calendar dates - meant
    for natural-language history queries like "how was I in March?",
    where the LLM resolves the vague phrase to concrete dates and calls
    this with them. Returns [] for invalid dates instead of raising, so
    a bad LLM-supplied date degrades to "no data" rather than a crash.
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)  # inclusive of end day
    except (ValueError, TypeError):
        return []
    if not MEMORY_FILE.exists():
        return []

    f = _fernet()
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as fh:
        for line in fh:
            entry = _decode_memory_line(line, f)
            if entry is None:
                continue
            ts = entry.get("timestamp", "")
            try:
                ts_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, TypeError):
                continue
            if start_dt <= ts_dt < end_dt:
                results.append(entry)
    return results

def memory_count() -> int:
    if not MEMORY_FILE.exists():
        return 0
    try:
        return sum(1 for _ in open(MEMORY_FILE, encoding="utf-8"))
    except Exception:
        return 0

def get_all_memory() -> List[Dict]:
    """Every memory entry ever logged, decoded, in file order. Useful for
    anomaly detection, before/after comparisons, and data export - places
    where 'the whole history' matters more than 'the last N days'."""
    return _read_all_memory_entries()

