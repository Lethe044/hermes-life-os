#!/usr/bin/env python3
"""
Hermes Life OS - Restore
==========================
Restores a JSON backup written by backup.py / data_export.py (--json /
export_data) into the active profile. Until v1.38.0 backups could be
written but there was no way to read one back in.

Safety rules, in order:

  1. The whole backup file is validated BEFORE anything is written: it
     must be a JSON object, every section must have the right shape (a
     list or an object), and any `--only` name must exist. One problem
     anywhere and nothing is touched.
  2. Sections that are NOT in the backup are left alone (an old, pre-
     v1.38.0 backup has no spending/reminders/... sections - restoring
     it must not wipe those). Sections that ARE in the backup replace
     the current data for that section.
  3. Before replacing anything, a safety copy of the current state is
     written to <data dir>/backups/pre-restore-<timestamp>.json. These
     files are never rotated away, so a mistaken restore can itself be
     undone by restoring the safety copy.
  4. The command line asks for confirmation (or --yes), and --dry-run
     shows exactly what would change without writing anything.

Data is written through the normal storage functions, so if
LIFE_OS_ENCRYPTION_KEY is set the restored files are encrypted with it.
Backups made while a key is set are themselves encrypted: set the same
LIFE_OS_ENCRYPTION_KEY (the passphrase they were made with) to restore
them.

Usage:
    hermes-life-os-restore --list
    hermes-life-os-restore --latest --dry-run
    hermes-life-os-restore --latest
    hermes-life-os-restore path/to/backup-2026-10-01-203000.json
    hermes-life-os-restore --latest --only spending,budgets --yes
    hermes-life-os-restore backup.json --profile alex
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
import backup
from data_export import export_json

MEMORY_SECTION = "memory"
META_SECTION = "_meta"


class RestoreError(RuntimeError):
    """The backup could not be read, or failed validation. Nothing was
    written."""


def known_sections() -> List[str]:
    """Every section a backup may contain and restore understands."""
    return storage.data_store_names() + [MEMORY_SECTION]


def load_backup_file(path) -> Dict[str, Any]:
    """Reads and parses a backup file, decrypting it with
    LIFE_OS_ENCRYPTION_KEY if it was written encrypted. Raises
    RestoreError if it is missing, not valid JSON (or encrypted with a
    different key), or not a JSON object."""
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise RestoreError(f"Backup file not found: {path}")
    payload, _ = backup._read_backup(path)
    if payload is not None:
        return payload

    # Not usable: tell the user why, as precisely as we can.
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RestoreError(
            f"Could not read {path.name}. It is not valid JSON - if it is an encrypted "
            f"backup, set LIFE_OS_ENCRYPTION_KEY to the passphrase it was made with."
        ) from None
    if not isinstance(parsed, dict):
        raise RestoreError(f"{path.name} is not a Hermes backup (expected a JSON object).")
    raise RestoreError(f"Could not read {path.name}.")


def validate_payload(payload: Dict[str, Any]) -> List[str]:
    """Returns a list of human-readable problems (empty if the payload is
    safe to restore). Unknown top-level keys are not problems - they are
    ignored and reported by plan_restore()."""
    problems: List[str] = []
    for name in storage.data_store_names():
        if name not in payload:
            continue
        expected = storage.DATA_STORES[name][3]
        if not isinstance(payload[name], expected):
            problems.append(
                f"'{name}' should be a JSON {'object' if expected is dict else 'list'}, "
                f"found {type(payload[name]).__name__}."
            )
    if MEMORY_SECTION in payload:
        memory = payload[MEMORY_SECTION]
        if not isinstance(memory, list):
            problems.append(f"'{MEMORY_SECTION}' should be a JSON list, found {type(memory).__name__}.")
        else:
            bad = sum(1 for e in memory if not isinstance(e, dict))
            if bad:
                problems.append(f"'{MEMORY_SECTION}' has {bad} entr{'y' if bad == 1 else 'ies'} that "
                                f"{'is' if bad == 1 else 'are'} not objects.")
    if not any(name in payload for name in known_sections()):
        problems.append("The file contains none of the sections a Hermes backup has "
                        "(is it really a backup?).")
    return problems


def parse_only(only: Optional[Any]) -> Optional[List[str]]:
    """Normalizes --only: accepts None, a comma-separated string or a
    list; returns a de-duplicated list of lower-cased names, or None for
    "everything". Raises RestoreError for an unknown name or an empty
    selection."""
    if only is None:
        return None
    if isinstance(only, str):
        only = only.split(",")
    names: List[str] = []
    for n in only:
        n = str(n).strip().lower()
        if n and n not in names:
            names.append(n)
    if not names:
        raise RestoreError("--only needs at least one section name.")
    unknown = [n for n in names if n not in known_sections()]
    if unknown:
        raise RestoreError(f"Unknown section(s): {', '.join(unknown)}. "
                           f"Valid sections: {', '.join(known_sections())}.")
    return names


def _current_count(name: str) -> int:
    if name == MEMORY_SECTION:
        return len(storage.get_all_memory())
    return len(storage.load_store(name))


def plan_restore(payload: Dict[str, Any], only: Optional[Any] = None) -> Dict[str, Any]:
    """What a restore would do, without doing it. Returns {"sections":
    [{"name", "current", "incoming"}] (sections that would be replaced),
    "skipped_not_in_backup": [...], "skipped_not_selected": [...],
    "ignored_keys": [...] (unknown top-level keys in the file)}.
    Raises RestoreError if the payload is invalid or `only` is bad."""
    problems = validate_payload(payload)
    if problems:
        raise RestoreError("Backup failed validation, nothing was changed:\n- " + "\n- ".join(problems))
    selected = parse_only(only)

    sections, not_in_backup, not_selected = [], [], []
    for name in known_sections():
        if selected is not None and name not in selected:
            not_selected.append(name)
        elif name not in payload:
            not_in_backup.append(name)
        else:
            sections.append({"name": name, "current": _current_count(name),
                             "incoming": len(payload[name])})
    if selected is not None:
        missing = [n for n in selected if n not in payload]
        if missing:
            raise RestoreError(f"The backup has no section(s): {', '.join(missing)}. Nothing was changed.")

    ignored = sorted(k for k in payload if k not in known_sections() and k != META_SECTION)
    return {"sections": sections, "skipped_not_in_backup": not_in_backup,
            "skipped_not_selected": not_selected, "ignored_keys": ignored}


def write_safety_backup(now: Optional[datetime] = None) -> Path:
    """Writes a copy of the CURRENT data to backups/pre-restore-<ts>.json
    (never matched by backup rotation, so it is kept until you delete it)
    and returns its path."""
    directory = backup.backups_dir()
    directory.mkdir(parents=True, exist_ok=True)
    ts = (now or datetime.now()).strftime("%Y-%m-%d-%H%M%S")
    path = directory / f"pre-restore-{ts}.json"
    n = 1
    while path.exists():
        path = directory / f"pre-restore-{ts}-{n}.json"
        n += 1
    export_json(str(path), encrypt=True)  # encrypted when a key is active, like backups
    return path


def restore_backup(path, only: Optional[Any] = None, dry_run: bool = False,
                   safety_backup: bool = True, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Restores `path` into the active profile. See the module docstring
    for the safety rules. Returns the plan (see plan_restore) plus
    {"dry_run": bool, "safety_backup": str | None, "restored": {name:
    count}}. Raises RestoreError, having written nothing, if the file is
    unreadable or invalid."""
    payload = load_backup_file(path)
    result = plan_restore(payload, only)
    result.update({"dry_run": dry_run, "safety_backup": None, "restored": {}})
    if dry_run:
        return result

    if safety_backup:
        result["safety_backup"] = str(write_safety_backup(now))

    for section in result["sections"]:
        name = section["name"]
        if name == MEMORY_SECTION:
            storage.replace_all_memory(payload[name])
        else:
            storage.save_store(name, payload[name])
        result["restored"][name] = section["incoming"]
    return result


