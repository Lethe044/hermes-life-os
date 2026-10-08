"""
Hermes Life OS - Automatic Backups
=====================================
Timestamped, self-rotating JSON backups of the active profile's data,
built on top of data_export.export_json().

Each call writes a file named backup-YYYY-MM-DD-HHMMSS.json into
<profile data dir>/backups/ (so backups follow whichever profile is
currently active - set_active_profile() switches this like every
other storage path), then deletes the oldest backups beyond --keep
(default 7), keeping the most recent N.

Backups cover every registered data store plus the memory journal (see
storage.DATA_STORES). To restore one, use restore.py (hermes-life-os-restore).

Usage:
    python demo/backup.py
    python demo/backup.py --keep 14
    python demo/backup.py --profile alex --keep 3

Also wired into the scheduler (20:30 daily, after the 20:00 nudge
check) via run_scheduler.py, where it runs silently on success and
only produces notifier output on failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
from data_export import export_json

BACKUP_FILENAME_RE = re.compile(r"^backup-\d{4}-\d{2}-\d{2}-\d{6}\.json$")


def backups_dir() -> Path:
    """Directory backups for the *currently active* profile live in."""
    return storage.HERMES_DIR / "backups"


def _list_backups(directory: Path) -> List[Path]:
    """All backup files in directory, oldest first, by filename (which
    sorts chronologically since the timestamp format is fixed-width)."""
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if BACKUP_FILENAME_RE.match(p.name))


def rotate_backups(directory: Path, keep: int) -> List[Path]:
    """Delete the oldest backups in directory until at most `keep`
    remain. Returns the list of paths that were deleted."""
    if keep < 0:
        raise ValueError("keep must be >= 0")
    existing = _list_backups(directory)
    excess = len(existing) - keep
    if excess <= 0:
        return []
    to_delete = existing[:excess]
    for path in to_delete:
        path.unlink()
    return to_delete


def run_backup(keep: int = 7, now: datetime | None = None) -> Path:
    """Write a fresh timestamped backup for the active profile, rotate
    old ones out per `keep`, and return the path of the new backup."""
    # Never rotate away the backup we are about to write: keep=0 (or a bad
    # value passed by the agent through the backup_now tool) would delete
    # every backup, including this one.
    keep = max(1, keep)
    directory = backups_dir()
    directory.mkdir(parents=True, exist_ok=True)

    ts = (now or datetime.now()).strftime("%Y-%m-%d-%H%M%S")
    out_path = directory / f"backup-{ts}.json"
    export_json(str(out_path), encrypt=True)

    rotate_backups(directory, keep)
    return out_path


def _created_from_name(name: str) -> Optional[datetime]:
    try:
        return datetime.strptime(name[len("backup-"):-len(".json")], "%Y-%m-%d-%H%M%S")
    except ValueError:
        return None


def read_backup_payload(path: Path) -> Optional[Dict[str, Any]]:
    """Parses a backup file into a dict, transparently decrypting it with
    the active LIFE_OS_ENCRYPTION_KEY when it is encrypted. Returns None
    if the file is unreadable, corrupt, not a JSON object, or encrypted
    with a key that is not the active one. The second element is True when
    the file was encrypted."""
    payload, _ = _read_backup(path)
    return payload


def _read_backup(path: Path):
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None, False
    encrypted = False
    try:
        payload = json.loads(raw)
    except ValueError:
        decrypted = storage.decrypt_text(raw)
        if decrypted == raw:
            return None, False
        try:
            payload = json.loads(decrypted)
        except ValueError:
            return None, False
        encrypted = True
    if not isinstance(payload, dict):
        return None, encrypted
    return payload, encrypted


def describe_backup(path: Path) -> Dict[str, Any]:
    """Summary of one backup file: {"name", "path", "size_bytes",
    "created" (datetime parsed from the filename), "format_version",
    "stores" (name -> item count, memory included), "missing_stores"
    (registered stores this backup does not contain, e.g. a pre-v1.38.0
    backup), "readable", "encrypted"}. An unreadable or corrupt file - or
    an encrypted one whose key is not the active key - is reported with
    readable=False rather than raising."""
    path = Path(path)
    info: Dict[str, Any] = {
        "name": path.name, "path": str(path),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "created": _created_from_name(path.name),
        "format_version": None, "stores": {}, "missing_stores": [],
        "readable": False, "encrypted": False,
    }
    payload, encrypted = _read_backup(path)
    info["encrypted"] = encrypted
    if payload is None:
        return info
    info["readable"] = True
    meta = payload.get("_meta")
    info["format_version"] = meta.get("format_version", 2) if isinstance(meta, dict) else 1
    for key in list(storage.data_store_names()) + ["memory"]:
        if key in payload:
            info["stores"][key] = len(payload[key]) if hasattr(payload[key], "__len__") else 0
    info["missing_stores"] = [n for n in storage.data_store_names() if n not in payload]
    return info


def list_backups() -> List[Path]:
    """Backups of the active profile, newest first."""
    return list(reversed(_list_backups(backups_dir())))


def latest_backup() -> Optional[Path]:
    """Newest backup of the active profile, or None if there is none."""
    backups = list_backups()
    return backups[0] if backups else None


def format_backup_status(now: Optional[datetime] = None) -> str:
    """Human-readable status of the active profile's backups: how many,
    when the newest was taken, how big it is, and whether it is complete."""
    now = now or datetime.now()
    backups = list_backups()
    if not backups:
        return ("No backups yet. Use backup_now to create one - the scheduler also takes "
                "one automatically every day at 20:30 while it is running.")

    latest = describe_backup(backups[0])
    lines = [f"{len(backups)} backup(s) saved in {backups_dir()}."]
    if latest["created"] is not None:
        age = now - latest["created"]
        hours = age.total_seconds() / 3600
        if hours < 1:
            ago = "less than an hour ago"
        elif hours < 48:
            ago = f"{int(hours)} hour(s) ago"
        else:
            ago = f"{age.days} day(s) ago"
        lines.append(f"Newest: {latest['name']} ({ago}, {round(latest['size_bytes'] / 1024, 1)} KB).")
    else:
        lines.append(f"Newest: {latest['name']} ({round(latest['size_bytes'] / 1024, 1)} KB).")
    if latest["encrypted"]:
        lines.append("It is encrypted with your LIFE_OS_ENCRYPTION_KEY.")

    if not latest["readable"]:
        lines.append("Warning: the newest backup could not be read - it may be corrupt, or encrypted "
                     "with a different passphrase than the one currently set. "
                     "Run backup_now to take a fresh one.")
    else:
        lines.append(f"It holds {latest['stores'].get('memory', 0)} memory entries across "
                     f"{len(latest['stores'])} data sections.")
        if latest["missing_stores"]:
            lines.append("Note: it predates complete backups and is missing: "
                         + ", ".join(latest["missing_stores"]) + ". Run backup_now for a full one.")
    lines.append("To restore, run `hermes-life-os-restore --latest --dry-run` from a terminal "
                 "(restoring is deliberately not available from chat).")
    return "\n".join(lines)


STALE_BACKUP_DAYS = 3


def backup_alert(now: Optional[datetime] = None,
                 stale_days: int = STALE_BACKUP_DAYS) -> Optional[str]:
    """A one-line warning if backups exist but the newest one is more than
    `stale_days` days old or cannot be read; None when there is no backup
    at all (nobody is nagged to start backing up), or the newest one is
    recent and readable. Used by nudges.generate_nudges."""
    now = now or datetime.now()
    latest = latest_backup()
    if latest is None:
        return None
    info = describe_backup(latest)
    if not info["readable"]:
        return ("Your newest backup could not be read - it may be corrupt, or encrypted with a "
                "different passphrase. Run backup_now to take a fresh one.")
    created = info["created"]
    if created is not None and (now - created).days >= stale_days:
        return (f"Your last backup is {(now - created).days} days old. "
                f"Run backup_now (the scheduler takes one daily while it is running).")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a rotating local backup.")
    parser.add_argument("--profile", default=None, help="Profile to back up (default: the default profile).")
    parser.add_argument("--keep", type=int, default=7, help="Number of most recent backups to retain (default: 7).")
    args = parser.parse_args()

    storage.set_active_profile(args.profile)
    out_path = run_backup(keep=args.keep)
    print(f"Backup written: {out_path}")


if __name__ == "__main__":
    main()
