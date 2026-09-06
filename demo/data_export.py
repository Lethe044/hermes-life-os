"""
Hermes Life OS - Data Export
===============================
Your data isn't locked in - export it any time.

  - JSON: a complete backup (every memory entry plus profile, habits,
    goals, and the nutrition/sleep/hydration/fitness/focus/mental logs),
    unmodified.
  - CSV: one row per day with columns (date, sleep_hours, mood, stress,
    energy, hydration) - the same shape health_import.py's --csv import
    expects, so you can export, edit in a spreadsheet, and re-import
    elsewhere.
  - Markdown: one file per day (YYYY-MM-DD.md) with YAML frontmatter
    for that day's numeric metrics and a bullet list of logged entries -
    matches Obsidian's Daily Notes plugin filename convention, and
    Notion's importer reads YAML frontmatter as page properties, so the
    same export folder drops into either tool with no conversion step.

Usage:
    python demo/data_export.py --json backup.json
    python demo/data_export.py --csv summary.csv
    python demo/data_export.py --markdown ./obsidian-vault/hermes
    python demo/data_export.py --json backup.json --csv summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
from analytics import daily_averages

_CSV_COLUMN_FOR_METRIC = {
    "sleep": "sleep_hours",
    "mood": "mood",
    "stress": "stress",
    "energy": "energy",
    "hydration": "hydration",
}
CSV_FIELDNAMES = ["date", "sleep_hours", "mood", "stress", "energy", "hydration"]


def export_json(out_path: str) -> int:
    """Writes a complete backup: every memory entry plus profile, habits,
    goals, and every other tracked log. Returns the number of memory
    entries included (the headline count; the other sections are
    included in full regardless)."""
    entries = storage.get_all_memory()
    payload = {
        "profile": storage.load_profile(),
        "habits": storage.load_habits(),
        "goals": storage.load_goals(),
        "nutrition": storage.load_nutrition(),
        "sleep": storage.load_sleep(),
        "hydration": storage.load_hydration(),
        "fitness": storage.load_fitness(),
        "focus": storage.load_focus(),
        "mental": storage.load_mental(),
        "memory": entries,
    }
    Path(out_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(entries)


def export_csv(out_path: str) -> int:
    """Writes one row per calendar day with a value for each metric that
    has data that day (blank if not logged). Returns the number of rows
    (days) written."""
    entries = storage.get_all_memory()
    daily = daily_averages(entries)

    rows: List[Dict[str, str]] = []
    for date in sorted(daily.keys()):
        day = daily[date]
        row = {"date": date}
        for metric, column in _CSV_COLUMN_FOR_METRIC.items():
            if metric in day:
                row[column] = day[metric]
        rows.append(row)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return len(rows)


def export_markdown(out_dir: str, days: Optional[int] = None) -> int:
    """Writes one daily note per day (YYYY-MM-DD.md) into `out_dir` -
    YAML frontmatter with that day's numeric metrics, then a bulleted
    list of every memory entry logged that day. Filename convention
    matches Obsidian's Daily Notes plugin; the YAML frontmatter is
    readable by Notion's markdown importer as page properties. Returns
    the number of daily notes written. `days=None` (default) exports
    everything; pass a number to export only a recent window."""
    entries = storage.get_all_memory() if days is None else storage.get_recent_memory(days)
    daily_metrics = daily_averages(entries)

    entries_by_date: Dict[str, List[dict]] = {}
    for e in entries:
        date = str(e.get("timestamp", ""))[:10]
        if date:
            entries_by_date.setdefault(date, []).append(e)

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    all_dates = sorted(set(daily_metrics.keys()) | set(entries_by_date.keys()))
    for date in all_dates:
        lines = ["---"]
        for metric, value in sorted(daily_metrics.get(date, {}).items()):
            lines.append(f"{metric}: {value}")
        lines.append("tags: hermes-life-os")
        lines.append("---")
        lines.append("")
        lines.append(f"# {date}")
        lines.append("")
        for e in entries_by_date.get(date, []):
            content = str(e.get("content", "")).replace("\n", " ").strip()
            entry_type = e.get("type", "entry")
            lines.append(f"- **{entry_type}**: {content}" if content else f"- **{entry_type}**")
        (out_path / f"{date}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return len(all_dates)


def main():
    parser = argparse.ArgumentParser(description="Export Hermes Life OS data")
    parser.add_argument("--json", metavar="FILE", help="Write a complete JSON backup to this path")
    parser.add_argument("--csv", metavar="FILE", help="Write a daily-summary CSV to this path "
                                                       "(re-importable via health_import.py --csv)")
    parser.add_argument("--markdown", metavar="DIR", help="Write one daily .md note per day into this "
                                                            "directory (Obsidian/Notion compatible)")
    parser.add_argument("--days", type=int, default=None,
                        help="Limit --markdown to the last N days. Default: export everything.")
    parser.add_argument("--profile", default=None,
                        help="Named profile to export. Default: 'default'. "
                             "Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args()

    if not args.json and not args.csv and not args.markdown:
        parser.error("Specify at least one of --json, --csv, or --markdown")

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    if args.json:
        count = export_json(args.json)
        print(f"Wrote {count} memory entries (plus profile/habits/goals/logs) to {args.json}")
    if args.csv:
        count = export_csv(args.csv)
        print(f"Wrote {count} daily rows to {args.csv}")
    if args.markdown:
        count = export_markdown(args.markdown, days=args.days)
        print(f"Wrote {count} daily notes to {args.markdown}/")


if __name__ == "__main__":
    main()
