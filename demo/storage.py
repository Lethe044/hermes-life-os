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
SPENDING_FILE = HERMES_DIR / "spending.json"
SOCIAL_FILE = HERMES_DIR / "social.json"
SUBSTANCE_FILE = HERMES_DIR / "substance.json"
ACHIEVEMENTS_FILE = HERMES_DIR / "achievements.json"
READING_FILE = HERMES_DIR / "reading.json"
MEDICATION_FILE = HERMES_DIR / "medication.json"
TEMPLATES_FILE = HERMES_DIR / "templates.json"
BUDGETS_FILE = HERMES_DIR / "budgets.json"
REMINDERS_FILE = HERMES_DIR / "reminders.json"
BODY_FILE = HERMES_DIR / "body.json"
TASKS_FILE = HERMES_DIR / "tasks.json"
SUBSCRIPTIONS_FILE = HERMES_DIR / "subscriptions.json"
PEOPLE_FILE = HERMES_DIR / "people.json"
LISTS_FILE = HERMES_DIR / "lists.json"
SAVINGS_FILE = HERMES_DIR / "savings.json"
SYMPTOMS_FILE = HERMES_DIR / "symptoms.json"
NOTES_FILE = HERMES_DIR / "notes.json"
INCOME_FILE = HERMES_DIR / "income.json"
DEBTS_FILE = HERMES_DIR / "debts.json"
COUNTDOWNS_FILE = HERMES_DIR / "countdowns.json"
SUPPLIES_FILE = HERMES_DIR / "supplies.json"
TIMEBLOCKS_FILE = HERMES_DIR / "timeblocks.json"
OKRS_FILE = HERMES_DIR / "okrs.json"
RECIPES_FILE = HERMES_DIR / "recipes.json"
MEALPLAN_FILE = HERMES_DIR / "mealplan.json"
TRIPS_FILE = HERMES_DIR / "trips.json"
CHORES_FILE = HERMES_DIR / "chores.json"
EXPIRIES_FILE = HERMES_DIR / "expiries.json"
ROUTINES_FILE = HERMES_DIR / "routines.json"
GIFTS_FILE = HERMES_DIR / "gifts.json"
DECISIONS_FILE = HERMES_DIR / "decisions.json"


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
    global FOCUS_FILE, MENTAL_FILE, SPENDING_FILE, SOCIAL_FILE, SUBSTANCE_FILE
    global ACHIEVEMENTS_FILE, READING_FILE, MEDICATION_FILE, TEMPLATES_FILE
    global BUDGETS_FILE, REMINDERS_FILE
    global BODY_FILE, TASKS_FILE, SUBSCRIPTIONS_FILE, PEOPLE_FILE
    global LISTS_FILE, SAVINGS_FILE, SYMPTOMS_FILE, NOTES_FILE
    global INCOME_FILE, DEBTS_FILE, COUNTDOWNS_FILE, SUPPLIES_FILE
    global TIMEBLOCKS_FILE, OKRS_FILE, RECIPES_FILE, MEALPLAN_FILE, TRIPS_FILE
    global CHORES_FILE, EXPIRIES_FILE, ROUTINES_FILE, GIFTS_FILE, DECISIONS_FILE

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
    SPENDING_FILE = HERMES_DIR / "spending.json"
    SOCIAL_FILE = HERMES_DIR / "social.json"
    SUBSTANCE_FILE = HERMES_DIR / "substance.json"
    ACHIEVEMENTS_FILE = HERMES_DIR / "achievements.json"
    READING_FILE = HERMES_DIR / "reading.json"
    MEDICATION_FILE = HERMES_DIR / "medication.json"
    TEMPLATES_FILE = HERMES_DIR / "templates.json"
    BUDGETS_FILE = HERMES_DIR / "budgets.json"
    REMINDERS_FILE = HERMES_DIR / "reminders.json"
    BODY_FILE = HERMES_DIR / "body.json"
    TASKS_FILE = HERMES_DIR / "tasks.json"
    SUBSCRIPTIONS_FILE = HERMES_DIR / "subscriptions.json"
    PEOPLE_FILE = HERMES_DIR / "people.json"
    LISTS_FILE = HERMES_DIR / "lists.json"
    SAVINGS_FILE = HERMES_DIR / "savings.json"
    SYMPTOMS_FILE = HERMES_DIR / "symptoms.json"
    NOTES_FILE = HERMES_DIR / "notes.json"
    INCOME_FILE = HERMES_DIR / "income.json"
    DEBTS_FILE = HERMES_DIR / "debts.json"
    COUNTDOWNS_FILE = HERMES_DIR / "countdowns.json"
    SUPPLIES_FILE = HERMES_DIR / "supplies.json"
    TIMEBLOCKS_FILE = HERMES_DIR / "timeblocks.json"
    OKRS_FILE = HERMES_DIR / "okrs.json"
    RECIPES_FILE = HERMES_DIR / "recipes.json"
    MEALPLAN_FILE = HERMES_DIR / "mealplan.json"
    TRIPS_FILE = HERMES_DIR / "trips.json"
    CHORES_FILE = HERMES_DIR / "chores.json"
    EXPIRIES_FILE = HERMES_DIR / "expiries.json"
    ROUTINES_FILE = HERMES_DIR / "routines.json"
    GIFTS_FILE = HERMES_DIR / "gifts.json"
    DECISIONS_FILE = HERMES_DIR / "decisions.json"

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

