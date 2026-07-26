"""Tests for demo/health_import.py - Apple Health XML and generic CSV bulk import."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def health_import(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "health_import"):
        if mod in sys.modules:
            del sys.modules[mod]
    import health_import as hi
    importlib.reload(hi)
    return hi


APPLE_HEALTH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
<Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleep" startDate="2026-01-10 23:30:00 -0500" endDate="2026-01-11 06:45:00 -0500"/>
<Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleep" startDate="2026-01-11 23:00:00 -0500" endDate="2026-01-12 06:00:00 -0500"/>
<Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisInBed" startDate="2026-01-11 22:30:00 -0500" endDate="2026-01-12 06:30:00 -0500"/>
<Record type="HKQuantityTypeIdentifierDietaryWater" unit="mL" value="1500" startDate="2026-01-10 08:00:00 -0500" endDate="2026-01-10 08:00:00 -0500"/>
<Record type="HKQuantityTypeIdentifierDietaryWater" unit="mL" value="500" startDate="2026-01-10 14:00:00 -0500" endDate="2026-01-10 14:00:00 -0500"/>
<Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="8500" startDate="2026-01-10 12:00:00 -0500" endDate="2026-01-10 12:00:00 -0500"/>
</HealthData>
"""


@pytest.fixture()
def apple_health_file(tmp_path):
    p = tmp_path / "export.xml"
    p.write_text(APPLE_HEALTH_XML, encoding="utf-8")
    return str(p)


class TestParseAppleHealthSleep:
    def test_aggregates_asleep_segments_per_day(self, health_import, apple_health_file):
        result = health_import.parse_apple_health_sleep(apple_health_file)
        assert result["2026-01-10"] == pytest.approx(7.25, abs=0.01)
        assert result["2026-01-11"] == pytest.approx(7.0, abs=0.01)

    def test_ignores_in_bed_records(self, health_import, apple_health_file):
        # the InBed record (22:30-06:30 = 8h) must not be counted -
        # only the Asleep segment (23:00-06:00 = 7h) should be
        result = health_import.parse_apple_health_sleep(apple_health_file)
        assert result["2026-01-11"] == pytest.approx(7.0, abs=0.01)


class TestParseAppleHealthWater:
    def test_aggregates_ml_to_glasses(self, health_import, apple_health_file):
        result = health_import.parse_apple_health_water(apple_health_file)
        # 1500 + 500 = 2000 mL / 237 = ~8.44 glasses
        assert result["2026-01-10"] == pytest.approx(8.44, abs=0.05)


class TestImportAppleHealth:
    def test_creates_expected_entry_count(self, health_import, apple_health_file):
        count = health_import.import_apple_health(apple_health_file)
        assert count == 3  # 2 sleep nights + 1 water day

    def test_entries_are_written_with_historical_dates(self, health_import, apple_health_file):
        health_import.import_apple_health(apple_health_file)
        entries = health_import.storage.get_recent_memory(days=3650)
        dates = {e["timestamp"][:10] for e in entries}
        assert "2026-01-10" in dates
        assert "2026-01-11" in dates

    def test_entries_tagged_as_import_source(self, health_import, apple_health_file):
        health_import.import_apple_health(apple_health_file)
        entries = health_import.storage.get_recent_memory(days=3650)
        assert all(e.get("source") == "import" for e in entries)

    def test_dry_run_writes_nothing(self, health_import, apple_health_file):
        count = health_import.import_apple_health(apple_health_file, dry_run=True)
        assert count == 3
        assert health_import.storage.memory_count() == 0


CSV_CONTENT = """date,sleep_hours,mood,stress,energy,hydration
2026-01-01,7.5,8,3,3,6
2026-01-02,6.0,5,7,1,4
2026-01-03,,,,,
invalid-date,8,8,2,3,7
"""


@pytest.fixture()
def csv_file(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text(CSV_CONTENT, encoding="utf-8")
    return str(p)


class TestImportCsv:
    def test_creates_one_entry_per_nonempty_metric(self, health_import, csv_file):
        count = health_import.import_csv(csv_file)
        assert count == 10  # 5 metrics x 2 valid rows, row3 empty, row4 bad date

    def test_skips_rows_with_invalid_date(self, health_import, csv_file):
        health_import.import_csv(csv_file)
        entries = health_import.storage.get_recent_memory(days=3650)
        dates = {e["timestamp"][:10] for e in entries}
        assert "invalid-date" not in dates

    def test_skips_empty_row(self, health_import, csv_file):
        health_import.import_csv(csv_file)
        entries = health_import.storage.get_recent_memory(days=3650)
        assert not any(e["timestamp"].startswith("2026-01-03") for e in entries)

    def test_values_mapped_correctly(self, health_import, csv_file):
        health_import.import_csv(csv_file)
        entries = health_import.storage.get_recent_memory(days=3650)
        by_date_type = {(e["timestamp"][:10], e["type"]): e for e in entries}

        sleep = by_date_type[("2026-01-01", "sleep")]
        assert sleep["hours"] == 7.5

        mood = by_date_type[("2026-01-01", "mood")]
        assert mood["score"] == 8.0

        energy = by_date_type[("2026-01-01", "energy")]
        assert energy["level"] == "high"  # 3 -> high

        energy_low = by_date_type[("2026-01-02", "energy")]
        assert energy_low["level"] == "low"  # 1 -> low

    def test_dry_run_writes_nothing(self, health_import, csv_file):
        count = health_import.import_csv(csv_file, dry_run=True)
        assert count == 10
        assert health_import.storage.memory_count() == 0

    def test_ignores_unknown_columns(self, health_import, tmp_path):
        p = tmp_path / "weird.csv"
        p.write_text("date,sleep_hours,made_up_column\n2026-01-01,7,999\n", encoding="utf-8")
        count = health_import.import_csv(str(p))
        assert count == 1  # only sleep_hours counted, made_up_column ignored

    def test_non_numeric_value_skipped(self, health_import, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("date,mood\n2026-01-01,not-a-number\n", encoding="utf-8")
        count = health_import.import_csv(str(p))
        assert count == 0


class TestMainCli:
    def test_missing_apple_health_file_exits_cleanly(self, health_import, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["health_import.py", "--apple-health", str(tmp_path / "nope.xml")]
            health_import.main()
        assert exc_info.value.code == 1

    def test_missing_csv_file_exits_cleanly(self, health_import, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["health_import.py", "--csv", str(tmp_path / "nope.csv")]
            health_import.main()
        assert exc_info.value.code == 1

    def test_successful_csv_import_via_cli(self, health_import, csv_file, capsys):
        sys.argv = ["health_import.py", "--csv", csv_file]
        health_import.main()
        captured = capsys.readouterr()
        assert "Imported 10 entries" in captured.out

    def test_profile_flag_isolates_import(self, health_import, apple_health_file):
        sys.argv = ["health_import.py", "--apple-health", apple_health_file, "--profile", "alex"]
        health_import.main()
        assert health_import.storage.ACTIVE_PROFILE == "alex"
        assert health_import.storage.memory_count() == 3

        health_import.storage.set_active_profile(None)
        assert health_import.storage.memory_count() == 0  # default profile untouched


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
