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
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List

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
    directory = backups_dir()
    directory.mkdir(parents=True, exist_ok=True)

    ts = (now or datetime.now()).strftime("%Y-%m-%d-%H%M%S")
    out_path = directory / f"backup-{ts}.json"
    export_json(str(out_path))

    rotate_backups(directory, keep)
    return out_path


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