def format_restore_result(result: Dict[str, Any]) -> str:
    """Plain-text report of restore_backup()'s result (also used for
    --dry-run)."""
    verb = "Would replace" if result["dry_run"] else "Replaced"
    lines = []
    if not result["sections"]:
        lines.append("Nothing to restore.")
    else:
        lines.append(f"{verb} {len(result['sections'])} section(s):")
        for s in result["sections"]:
            lines.append(f"  - {s['name']}: {s['current']} -> {s['incoming']} item(s)")
    if result["skipped_not_in_backup"]:
        lines.append("Left untouched (not in this backup): " + ", ".join(result["skipped_not_in_backup"]))
    if result["skipped_not_selected"]:
        lines.append("Left untouched (not selected): " + ", ".join(result["skipped_not_selected"]))
    if result["ignored_keys"]:
        lines.append("Ignored unknown keys in the file: " + ", ".join(result["ignored_keys"]))
    if result.get("safety_backup"):
        lines.append(f"Safety copy of your previous data: {result['safety_backup']}")
    if result["dry_run"]:
        lines.append("Dry run - nothing was changed.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Restore a Hermes Life OS JSON backup.")
    parser.add_argument("backup", nargs="?", help="Path to a backup .json file.")
    parser.add_argument("--latest", action="store_true", help="Use the newest backup of the profile.")
    parser.add_argument("--list", action="store_true", help="List the profile's backups and exit.")
    parser.add_argument("--only", default=None, metavar="A,B",
                        help="Restore only these sections (comma-separated), e.g. spending,budgets.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing.")
    parser.add_argument("--no-safety-backup", action="store_true",
                        help="Skip the pre-restore safety copy (not recommended).")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    parser.add_argument("--profile", default=None,
                        help="Profile to restore into. Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args(argv)

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    if args.list:
        backups = backup.list_backups()
        if not backups:
            print(f"No backups found in {backup.backups_dir()}.")
            return
        for p in backups:
            info = backup.describe_backup(p)
            status = "ok" if info["readable"] else "UNREADABLE"
            print(f"{p.name}  {round(info['size_bytes'] / 1024, 1)} KB  {status}")
        return

    if args.latest and args.backup:
        parser.error("Give either a backup path or --latest, not both.")
    if args.latest:
        path = backup.latest_backup()
        if path is None:
            print(f"No backups found in {backup.backups_dir()}.")
            sys.exit(1)
    elif args.backup:
        path = Path(args.backup)
    else:
        parser.error("Give a backup path, or use --latest (or --list to see what is available).")

    try:
        plan = restore_backup(path, only=args.only, dry_run=True)
    except RestoreError as e:
        print(f"Restore failed: {e}")
        sys.exit(1)

    print(f"Backup: {path}")
    print(f"Profile: {storage.ACTIVE_PROFILE}")
    print(format_restore_result(plan))
    if args.dry_run:
        return
    if not plan["sections"]:
        return

    if not args.yes:
        answer = input("Replace the sections above with the backup's data? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled - nothing was changed.")
            return

    try:
        result = restore_backup(path, only=args.only, safety_backup=not args.no_safety_backup)
    except RestoreError as e:
        print(f"Restore failed: {e}")
        sys.exit(1)
    print()
    print(format_restore_result(result))


if __name__ == "__main__":
    main()
