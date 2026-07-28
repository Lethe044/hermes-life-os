"""
Hermes Life OS - Calendar Import
===================================
Correlates meeting-heavy days with mood/stress/sleep, without needing
any OAuth setup or live API access. Works from a standard .ics file -
the universal calendar export format supported by Google Calendar,
Outlook, and Apple Calendar alike:

  Google Calendar:  Settings -> Import & export -> Export
  Outlook:          File -> Save Calendar
  Apple Calendar:   File -> Export -> Export...

Only counts timed events (all-day events have no meaningful "hours",
so they're skipped) and only VEVENT blocks with both DTSTART and DTEND.
Recurring events (RRULE) are counted once, on their own start date -
this is a simple importer, not a full calendar engine.

Usage:
    python demo/calendar_import.py --ics calendar.ics
    python demo/calendar_import.py --ics calendar.ics --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage

_DATE_TIME_RE = re.compile(r"^(\d{8})T(\d{6})Z?$")
_DATE_ONLY_RE = re.compile(r"^(\d{8})$")


def _unfold_lines(raw_text: str) -> List[str]:
    """iCalendar 'folds' long lines by breaking them and indenting the
    continuation with a space or tab - undo that so each logical
    property is on one line."""
    lines: List[str] = []
    for line in raw_text.splitlines():
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _parse_ics_datetime(value: str) -> Optional[datetime]:
    m = _DATE_TIME_RE.match(value)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            return None
    return None  # all-day (DATE-only) values are intentionally not counted


def parse_ics_meeting_hours(ics_path: str) -> Dict[str, float]:
    """Returns {date: total_meeting_hours} aggregated per calendar day,
    from every VEVENT with a timed (not all-day) DTSTART/DTEND pair."""
    text = Path(ics_path).read_text(encoding="utf-8", errors="replace")
    lines = _unfold_lines(text)

    per_day: Dict[str, float] = defaultdict(float)
    in_event = False
    dtstart: Optional[datetime] = None
    dtend: Optional[datetime] = None

    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            in_event = True
            dtstart = dtend = None
            continue
        if line.strip() == "END:VEVENT":
            if in_event and dtstart and dtend and dtend > dtstart:
                hours = (dtend - dtstart).total_seconds() / 3600.0
                per_day[dtstart.strftime("%Y-%m-%d")] += hours
            in_event = False
            continue
        if not in_event or ":" not in line:
            continue

        key, _, value = line.partition(":")
        prop = key.split(";")[0].upper()
        if prop == "DTSTART":
            dtstart = _parse_ics_datetime(value.strip())
        elif prop == "DTEND":
            dtend = _parse_ics_datetime(value.strip())

    return dict(per_day)


def import_ics(ics_path: str, dry_run: bool = False) -> int:
    """Imports meeting-hours-per-day from an .ics file. Returns the
    number of memory entries created (or that would be, if dry_run)."""
    per_day = parse_ics_meeting_hours(ics_path)
    count = 0
    for day, hours in per_day.items():
        if not dry_run:
            storage.write_memory({
                "type": "calendar", "meeting_hours": round(hours, 2),
                "timestamp": f"{day}T09:00:00Z", "source": "import",
            })
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Import meeting load from a calendar .ics export")
    parser.add_argument("--ics", required=True, metavar="FILE", help="Path to a .ics calendar export")
    parser.add_argument("--profile", default=None,
                        help="Named profile to import into. Default: 'default'. "
                             "Can also be set via LIFE_OS_PROFILE.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show how many entries would be imported without writing anything.")
    args = parser.parse_args()

    if not Path(args.ics).exists():
        print(f"File not found: {args.ics}")
        sys.exit(1)

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))
    count = import_ics(args.ics, dry_run=args.dry_run)

    verb = "Would import" if args.dry_run else "Imported"
    print(f"{verb} {count} days of meeting data from {args.ics} "
          f"(profile: {storage.ACTIVE_PROFILE}).")
    if count == 0:
        print("No timed events found - all-day events aren't counted, "
              "and the file must contain VEVENT blocks with DTSTART/DTEND.")
    else:
        print("Ask Hermes things like 'is my stress linked to meeting-heavy "
              "days?' or check the dashboard's Correlations section.")


if __name__ == "__main__":
    main()
