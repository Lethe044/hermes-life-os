#!/usr/bin/env python3
"""
Hermes Life OS - Doctor
=========================
A read-only health check of the active profile's data. Hermes' storage
layer is deliberately forgiving: a file it cannot read (wrong
LIFE_OS_ENCRYPTION_KEY, corruption) quietly loads as empty so the app
keeps running - which also means problems stay invisible until data is
overwritten. The doctor makes them visible. It never changes anything.

Checks:

  * every data store: readable, valid JSON, right shape, and consistent
    with the encryption key (encrypted file without a key, wrong key,
    plaintext file although a key is set)
  * the memory journal: how many lines cannot be read, duplicate entry ids
  * leftover .tmp files from an interrupted write
  * the clock: an invalid LIFE_OS_DAY_START_HOUR, and entries dated in the
    future (a wrong computer clock or a bad import)
  * entry ids: duplicate ids, and journal entries linked to a tracker row that
    no longer exists
  * the planner data (tasks, subscriptions, people, body readings, lists,
    savings goals, symptoms, notes, income, debts, countdowns, supplies, time blocks, objectives, recipes,
    the meal plan, trips): dates and values that cannot be read, shared ids (repair_hints.py names the entries and
    the fixing tool call)
  * backups: whether there are any, how old the newest is, whether it is
    readable and complete, whether older ones are unreadable
  * reminders: timed reminders whose time can never fire, ids that clash,
    past one-offs that can be cleared
  * budgets: non-numeric or negative limits, duplicate categories,
    out-of-range alert thresholds

Usage:
    hermes-life-os-doctor
    hermes-life-os-doctor --profile alex
    hermes-life-os-doctor --json
    hermes-life-os-doctor --strict

Exit status: 0 if there are no errors (warnings are fine), 1 if there is
at least one error - or, with --strict, at least one warning.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clock
import storage
import backup
import budgets
import reminders

OK, WARN, ERROR = "ok", "warn", "error"
STALE_BACKUP_DAYS = backup.STALE_BACKUP_DAYS  # one definition, shared with the stale-backup nudge
_FERNET_PREFIX = "gAAAA"  # every Fernet token starts with this


def _finding(level: str, area: str, message: str) -> Dict[str, str]:
    return {"level": level, "area": area, "message": message}


def _key_is_set() -> bool:
    return bool(os.environ.get("LIFE_OS_ENCRYPTION_KEY"))


def _crypto_usable() -> Tuple[bool, Optional[str]]:
    """Can the active key (if any) actually be used? Returns (usable,
    problem). With no key set this is trivially usable."""
    if not _key_is_set():
        return True, None
    try:
        storage.encrypt_text("probe")
    except Exception as e:  # noqa: BLE001 - e.g. the cryptography package is missing
        return False, str(e)
    return True, None


def check_encryption() -> List[Dict[str, str]]:
    usable, problem = _crypto_usable()
    if not usable:
        return [_finding(ERROR, "encryption",
                         f"LIFE_OS_ENCRYPTION_KEY is set but encryption cannot be used: {problem}")]
    if _key_is_set():
        return [_finding(OK, "encryption", "Encryption is on (LIFE_OS_ENCRYPTION_KEY is set).")]
    return [_finding(OK, "encryption", "Encryption is off (LIFE_OS_ENCRYPTION_KEY is not set).")]


def _classify_raw(raw: str):
    """Returns (data, state) where state is "ok", "plaintext_with_key",
    "encrypted_no_key", "wrong_key", or "corrupt"."""
    stripped = raw.strip()
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    else:
        return data, ("plaintext_with_key" if _key_is_set() else "ok")

    decrypted = storage.decrypt_text(raw)
    if decrypted != raw:
        try:
            return json.loads(decrypted), "ok"
        except ValueError:
            return None, "corrupt"
    if stripped.startswith(_FERNET_PREFIX):
        return None, ("wrong_key" if _key_is_set() else "encrypted_no_key")
    return None, "corrupt"


def check_stores() -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    present = 0
    problems = 0
    for name in storage.data_store_names():
        path = storage.data_store_path(name)
        if not path.exists():
            continue
        present += 1
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            problems += 1
            findings.append(_finding(ERROR, name, f"{path.name} cannot be read: {e}"))
            continue

        data, state = _classify_raw(raw)
        if state == "corrupt":
            problems += 1
            findings.append(_finding(
                ERROR, name,
                f"{path.name} is not valid data (corrupt or truncated). Restore it from a backup "
                f"with hermes-life-os-restore --latest --only {name}."))
        elif state == "encrypted_no_key":
            problems += 1
            findings.append(_finding(
                ERROR, name,
                f"{path.name} is encrypted but LIFE_OS_ENCRYPTION_KEY is not set, so Hermes reads it "
                f"as empty. Set the passphrase it was encrypted with."))
        elif state == "wrong_key":
            problems += 1
            findings.append(_finding(
                ERROR, name,
                f"{path.name} is encrypted but cannot be decrypted with the current "
                f"LIFE_OS_ENCRYPTION_KEY, so Hermes reads it as empty. Use the passphrase it was "
                f"encrypted with (saving now would overwrite it with empty data)."))
        else:
            expected = storage.DATA_STORES[name][3]
            if not isinstance(data, expected):
                problems += 1
                findings.append(_finding(
                    ERROR, name,
                    f"{path.name} should hold a JSON {'object' if expected is dict else 'list'} but "
                    f"holds a {type(data).__name__}."))
            elif state == "plaintext_with_key":
                findings.append(_finding(
                    WARN, name,
                    f"{path.name} is stored as plaintext although LIFE_OS_ENCRYPTION_KEY is set. "
                    f"It is encrypted the next time it is saved, or run hermes-life-os-rekey."))

    if present == 0:
        findings.append(_finding(OK, "stores", "No data files yet - nothing to check."))
    elif problems == 0 and not any(f["level"] == WARN for f in findings):
        findings.append(_finding(OK, "stores", f"All {present} data file(s) are readable and well-formed."))
    return findings


def check_memory() -> List[Dict[str, str]]:
    path = storage.MEMORY_FILE
    if not path.exists():
        return [_finding(OK, "memory", "No memory journal yet.")]
    try:
        f = storage._fernet()
    except Exception:  # noqa: BLE001 - already reported by check_encryption
        return []

    total = unreadable = 0
    ids: Dict[str, int] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                total += 1
                entry = storage._decode_memory_line(line, f)
                if not isinstance(entry, dict):
                    unreadable += 1
                    continue
                entry_id = entry.get("id")
                if entry_id:
                    ids[entry_id] = ids.get(entry_id, 0) + 1
    except (OSError, UnicodeDecodeError) as e:
        return [_finding(ERROR, "memory", f"{path.name} cannot be read: {e}")]

    findings: List[Dict[str, str]] = []
    if unreadable:
        findings.append(_finding(
            ERROR, "memory",
            f"{unreadable} of {total} line(s) in {path.name} cannot be read (corrupt, or encrypted "
            f"with a different key). Those entries are invisible to Hermes."))
    duplicates = sorted(i for i, n in ids.items() if n > 1)
    if duplicates:
        findings.append(_finding(
            WARN, "memory",
            f"{len(duplicates)} entry id(s) appear more than once (e.g. {duplicates[0]}); "
            f"correcting or deleting those entries by id will only touch the first."))
    if not findings:
        findings.append(_finding(OK, "memory", f"{total} memory entr{'y' if total == 1 else 'ies'}, all readable."))
    return findings


def check_leftovers() -> List[Dict[str, str]]:
    leftovers = sorted(storage.HERMES_DIR.glob("*.tmp")) if storage.HERMES_DIR.exists() else []
    if not leftovers:
        return [_finding(OK, "temp files", "No leftover temp files from interrupted writes.")]
    return [_finding(WARN, "temp files",
                     f"{p.name} was left behind by an interrupted write. If your data looks right "
                     f"it is safe to delete.") for p in leftovers]


def check_clock() -> List[Dict[str, str]]:
    """The day-start setting (LIFE_OS_DAY_START_HOUR): flags an invalid
    value, which is otherwise silently ignored."""
    problem = clock.day_start_problem()
    if problem:
        return [_finding(WARN, "clock", problem)]
    hour = clock.day_start_hour()
    if hour:
        return [_finding(OK, "clock", f"Your day starts at {hour:02d}:00 (LIFE_OS_DAY_START_HOUR), "
                                       f"so entries logged earlier count for the previous day.")]
    return [_finding(OK, "clock", "Days run midnight to midnight, local time.")]


# stores that hold a list of entries, each with a "date" (hydration keeps
# its entries under ["log"], handled separately)
_DATED_LIST_STORES = ["nutrition", "sleep", "fitness", "focus", "mental", "spending", "social",
                      "substance", "reading", "medication", "body", "symptoms", "income"]


def check_future_dates() -> List[Dict[str, str]]:
    """Entries dated more than a day after today. The writers use the same
    local clock as this check, so that only happens after a hand-edit, an
    import with bad dates, or a computer clock that was set wrong when the
    entry was logged - and it skews every "last N days" window."""
    limit = (clock.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    findings: List[Dict[str, str]] = []
    for name in _DATED_LIST_STORES + ["hydration"]:
        try:
            data = storage.load_store(name)
        except Exception:  # noqa: BLE001 - unreadable stores are reported by check_stores
            continue
        if name == "hydration":
            data = data.get("log", []) if isinstance(data, dict) else []
        if not isinstance(data, list):
            continue
        future = sorted(e["date"] for e in data
                        if isinstance(e, dict) and isinstance(e.get("date"), str) and e["date"] > limit)
        if future:
            findings.append(_finding(
                WARN, name,
                f"{len(future)} entr{'y' if len(future) == 1 else 'ies'} dated in the future "
                f"(latest {future[-1]}). That usually means the computer's clock was wrong when "
                f"they were logged, or an import used bad dates."))
    if not findings:
        findings.append(_finding(OK, "dates", "No entries are dated in the future."))
    return findings


# stores whose rows carry a persistent id (v1.39.0 / v1.40.0)
_ID_STORES = ["nutrition", "sleep", "fitness", "focus", "mental", "spending", "social",
              "substance", "reading", "medication", "hydration", "body", "symptoms", "income"]


def check_entry_ids() -> List[Dict[str, str]]:
    """Persistent entry ids: rows sharing an id (edit/delete by id would only
    reach the first one) and journal entries linked (expense_id / log_id) to a
    tracker row that no longer exists, which happens after a partial restore
    or when a data file is edited by hand."""
    findings: List[Dict[str, str]] = []
    all_ids = set()
    for name in _ID_STORES:
        try:
            data = storage.load_store(name)
        except Exception:  # noqa: BLE001 - unreadable stores are reported by check_stores
            continue
        if name == "hydration":  # its entries live under ["log"]
            data = data.get("log", []) if isinstance(data, dict) else []
        if not isinstance(data, list):
            continue
        ids = [e["id"] for e in data if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"]]
        all_ids.update(ids)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            findings.append(_finding(
                WARN, name,
                f"{len(dupes)} entry id(s) are shared by more than one entry ({', '.join(dupes[:3])}"
                f"{'...' if len(dupes) > 3 else ''}). Editing or deleting by id only reaches the first."))
    try:
        memory = storage.get_all_memory()
    except Exception:  # noqa: BLE001 - reported by check_memory
        memory = []
    orphans = [m for m in memory if isinstance(m, dict)
               and any(m.get(k) and m.get(k) not in all_ids for k in ("expense_id", "log_id"))]
    if orphans:
        findings.append(_finding(
            WARN, "journal",
            f"{len(orphans)} journal entr{'y' if len(orphans) == 1 else 'ies'} point to a logged entry "
            f"that no longer exists (a partial restore or a hand-edited data file). They still count "
            f"in the life score and other journal-based tools."))
    if not findings:
        findings.append(_finding(OK, "entry ids", "Entry ids are unique and every journal link has its entry."))
    return findings


def _valid_day(value: Any) -> bool:
    try:
        clock.parse_day(value)
        return True
    except ValueError:
        return False


def check_planner_data() -> List[Dict[str, Any]]:
    """The planner stores (tasks, subscriptions, people, body readings): entries
    that Hermes silently skips or never acts on - a task whose due date cannot
    be read never shows as overdue, a subscription without a readable renewal
    date never reminds you, a birthday that cannot be read never fires, a body
    reading with an unknown metric is left out of trends - and ids shared by
    two entries. Read-only: it never assigns the missing ids that the tools
    hand out on first use."""
    import timeblocks
    findings: List[Dict[str, str]] = []

    def rows(name: str) -> List[Dict[str, Any]]:
        try:
            data = storage.load_store(name)
        except Exception:  # noqa: BLE001 - unreadable stores are reported by check_stores
            return []
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []

    def warn(area: str, count: int, what: str) -> None:
        if count:
            findings.append(_finding(WARN, area, f"{count} {what}"))

    tasks = rows("tasks")
    warn("tasks", sum(1 for t in tasks if not t.get("done") and t.get("due") and not _valid_day(t.get("due"))),
         "open task(s) have a due date that cannot be read, so they never show as overdue.")
    subs = [s for s in rows("subscriptions") if s.get("active", True)]
    warn("subscriptions", sum(1 for s in subs if not _valid_day(s.get("next_date"))
                              or s.get("cycle") not in ("weekly", "monthly", "quarterly", "yearly")
                              or not isinstance(s.get("amount"), (int, float)) or s.get("amount", 0) <= 0),
         "active subscription(s) have no readable renewal date, cycle or amount, so they are left out of "
         "totals and renewal reminders.")
    warn("people", sum(1 for p in rows("people") if p.get("birthday") and not (
        _valid_day(p["birthday"]) if len(str(p["birthday"]).split("-")) == 3 else _valid_day(f"2024-{p['birthday']}"))),
         "birthday(s) cannot be read, so they never trigger a reminder.")
    from body import METRICS
    warn("body", sum(1 for r in rows("body") if r.get("type") != "goal" and (
        r.get("metric") not in METRICS or not isinstance(r.get("value"), (int, float))
        or not _valid_day(r.get("date")))), "body reading(s) have an unknown metric, a non-numeric value or "
                                            "no date, so they are left out of trends.")
    warn("savings", sum(1 for g in rows("savings") if not isinstance(g.get("target"), (int, float))
                        or g.get("target", 0) <= 0 or (g.get("deadline") and not _valid_day(g.get("deadline")))),
         "savings goal(s) have a target that is not a positive number or a deadline that cannot be read.")
    warn("symptoms", sum(1 for r in rows("symptoms") if not isinstance(r.get("symptom"), str)
                         or not isinstance(r.get("severity"), (int, float)) or not 1 <= r.get("severity", 0) <= 10
                         or not _valid_day(r.get("date"))),
         "symptom entries have no name, a severity outside 1-10 or no readable date, so they are left out of "
         "the summary.")
    warn("lists", sum(1 for r in rows("lists") if not isinstance(r.get("text"), str) or not r.get("text", "").strip()),
         "list item(s) have no text.")
    warn("notes", sum(1 for r in rows("notes") if not isinstance(r.get("text"), str) or not r.get("text", "").strip()),
         "note(s) have no text.")
    warn("income", sum(1 for r in rows("income") if not isinstance(r.get("amount"), (int, float))
                       or isinstance(r.get("amount"), bool) or r.get("amount", 0) <= 0
                       or not _valid_day(r.get("date"))),
         "income entries have an amount that is not a positive number or no readable date, so they are left "
         "out of cash flow.")
    warn("debts", sum(1 for d in rows("debts") if not isinstance(d.get("amount"), (int, float))
                      or d.get("amount", 0) <= 0 or d.get("direction") not in ("owe", "owed")
                      or (d.get("due") and not _valid_day(d.get("due")))),
         "debt(s) have an unusable amount, direction or due date.")
    warn("countdowns", sum(1 for c in rows("countdowns") if not _valid_day(c.get("date"))),
         "countdown(s) have a date that cannot be read.")
    warn("supplies", sum(1 for s in rows("supplies") if not _valid_day(s.get("as_of"))
                         or not isinstance(s.get("quantity"), (int, float)) or s.get("quantity", 0) < 0
                         or not isinstance(s.get("per_day"), (int, float)) or s.get("per_day", 0) < 0),
         "supply item(s) have a count, daily use or date that cannot be read.")
    warn("timeblocks", sum(1 for b in rows("timeblocks") if timeblocks.span(b) is None),
         "time block(s) have a date or time that cannot be read, or end before they start, so they are left "
         "out of the day plan.")
    warn("okrs", sum(1 for o in rows("okrs") if not _valid_day(o.get("start")) or not _valid_day(o.get("end"))
                     or any(not isinstance(k, dict) or not all(isinstance(k.get(f), (int, float)) and not isinstance(k.get(f), bool)
                                                              for f in ("start_value", "target", "current"))
                            or k.get("start_value") == k.get("target")
                            for k in (o.get("key_results") if isinstance(o.get("key_results"), list) else []))),
         "objective(s) have a period or key result numbers that cannot be used.")
    warn("recipes", sum(1 for r in rows("recipes") if not isinstance(r.get("ingredients"), list)
                        or not r.get("ingredients") or not isinstance(r.get("servings"), (int, float))
                        or isinstance(r.get("servings"), bool) or r.get("servings", 0) < 1),
         "recipe(s) have no ingredients or no usable number of servings.")
    warn("mealplan", sum(1 for m in rows("mealplan") if not _valid_day(m.get("date"))
                         or m.get("slot") not in ("breakfast", "lunch", "dinner", "snack")),
         "planned meal(s) have a date that cannot be read or an unknown slot.")
    warn("trips", sum(1 for t in rows("trips") if not _valid_day(t.get("start")) or not _valid_day(t.get("end"))
                      or str(t.get("end")) < str(t.get("start"))),
         "trip(s) have dates that cannot be read or end before they start.")
    import chores
    import routines
    warn("chores", sum(1 for c in rows("chores") if chores.due_date(c) is None),
         "chore(s) have an interval or date that cannot be read, so they never show as due.")
    warn("expiries", sum(1 for e in rows("expiries") if not _valid_day(e.get("date"))),
         "expiry date(s) cannot be read, so they never remind you.")
    warn("routines", sum(1 for r in rows("routines") if not routines.steps_of(r)
                         or (r.get("days") is not None and not (isinstance(r.get("days"), list) and all(
                             isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in r["days"])))),
         "routine(s) have no usable steps or a schedule that cannot be read.")
    warn("gifts", sum(1 for g in rows("gifts") if g.get("status") not in ("idea", "bought", "given")
                      or not isinstance(g.get("idea"), str) or not g["idea"].strip()
                      or not isinstance(g.get("person"), str) or not g["person"].strip()),
         "gift idea(s) have no person or idea text, or an unknown status.")
    warn("decisions", sum(1 for d in rows("decisions") if d.get("status") not in ("open", "reviewed")
                          or (d.get("status") != "reviewed" and not _valid_day(d.get("review")))
                          or not isinstance(d.get("title"), str) or not d["title"].strip()),
         "decision(s) have no title, an unknown status or a review date that cannot be read.")
    for name in ("tasks", "subscriptions", "people", "lists", "savings", "symptoms", "notes", "income", "debts",
                 "countdowns", "supplies", "timeblocks", "okrs", "recipes", "mealplan", "trips", "chores", "expiries",
                 "routines", "gifts", "decisions"):
        ids = [r["id"] for r in rows(name) if isinstance(r.get("id"), str) and r["id"]]
        dupes = len({i for i in ids if ids.count(i) > 1})
        warn(name, dupes, "id(s) are shared by more than one entry, so editing or deleting by id only reaches "
                          "the first.")
    if not findings:
        findings.append(_finding(OK, "planner", "Tasks, subscriptions, people, body readings, lists, savings, symptoms, notes, income, debts, countdowns, supplies, time blocks, objectives, recipes, the meal plan, trips, chores, expiry dates, routines, gift ideas and decisions are all readable. Run get_repair_suggestions when a warning needs follow-up."))
    return findings


def _has_any_data() -> bool:
    return storage.MEMORY_FILE.exists() or any(p.exists() for p in storage.data_store_paths())


def check_backups(now: Optional[datetime] = None) -> List[Dict[str, str]]:
    now = now or datetime.now()
    backups = backup.list_backups()
    if not backups:
        if not _has_any_data():
            return [_finding(OK, "backups", "No data yet, so nothing to back up.")]
        return [_finding(WARN, "backups",
                         "No backups yet. Run hermes-life-os-backup (or ask for backup_now); "
                         "the scheduler also takes one daily at 20:30 while it is running.")]

    findings: List[Dict[str, str]] = []
    infos = [backup.describe_backup(p) for p in backups]
    newest = infos[0]

    unreadable_older = [i["name"] for i in infos[1:] if not i["readable"]]
    if not newest["readable"]:
        findings.append(_finding(
            ERROR, "backups",
            f"The newest backup ({newest['name']}) cannot be read - it is corrupt, or encrypted with a "
            f"different passphrase than the current one. Take a fresh one with hermes-life-os-backup."))
    else:
        if newest["created"] is not None:
            age_days = (now - newest["created"]).days
            if age_days >= STALE_BACKUP_DAYS:
                findings.append(_finding(
                    WARN, "backups",
                    f"The newest backup is {age_days} day(s) old. Is the scheduler running?"))
        if newest["missing_stores"]:
            findings.append(_finding(
                WARN, "backups",
                f"The newest backup predates complete backups and lacks: "
                f"{', '.join(newest['missing_stores'])}. Take a fresh one."))
        if _key_is_set() and not newest["encrypted"]:
            findings.append(_finding(
                WARN, "backups",
                f"The newest backup ({newest['name']}) is not encrypted although encryption is on. "
                f"Take a fresh one, or run hermes-life-os-rekey to encrypt existing backups."))
    if unreadable_older:
        findings.append(_finding(
            WARN, "backups",
            f"{len(unreadable_older)} older backup(s) cannot be read: {', '.join(unreadable_older)}."))
    if not findings:
        findings.append(_finding(
            OK, "backups",
            f"{len(infos)} backup(s); the newest ({newest['name']}) is readable and complete."))
    return findings


def check_reminders(now: Optional[datetime] = None) -> List[Dict[str, str]]:
    rem = reminders
    now = now or datetime.now()
    items = storage.load_reminders()
    if not items:
        return [_finding(OK, "reminders", "No reminders set.")]

    findings: List[Dict[str, str]] = []
    seen: Dict[str, int] = {}
    for r in items:
        rid = str(r.get("id", ""))
        seen[rid] = seen.get(rid, 0) + 1
    clashes = sorted(i for i, n in seen.items() if n > 1)
    if clashes:
        findings.append(_finding(
            ERROR, "reminders",
            f"Reminder id(s) used more than once: {', '.join(clashes)}. Editing or deleting by id "
            f"will hit the wrong one - delete and recreate the duplicates."))

    for r in items:
        if not rem.is_enabled(r):
            continue
        time_hint = r.get("time")
        if time_hint and rem.normalize_time(time_hint) is None:
            findings.append(_finding(
                WARN, "reminders",
                f"Reminder '{r.get('text', '')}' [{r.get('id', '?')}] has time '{time_hint}', which is "
                f"not a clock time, so it will never fire. Use update_reminder with e.g. '09:00'."))

    today = now.strftime("%Y-%m-%d")
    past = [r for r in items if r.get("date") and r["date"] < today]
    if past:
        findings.append(_finding(
            WARN, "reminders",
            f"{len(past)} one-off reminder(s) are in the past and can never fire again "
            f"(clear_past_reminders removes them)."))

    if not findings:
        findings.append(_finding(OK, "reminders", f"{len(items)} reminder(s), all schedulable."))
    return findings


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_budgets() -> List[Dict[str, str]]:
    items = storage.load_budgets()
    if not items:
        return [_finding(OK, "budgets", "No budgets set.")]

    findings: List[Dict[str, str]] = []
    seen: Dict[str, int] = {}
    for b in items:
        category = str(b.get("category", ""))
        seen[category.lower()] = seen.get(category.lower(), 0) + 1
        limit = b.get("limit")
        if not _is_number(limit):
            findings.append(_finding(
                ERROR, "budgets",
                f"Budget '{category}' has a non-numeric limit ({limit!r}); it cannot be tracked. "
                f"Set it again with set_budget."))
        elif limit < 0:
            findings.append(_finding(WARN, "budgets", f"Budget '{category}' has a negative limit ({limit})."))
        alert = b.get("alert_pct")
        if alert is not None and not budgets.valid_alert_pct(alert):
            findings.append(_finding(
                WARN, "budgets",
                f"Budget '{category}' has an invalid alert_pct ({alert!r}); it is ignored and the "
                f"default of {budgets.DEFAULT_ALERT_PCT:g}% is used instead."))
    dupes = sorted(c for c, n in seen.items() if n > 1)
    if dupes:
        findings.append(_finding(
            WARN, "budgets",
            f"Duplicate budget categories (case-insensitive): {', '.join(dupes)}."))

    if not findings:
        findings.append(_finding(OK, "budgets", f"{len(items)} budget(s), all valid."))
    return findings


def run_checks(now: Optional[datetime] = None) -> List[Dict[str, str]]:
    """Runs every check against the active profile and returns the
    findings (each {"level": "ok"|"warn"|"error", "area", "message"}).
    Read-only. If the encryption key is set but unusable, only the checks
    that need no decryption run."""
    findings = check_encryption()
    usable, _ = _crypto_usable()
    if usable:
        findings += check_stores()
        findings += check_memory()
    findings += check_leftovers()
    findings += check_clock()
    if usable:
        findings += check_future_dates()
        findings += check_entry_ids()
        findings += check_planner_data()
        findings += check_backups(now)
        findings += check_reminders(now)
        findings += check_budgets()
    return findings


def summarize(findings: List[Dict[str, str]]) -> Dict[str, int]:
    return {
        "errors": sum(1 for f in findings if f["level"] == ERROR),
        "warnings": sum(1 for f in findings if f["level"] == WARN),
        "ok": sum(1 for f in findings if f["level"] == OK),
    }


_TAGS = {OK: "[OK]   ", WARN: "[WARN] ", ERROR: "[ERROR]"}


def format_report(findings: List[Dict[str, str]]) -> str:
    """Plain-text report: problems first (errors, then warnings), then the
    passing checks, then a one-line verdict."""
    order = {ERROR: 0, WARN: 1, OK: 2}
    ordered = sorted(findings, key=lambda f: order.get(f["level"], 3))
    lines = [f"Hermes Life OS health check - profile '{storage.ACTIVE_PROFILE}' ({storage.HERMES_DIR})"]
    for f in ordered:
        lines.append(f"{_TAGS[f['level']]} {f['area']}: {f['message']}")
    s = summarize(findings)
    if s["errors"]:
        verdict = f"{s['errors']} error(s) and {s['warnings']} warning(s) found - fix the errors first."
    elif s["warnings"]:
        verdict = f"No errors, {s['warnings']} warning(s)."
    else:
        verdict = "Everything looks healthy."
    lines.append(verdict)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only health check of your Hermes Life OS data.")
    parser.add_argument("--profile", default=None,
                        help="Profile to check. Can also be set via LIFE_OS_PROFILE.")
    parser.add_argument("--json", action="store_true", help="Print the findings as JSON.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures (exit status 1).")
    args = parser.parse_args(argv)

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))
    findings = run_checks()
    summary = summarize(findings)

    if args.json:
        print(json.dumps({"profile": storage.ACTIVE_PROFILE, "summary": summary, "findings": findings},
                         indent=2, ensure_ascii=False))
    else:
        print(format_report(findings))

    if summary["errors"] or (args.strict and summary["warnings"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
