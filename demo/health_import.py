"""
Hermes Life OS - Health Data Import
======================================
Reduces manual entry: bulk-import data you already have instead of
logging one day at a time through chat.

Two sources supported:

  1. Apple Health export.xml (Health app -> profile icon -> Export All
     Health Data). Imports Sleep Analysis and Dietary Water records,
     aggregated per calendar day.

  2. A generic CSV with a "date" column (YYYY-MM-DD) plus any subset of:
     sleep_hours, mood, stress, energy, hydration. Works with a Google
     Fit CSV export, a spreadsheet you already keep, or anything else
     you can get into that shape.

Imported entries keep their real historical date (not "today") and are
tagged {"source": "import"} so they're distinguishable from entries
logged live through chat.

Usage:
    python demo/health_import.py --apple-health export.xml
    python demo/health_import.py --csv my_data.csv
    python demo/health_import.py --csv my_data.csv --dry-run
"""

from __future__ import annotations

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage

CSV_METRIC_COLUMNS = ("sleep_hours", "mood", "stress", "energy", "hydration")

# ---------------------------------------------------------------------------
# Apple Health export.xml
# ---------------------------------------------------------------------------
#
# export.xml can be very large (hundreds of MB to a few GB for years of
# data), so this uses iterparse + elem.clear() to stream through it with
# bounded memory instead of loading the whole tree at once.

def _parse_apple_date(value: str):
    # Apple Health dates look like "2026-01-15 07:30:00 -0500"
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def parse_apple_health_sleep(xml_path: str) -> Dict[str, float]:
    """Returns {date: total_asleep_hours} aggregated per calendar day
    from HKCategoryTypeIdentifierSleepAnalysis records. Only counts
    "Asleep" segments (not "InBed", which includes time spent awake in bed)
    when both are present in the export."""
    per_day: Dict[str, float] = defaultdict(float)
    for _, elem in ET.iterparse(xml_path, events=("end",)):
        if elem.tag == "Record" and elem.get("type") == "HKCategoryTypeIdentifierSleepAnalysis":
            value = elem.get("value", "")
            if "Asleep" in value:
                start = _parse_apple_date(elem.get("startDate", ""))
                end = _parse_apple_date(elem.get("endDate", ""))
                if start and end and end > start:
                    hours = (end - start).total_seconds() / 3600.0
                    per_day[start.strftime("%Y-%m-%d")] += hours
        elem.clear()
    return dict(per_day)


def parse_apple_health_water(xml_path: str) -> Dict[str, float]:
    """Returns {date: total_glasses} from HKQuantityTypeIdentifierDietaryWater
    records, converting whatever unit Apple Health reports to glasses
    (1 glass ~= 8 fl oz ~= 237 mL ~= 0.237 L)."""
    per_day: Dict[str, float] = defaultdict(float)
    for _, elem in ET.iterparse(xml_path, events=("end",)):
        if elem.tag == "Record" and elem.get("type") == "HKQuantityTypeIdentifierDietaryWater":
            try:
                value = float(elem.get("value", "0"))
            except ValueError:
                elem.clear()
                continue
            unit = (elem.get("unit") or "").lower()
            if unit in ("ml", "milliliter", "milliliters"):
                glasses = value / 237.0
            elif unit in ("l", "liter", "liters"):
                glasses = value / 0.237
            elif unit in ("fl_oz_us", "floz", "fl oz"):
                glasses = value / 8.0
            else:
                glasses = value / 237.0  # Apple Health's default unit is mL
            per_day[elem.get("startDate", "")[:10]] += glasses
        elem.clear()
    return dict(per_day)


def import_apple_health(xml_path: str, dry_run: bool = False) -> int:
    """Imports sleep and water data from an Apple Health export.xml.
    Returns the number of memory entries created (or that would be
    created, if dry_run)."""
    sleep_by_day = parse_apple_health_sleep(xml_path)
    water_by_day = parse_apple_health_water(xml_path)

    count = 0
    for day, hours in sleep_by_day.items():
        if not dry_run:
            storage.write_memory({
                "type": "sleep", "hours": round(hours, 2),
                "timestamp": f"{day}T09:00:00Z", "source": "import",
            })
        count += 1
    for day, glasses in water_by_day.items():
        if not dry_run:
            storage.write_memory({
                "type": "hydration", "glasses": round(glasses, 1),
                "timestamp": f"{day}T09:00:00Z", "source": "import",
            })
        count += 1
    return count


# ---------------------------------------------------------------------------
# Generic CSV
# ---------------------------------------------------------------------------

def import_csv(csv_path: str, dry_run: bool = False) -> int:
    """
    Bulk-imports a CSV with a "date" column (YYYY-MM-DD) plus any subset
    of: sleep_hours, mood, stress, energy, hydration. Each non-empty
    metric column on a row becomes one memory entry dated that day.
    Unknown columns are ignored. Rows without a valid date are skipped.
    Returns the number of memory entries created (or that would be, if
    dry_run).
    """
    count = 0
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = (row.get("date") or "").strip()
            if not date:
                continue
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                continue
            ts = f"{date}T09:00:00Z"

            for col in CSV_METRIC_COLUMNS:
                raw = (row.get(col) or "").strip()
                if not raw:
                    continue
                try:
                    numeric = float(raw)
                except ValueError:
                    continue
                entry = {"timestamp": ts, "source": "import"}
                if col == "sleep_hours":
                    entry.update({"type": "sleep", "hours": numeric})
                elif col == "mood":
                    entry.update({"type": "mood", "score": numeric})
                elif col == "stress":
                    entry.update({"type": "stress", "score": numeric})
                elif col == "energy":
                    level = "low" if numeric <= 1 else ("high" if numeric >= 3 else "medium")
                    entry.update({"type": "energy", "level": level})
                elif col == "hydration":
                    entry.update({"type": "hydration", "glasses": numeric})
                if not dry_run:
                    storage.write_memory(entry)
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Bulk-import health data into Hermes Life OS")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--apple-health", metavar="EXPORT_XML",
                        help="Path to Apple Health's export.xml")
    source.add_argument("--csv", metavar="FILE",
                        help="Path to a CSV with a 'date' column plus any of: "
                             + ", ".join(CSV_METRIC_COLUMNS))
    parser.add_argument("--profile", default=None,
                        help="Named profile to import into. Default: 'default'. "
                             "Can also be set via LIFE_OS_PROFILE.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show how many entries would be imported without writing anything.")
    args = parser.parse_args()

    import os
    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    if args.apple_health:
        if not Path(args.apple_health).exists():
            print(f"File not found: {args.apple_health}")
            sys.exit(1)
        count = import_apple_health(args.apple_health, dry_run=args.dry_run)
        source_desc = "Apple Health export"
    else:
        if not Path(args.csv).exists():
            print(f"File not found: {args.csv}")
            sys.exit(1)
        count = import_csv(args.csv, dry_run=args.dry_run)
        source_desc = "CSV"

    verb = "Would import" if args.dry_run else "Imported"
    print(f"{verb} {count} entries from {source_desc} "
          f"(profile: {storage.ACTIVE_PROFILE}).")
    if count == 0:
        print("No recognized data found - check the file has the expected "
              "columns/record types.")


if __name__ == "__main__":
    main()