def encrypt_text(raw: str) -> str:
    """Encrypts `raw` under the active key (LIFE_OS_ENCRYPTION_KEY), or
    returns it unchanged when no key is set. Used for whole-file payloads
    such as backups."""
    f = _fernet()
    if f is None:
        return raw
    return f.encrypt(raw.encode("utf-8")).decode("ascii")

def decrypt_text(raw: str) -> str:
    """Inverse of encrypt_text. Tolerant like _load(): if there is no key,
    or `raw` is not a token this key can decrypt (e.g. it is still
    plaintext), `raw` is returned unchanged, so the caller's own parsing
    decides whether it is usable."""
    f = _fernet()
    if f is None:
        return raw
    try:
        return f.decrypt(raw.strip().encode("ascii")).decode("utf-8")
    except Exception:
        return raw

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
def load_spending() -> List:   return _load(SPENDING_FILE, [])
def save_spending(s):          _save(SPENDING_FILE, s)
def load_social() -> List:     return _load(SOCIAL_FILE, [])
def save_social(s):            _save(SOCIAL_FILE, s)
def load_substance() -> List:  return _load(SUBSTANCE_FILE, [])
def save_substance(s):         _save(SUBSTANCE_FILE, s)
def load_achievements() -> List: return _load(ACHIEVEMENTS_FILE, [])
def save_achievements(a):        _save(ACHIEVEMENTS_FILE, a)
def load_reading() -> List:      return _load(READING_FILE, [])
def save_reading(r):             _save(READING_FILE, r)
def load_medication() -> List:   return _load(MEDICATION_FILE, [])
def save_medication(m):          _save(MEDICATION_FILE, m)
def load_templates() -> Dict:    return _load(TEMPLATES_FILE, {})
def save_templates(t):           _save(TEMPLATES_FILE, t)
def load_budgets() -> List:      return _load(BUDGETS_FILE, [])
def save_budgets(b):             _save(BUDGETS_FILE, b)
def load_reminders() -> List:    return _load(REMINDERS_FILE, [])
def save_reminders(r):           _save(REMINDERS_FILE, r)
def load_body() -> List:         return _load(BODY_FILE, [])
def save_body(b):                _save(BODY_FILE, b)
def load_tasks() -> List:        return _load(TASKS_FILE, [])
def save_tasks(t):               _save(TASKS_FILE, t)
def load_subscriptions() -> List: return _load(SUBSCRIPTIONS_FILE, [])
def save_subscriptions(s):       _save(SUBSCRIPTIONS_FILE, s)
def load_people() -> List:       return _load(PEOPLE_FILE, [])
def save_people(p):              _save(PEOPLE_FILE, p)
def load_lists() -> List:        return _load(LISTS_FILE, [])
def save_lists(x):               _save(LISTS_FILE, x)
def load_savings() -> List:      return _load(SAVINGS_FILE, [])
def save_savings(x):             _save(SAVINGS_FILE, x)
def load_symptoms() -> List:     return _load(SYMPTOMS_FILE, [])
def save_symptoms(x):            _save(SYMPTOMS_FILE, x)
def load_notes() -> List:        return _load(NOTES_FILE, [])
def save_notes(x):               _save(NOTES_FILE, x)
def load_income() -> List:       return _load(INCOME_FILE, [])
def save_income(x):              _save(INCOME_FILE, x)
def load_debts() -> List:        return _load(DEBTS_FILE, [])
def save_debts(x):               _save(DEBTS_FILE, x)
def load_countdowns() -> List:   return _load(COUNTDOWNS_FILE, [])
def save_countdowns(x):          _save(COUNTDOWNS_FILE, x)
def load_supplies() -> List:     return _load(SUPPLIES_FILE, [])
def save_supplies(x):            _save(SUPPLIES_FILE, x)
def load_timeblocks() -> List:    return _load(TIMEBLOCKS_FILE, [])
def save_timeblocks(x):        _save(TIMEBLOCKS_FILE, x)
def load_okrs() -> List:          return _load(OKRS_FILE, [])
def save_okrs(x):              _save(OKRS_FILE, x)
def load_recipes() -> List:       return _load(RECIPES_FILE, [])
def save_recipes(x):           _save(RECIPES_FILE, x)
def load_mealplan() -> List:      return _load(MEALPLAN_FILE, [])
def save_mealplan(x):          _save(MEALPLAN_FILE, x)
def load_trips() -> List:         return _load(TRIPS_FILE, [])
def save_trips(x):             _save(TRIPS_FILE, x)
def load_chores() -> List:        return _load(CHORES_FILE, [])
def save_chores(x):            _save(CHORES_FILE, x)
def load_expiries() -> List:      return _load(EXPIRIES_FILE, [])
def save_expiries(x):          _save(EXPIRIES_FILE, x)
def load_routines() -> List:      return _load(ROUTINES_FILE, [])
def save_routines(x):          _save(ROUTINES_FILE, x)
def load_gifts() -> List:         return _load(GIFTS_FILE, [])
def save_gifts(x):             _save(GIFTS_FILE, x)
def load_decisions() -> List:     return _load(DECISIONS_FILE, [])
def save_decisions(x):         _save(DECISIONS_FILE, x)


