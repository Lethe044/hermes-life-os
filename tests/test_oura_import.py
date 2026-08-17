"""Tests for demo/oura_import.py. Fixture JSON matches Oura's documented
v2 API response shape. No live network access to api.ouraring.com -
_oura_get is monkeypatched for the higher-level import tests, and
tested for error handling separately via a mocked urlopen."""

from __future__ import annotations

import importlib
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def oura_import(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "oura_import"):
        if mod in sys.modules:
            del sys.modules[mod]
    import oura_import as oi
    importlib.reload(oi)
    return oi


SLEEP_RESPONSE = {
    "data": [
        {"day": "2026-01-10", "total_sleep_duration": 25200, "time_in_bed": 26100, "type": "long_sleep"},
        {"day": "2026-01-11", "total_sleep_duration": 27000, "time_in_bed": 28000, "type": "long_sleep"},
        {"day": "2026-01-11", "total_sleep_duration": 1800, "time_in_bed": 2000, "type": "nap"},
    ],
    "next_token": None,
}

READINESS_RESPONSE = {
    "data": [
        {"day": "2026-01-10", "score": 78, "temperature_deviation": 0.1},
        {"day": "2026-01-11", "score": 85, "temperature_deviation": -0.1},
    ],
    "next_token": None,
}


class TestParseSleepResponse:
    def test_converts_seconds_to_hours(self, oura_import):
        result = oura_import.parse_sleep_response(SLEEP_RESPONSE)
        assert result["2026-01-10"] == pytest.approx(7.0)

    def test_sums_multiple_periods_same_day(self, oura_import):
        result = oura_import.parse_sleep_response(SLEEP_RESPONSE)
        assert result["2026-01-11"] == pytest.approx(8.0)

    def test_empty_data_returns_empty(self, oura_import):
        assert oura_import.parse_sleep_response({"data": []}) == {}

    def test_missing_data_key_returns_empty(self, oura_import):
        assert oura_import.parse_sleep_response({}) == {}

    def test_record_without_duration_skipped(self, oura_import):
        data = {"data": [{"day": "2026-01-10", "total_sleep_duration": None}]}
        assert oura_import.parse_sleep_response(data) == {}


class TestParseReadinessResponse:
    def test_extracts_scores_per_day(self, oura_import):
        result = oura_import.parse_readiness_response(READINESS_RESPONSE)
        assert result == {"2026-01-10": 78.0, "2026-01-11": 85.0}

    def test_empty_data_returns_empty(self, oura_import):
        assert oura_import.parse_readiness_response({"data": []}) == {}

    def test_score_zero_is_not_treated_as_missing(self, oura_import):
        data = {"data": [{"day": "2026-01-10", "score": 0}]}
        assert oura_import.parse_readiness_response(data) == {"2026-01-10": 0.0}


class TestImportOura:
    def test_creates_expected_entries(self, oura_import, monkeypatch):
        def fake_get(token, endpoint, start_date, end_date):
            return SLEEP_RESPONSE if endpoint == "sleep" else READINESS_RESPONSE

        monkeypatch.setattr(oura_import, "_oura_get", fake_get)
        count = oura_import.import_oura("fake-token", "2026-01-10", "2026-01-11")
        assert count == 4

    def test_sleep_entries_use_existing_sleep_type(self, oura_import, monkeypatch):
        monkeypatch.setattr(oura_import, "_oura_get",
                            lambda t, e, s, end: SLEEP_RESPONSE if e == "sleep" else {"data": []})
        oura_import.import_oura("fake-token", "2026-01-10", "2026-01-11")
        entries = oura_import.storage.get_recent_memory(days=3650)
        assert all(e["type"] == "sleep" for e in entries)
        assert all(e["source"] == "oura" for e in entries)

    def test_readiness_feeds_into_analytics_metric(self, oura_import, monkeypatch):
        import analytics
        monkeypatch.setattr(oura_import, "_oura_get",
                            lambda t, e, s, end: READINESS_RESPONSE if e == "daily_readiness" else {"data": []})
        oura_import.import_oura("fake-token", "2026-01-10", "2026-01-11")
        entries = oura_import.storage.get_recent_memory(days=3650)
        daily = analytics.daily_averages(entries)
        assert daily["2026-01-10"]["readiness"] == 78.0

    def test_dry_run_writes_nothing(self, oura_import, monkeypatch):
        monkeypatch.setattr(oura_import, "_oura_get",
                            lambda t, e, s, end: SLEEP_RESPONSE if e == "sleep" else READINESS_RESPONSE)
        count = oura_import.import_oura("fake-token", "2026-01-10", "2026-01-11", dry_run=True)
        assert count == 4
        assert oura_import.storage.memory_count() == 0


class TestOuraGetErrorHandling:
    def test_401_raises_clear_token_error(self, oura_import, monkeypatch):
        def raise_401(*a, **k):
            raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

        monkeypatch.setattr(oura_import.urllib.request, "urlopen", raise_401)
        with pytest.raises(oura_import.OuraError, match="token"):
            oura_import._oura_get("bad-token", "sleep", "2026-01-01", "2026-01-02")

    def test_network_error_raises_oura_error(self, oura_import, monkeypatch):
        def raise_url_error(*a, **k):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(oura_import.urllib.request, "urlopen", raise_url_error)
        with pytest.raises(oura_import.OuraError):
            oura_import._oura_get("token", "sleep", "2026-01-01", "2026-01-02")


class TestMainCli:
    def test_missing_token_exits_cleanly(self, oura_import, monkeypatch):
        monkeypatch.delenv("OURA_PERSONAL_ACCESS_TOKEN", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["oura_import.py"]
            oura_import.main()
        assert exc_info.value.code == 1

    def test_start_date_without_end_date_errors(self, oura_import, monkeypatch):
        monkeypatch.setenv("OURA_PERSONAL_ACCESS_TOKEN", "fake-token")
        with pytest.raises(SystemExit):
            sys.argv = ["oura_import.py", "--start-date", "2026-01-01"]
            oura_import.main()

    def test_successful_import_via_cli(self, oura_import, monkeypatch, capsys):
        monkeypatch.setenv("OURA_PERSONAL_ACCESS_TOKEN", "fake-token")
        monkeypatch.setattr(oura_import, "_oura_get",
                            lambda t, e, s, end: SLEEP_RESPONSE if e == "sleep" else READINESS_RESPONSE)
        sys.argv = ["oura_import.py", "--days", "7"]
        oura_import.main()
        captured = capsys.readouterr()
        assert "Imported 4 entries" in captured.out

    def test_profile_flag_isolates_import(self, oura_import, monkeypatch):
        monkeypatch.setenv("OURA_PERSONAL_ACCESS_TOKEN", "fake-token")
        monkeypatch.setattr(oura_import, "_oura_get",
                            lambda t, e, s, end: SLEEP_RESPONSE if e == "sleep" else READINESS_RESPONSE)
        sys.argv = ["oura_import.py", "--days", "7", "--profile", "alex"]
        oura_import.main()
        assert oura_import.storage.ACTIVE_PROFILE == "alex"
        assert oura_import.storage.memory_count() == 4

        oura_import.storage.set_active_profile(None)
        assert oura_import.storage.memory_count() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
