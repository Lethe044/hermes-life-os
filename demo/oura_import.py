"""
Hermes Life OS - Oura Ring Import
=====================================
Imports sleep duration and readiness scores from an Oura Ring, using a
Personal Access Token - no OAuth login flow needed:

    1. https://cloud.ouraring.com/personal-access-tokens
    2. "Create New Personal Access Token"
    3. set OURA_PERSONAL_ACCESS_TOKEN=...
    4. python demo/oura_import.py --days 30

Sleep duration is imported as a normal "sleep" entry (hours), the same
type used everywhere else in Hermes Life OS, so it merges directly with
manually logged sleep and Apple Health imports and participates in the
same correlations/goals/dashboard. Readiness is imported as a new
"readiness" metric (Oura's own 0-100 recovery score) - also fully
tracked, so you can ask things like "is my readiness linked to sleep?"

A note on testing: this module's HTTP calls are built against Oura's
documented v2 API response shape, but this environment has no network
access to api.ouraring.com, so they haven't been exercised against a
live account. The response-parsing logic (parse_sleep_response,
parse_readiness_response) is thoroughly unit tested against fixture
JSON matching Oura's documented schema - the actual HTTP round-trip is
simple and low-risk, but your first real run is the true end-to-end
check. If Oura's response shape doesn't match, please report back what
you see and it's a quick fix.

Usage:
    python demo/oura_import.py --days 30
    python demo/oura_import.py --start-date 2026-01-01 --end-date 2026-01-31
    python demo/oura_import.py --days 7 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage

OURA_API_BASE = "https://api.ouraring.com/v2/usercollection"


class OuraError(RuntimeError):
    pass


def _oura_get(token: str, endpoint: str, start_date: str, end_date: str) -> Dict[str, Any]:
    url = f"{OURA_API_BASE}/{endpoint}?start_date={start_date}&end_date={end_date}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise OuraError("Oura rejected the token (401) - it may be invalid or expired. "
                             "Generate a new one at https://cloud.ouraring.com/personal-access-tokens") from e
        raise OuraError(f"Oura API request to '{endpoint}' failed ({e.code}): {e}") from e
    except urllib.error.URLError as e:
        raise OuraError(f"Oura API request to '{endpoint}' failed: {e}") from e


def parse_sleep_response(data: Dict[str, Any]) -> Dict[str, float]:
    """Oura's /v2/usercollection/sleep returns {"data": [{"day": "...",
    "total_sleep_duration": <seconds>, "type": "long_sleep"|"nap"|...}, ...]}.
    Sums same-day periods (e.g. a nap plus the main sleep) into total hours."""
    per_day: Dict[str, float] = defaultdict(float)
    for record in data.get("data", []) or []:
        day = record.get("day")
        seconds = record.get("total_sleep_duration")
        if day and seconds:
            per_day[day] += seconds / 3600.0
    return dict(per_day)


def parse_readiness_response(data: Dict[str, Any]) -> Dict[str, float]:
    """Oura's /v2/usercollection/daily_readiness returns {"data": [{"day":
    "...", "score": 0-100, ...}, ...]}. One score per day - later entries
    for the same day (shouldn't normally happen) overwrite earlier ones."""
    per_day: Dict[str, float] = {}
    for record in data.get("data", []) or []:
        day = record.get("day")
        score = record.get("score")
        if day and score is not None:
            per_day[day] = float(score)
    return per_day


def import_oura(token: str, start_date: str, end_date: str, dry_run: bool = False) -> int:
    """Fetches and imports sleep + readiness for the given date range.
    Returns the number of memory entries created (or that would be, if
    dry_run)."""
    sleep_by_day = parse_sleep_response(_oura_get(token, "sleep", start_date, end_date))
    readiness_by_day = parse_readiness_response(_oura_get(token, "daily_readiness", start_date, end_date))

    count = 0
    for day, hours in sleep_by_day.items():
        if not dry_run:
            storage.write_memory({
                "type": "sleep", "hours": round(hours, 2),
                "timestamp": f"{day}T09:00:00Z", "source": "oura",
            })
        count += 1
    for day, score in readiness_by_day.items():
        if not dry_run:
            storage.write_memory({
                "type": "oura_readiness", "score": score,
                "timestamp": f"{day}T09:00:00Z", "source": "oura",
            })
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Import sleep and readiness data from Oura Ring")
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--days", type=int, default=7, help="Import the last N days (default: 7)")
    date_group.add_argument("--start-date", metavar="YYYY-MM-DD")
    parser.add_argument("--end-date", metavar="YYYY-MM-DD",
                        help="Required if --start-date is given; defaults to today otherwise")
    parser.add_argument("--token", default=None,
                        help="Oura Personal Access Token. Default: OURA_PERSONAL_ACCESS_TOKEN env var.")
    parser.add_argument("--profile", default=None,
                        help="Named profile to import into. Default: 'default'. "
                             "Can also be set via LIFE_OS_PROFILE.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show how many entries would be imported without writing anything.")
    args = parser.parse_args()

    if args.start_date and not args.end_date:
        parser.error("--end-date is required when --start-date is given")

    token = args.token or os.environ.get("OURA_PERSONAL_ACCESS_TOKEN")
    if not token:
        print("Set OURA_PERSONAL_ACCESS_TOKEN first (see this file's docstring for setup steps).")
        sys.exit(1)

    if args.start_date:
        start_date, end_date = args.start_date, args.end_date
    else:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    try:
        count = import_oura(token, start_date, end_date, dry_run=args.dry_run)
    except OuraError as e:
        print(f"Import failed: {e}")
        sys.exit(1)

    verb = "Would import" if args.dry_run else "Imported"
    print(f"{verb} {count} entries from Oura ({start_date} to {end_date}, "
          f"profile: {storage.ACTIVE_PROFILE}).")
    if count == 0:
        print("No data found for that range - check the dates and that your ring has synced.")


if __name__ == "__main__":
    main()