# ---------------------------------------------------------------------------
# Data store registry
# ---------------------------------------------------------------------------
#
# The single list of every per-profile JSON data store (everything except
# the append-only memory.jsonl, which has its own line-by-line handling).
# Backup/export (data_export.py), restore (restore.py) and re-keying
# (rekey.py) all derive their file lists from this, so a new data type only
# has to be registered here once - before this existed each of those kept
# its own hand-written list and drifted out of sync (rekey silently skipped
# half the stores). tests/test_storage.py fails if a *_FILE path exists
# above that is not registered here.
#
# name -> (file attribute, loader function, saver function, expected type).
# Attribute/function names are strings resolved at call time, so switching
# profiles or reloading this module never leaves a stale reference.

DATA_STORES: Dict[str, tuple] = {
    "profile":      ("PROFILE_FILE",      "load_profile",      "save_profile",      dict),
    "habits":       ("HABITS_FILE",       "load_habits",       "save_habits",       list),
    "goals":        ("GOALS_FILE",        "load_goals",        "save_goals",        list),
    "nutrition":    ("NUTRITION_FILE",    "load_nutrition",    "save_nutrition",    list),
    "sleep":        ("SLEEP_FILE",        "load_sleep",        "save_sleep",        list),
    "hydration":    ("HYDRATION_FILE",    "load_hydration",    "save_hydration",    dict),
    "fitness":      ("FITNESS_FILE",      "load_fitness",      "save_fitness",      list),
    "focus":        ("FOCUS_FILE",        "load_focus",        "save_focus",        list),
    "mental":       ("MENTAL_FILE",       "load_mental",       "save_mental",       list),
    "spending":     ("SPENDING_FILE",     "load_spending",     "save_spending",     list),
    "social":       ("SOCIAL_FILE",       "load_social",       "save_social",       list),
    "substance":    ("SUBSTANCE_FILE",    "load_substance",    "save_substance",    list),
    "reading":      ("READING_FILE",      "load_reading",      "save_reading",      list),
    "medication":   ("MEDICATION_FILE",   "load_medication",   "save_medication",   list),
    "achievements": ("ACHIEVEMENTS_FILE", "load_achievements", "save_achievements", list),
    "templates":    ("TEMPLATES_FILE",    "load_templates",    "save_templates",    dict),
    "budgets":      ("BUDGETS_FILE",      "load_budgets",      "save_budgets",      list),
    "reminders":    ("REMINDERS_FILE",    "load_reminders",    "save_reminders",    list),
    "body":         ("BODY_FILE",         "load_body",         "save_body",         list),
    "tasks":        ("TASKS_FILE",        "load_tasks",        "save_tasks",        list),
    "subscriptions": ("SUBSCRIPTIONS_FILE", "load_subscriptions", "save_subscriptions", list),
    "people":       ("PEOPLE_FILE",       "load_people",       "save_people",       list),
    "lists":        ("LISTS_FILE",        "load_lists",        "save_lists",        list),
    "savings":      ("SAVINGS_FILE",      "load_savings",      "save_savings",      list),
    "symptoms":     ("SYMPTOMS_FILE",     "load_symptoms",     "save_symptoms",     list),
    "notes":        ("NOTES_FILE",        "load_notes",        "save_notes",        list),
    "income":       ("INCOME_FILE",       "load_income",       "save_income",       list),
    "debts":        ("DEBTS_FILE",        "load_debts",        "save_debts",        list),
    "countdowns":   ("COUNTDOWNS_FILE",   "load_countdowns",   "save_countdowns",   list),
    "supplies":     ("SUPPLIES_FILE",     "load_supplies",     "save_supplies",     list),
    "timeblocks":    ("TIMEBLOCKS_FILE",      "load_timeblocks",   "save_timeblocks",   list),
    "okrs":          ("OKRS_FILE",            "load_okrs",         "save_okrs",         list),
    "recipes":       ("RECIPES_FILE",         "load_recipes",      "save_recipes",      list),
    "mealplan":      ("MEALPLAN_FILE",        "load_mealplan",     "save_mealplan",     list),
    "trips":         ("TRIPS_FILE",           "load_trips",        "save_trips",        list),
    "chores":        ("CHORES_FILE",          "load_chores",       "save_chores",       list),
    "expiries":      ("EXPIRIES_FILE",        "load_expiries",     "save_expiries",     list),
    "routines":      ("ROUTINES_FILE",        "load_routines",     "save_routines",     list),
    "gifts":         ("GIFTS_FILE",           "load_gifts",        "save_gifts",        list),
    "decisions":     ("DECISIONS_FILE",       "load_decisions",    "save_decisions",    list),
}


def data_store_names() -> List[str]:
    """Names of every registered data store, in registry order."""
    return list(DATA_STORES)


def data_store_path(name: str) -> Path:
    """Current file path of a registered store (follows the active profile)."""
    return globals()[DATA_STORES[name][0]]


def data_store_paths() -> List[Path]:
    """Current file paths of every registered store."""
    return [data_store_path(n) for n in DATA_STORES]


def load_store(name: str):
    """Load a registered store by name."""
    return globals()[DATA_STORES[name][1]]()


def save_store(name: str, data) -> None:
    """Save a registered store by name (encrypted if a key is active)."""
    globals()[DATA_STORES[name][2]](data)


def replace_all_memory(entries: List[Dict]) -> int:
    """Atomically replace the whole memory journal with exactly these
    entries (re-encrypted under the active key, if any). Used by restore.
    Returns the number of entries written."""
    entries = list(entries)
    _rewrite_all_memory_entries(entries)
    return len(entries)

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

def find_memory_ids(field: str, value) -> List[str]:
    """Ids of the memory entries whose `field` equals `value` (used to keep a
    tracker row and its journal entry in sync)."""
    return [e["id"] for e in _read_all_memory_entries()
            if e.get("id") and e.get(field) == value]

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

