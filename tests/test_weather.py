"""Tests for demo/weather.py. All Open-Meteo HTTP calls are mocked -
these tests never touch the real network, which also matches this
sandbox's restricted egress (only specific domains are reachable)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def weather(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "weather"):
        if mod in sys.modules:
            del sys.modules[mod]
    import weather as w
    import storage
    storage.set_active_profile(None)
    return w


def _mock_response(payload: dict):
    """Builds a context-manager mock standing in for
    urllib.request.urlopen()'s return value."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(payload).encode("utf-8")
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


GEOCODE_SUCCESS = {
    "results": [{"name": "Istanbul", "latitude": 41.0, "longitude": 28.9, "country": "Turkey"}]
}

ARCHIVE_SUCCESS = {
    "daily": {
        "time": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "temperature_2m_mean": [5.0, 8.0, 12.0, 15.0],
        "precipitation_sum": [10.0, 2.0, 0.0, 0.0],
    }
}


class TestGeocodeLocation:
    def test_successful_geocode(self, weather):
        with patch("urllib.request.urlopen", return_value=_mock_response(GEOCODE_SUCCESS)):
            result = weather.geocode_location("Istanbul")
        assert result["name"] == "Istanbul"
        assert result["latitude"] == 41.0
        assert result["longitude"] == 28.9

    def test_no_results_raises_weather_error(self, weather):
        with patch("urllib.request.urlopen", return_value=_mock_response({"results": []})):
            with pytest.raises(weather.WeatherError, match="No location found"):
                weather.geocode_location("Nowhereville")

    def test_network_failure_raises_weather_error(self, weather):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            with pytest.raises(weather.WeatherError, match="Could not look up location"):
                weather.geocode_location("Istanbul")

    def test_malformed_json_raises_weather_error(self, weather):
        mock = MagicMock()
        mock.read.return_value = b"not json"
        mock.__enter__.return_value = mock
        mock.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=mock):
            with pytest.raises(weather.WeatherError):
                weather.geocode_location("Istanbul")


class TestFetchDailyWeather:
    def test_successful_fetch(self, weather):
        with patch("urllib.request.urlopen", return_value=_mock_response(ARCHIVE_SUCCESS)):
            result = weather.fetch_daily_weather(41.0, 28.9, "2026-01-01", "2026-01-04")
        assert result["2026-01-01"] == {"temp": 5.0, "precipitation": 10.0}
        assert result["2026-01-04"] == {"temp": 15.0, "precipitation": 0.0}
        assert len(result) == 4

    def test_empty_time_array_raises(self, weather):
        with patch("urllib.request.urlopen", return_value=_mock_response({"daily": {"time": []}})):
            with pytest.raises(weather.WeatherError, match="No weather data"):
                weather.fetch_daily_weather(41.0, 28.9, "2026-01-01", "2026-01-04")

    def test_network_failure_raises_weather_error(self, weather):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(weather.WeatherError, match="Could not fetch weather data"):
                weather.fetch_daily_weather(41.0, 28.9, "2026-01-01", "2026-01-04")

    def test_null_values_in_response_are_skipped(self, weather):
        payload = {"daily": {
            "time": ["2026-01-01", "2026-01-02"],
            "temperature_2m_mean": [5.0, None],
            "precipitation_sum": [None, 3.0],
        }}
        with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
            result = weather.fetch_daily_weather(41.0, 28.9, "2026-01-01", "2026-01-02")
        assert result["2026-01-01"] == {"temp": 5.0}
        assert result["2026-01-02"] == {"precipitation": 3.0}


class TestAlign:
    def test_pairs_only_overlapping_dates(self, weather):
        weather_by_date = {"2026-01-01": {"temp": 5.0}, "2026-01-02": {"temp": 10.0}}
        tracked_daily = {"2026-01-01": {"mood": 6.0}, "2026-01-03": {"mood": 8.0}}
        aligned = weather._align(weather_by_date, "temp", tracked_daily)
        assert aligned["mood"] == ([5.0], [6.0])  # only 01-01 overlaps

    def test_no_overlap_returns_empty(self, weather):
        weather_by_date = {"2026-01-05": {"temp": 5.0}}
        tracked_daily = {"2026-01-01": {"mood": 6.0}}
        assert weather._align(weather_by_date, "temp", tracked_daily) == {}

    def test_missing_weather_metric_on_a_day_excluded(self, weather):
        weather_by_date = {"2026-01-01": {"precipitation": 1.0}}  # no "temp" key
        tracked_daily = {"2026-01-01": {"mood": 6.0}}
        assert weather._align(weather_by_date, "temp", tracked_daily) == {}


class TestComputeWeatherCorrelation:
    def test_full_flow_with_correlated_data(self, weather):
        import storage
        # Write mood entries that clearly trend with temperature
        # (mock will supply matching dates via the archive response).
        storage.write_memory({"type": "mood", "content": "day", "score": 3})

        def fake_urlopen(url, timeout=10):
            if "geocoding" in url:
                return _mock_response(GEOCODE_SUCCESS)
            return _mock_response(ARCHIVE_SUCCESS)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = weather.compute_weather_correlation("Istanbul", days=30)

        assert result["location"]["name"] == "Istanbul"
        assert result["days"] == 30
        assert isinstance(result["correlations"], list)

    def test_geocode_failure_propagates(self, weather):
        with patch("urllib.request.urlopen", return_value=_mock_response({"results": []})):
            with pytest.raises(weather.WeatherError):
                weather.compute_weather_correlation("Nowhereville")


class TestFormatWeatherInsights:
    def test_empty_correlations_returns_empty_list(self, weather):
        result = {"location": {"name": "Istanbul"}, "days": 30, "correlations": []}
        assert weather.format_weather_insights(result) == []

    def test_formats_positive_correlation(self, weather):
        result = {
            "location": {"name": "Istanbul"},
            "days": 30,
            "correlations": [{
                "weather_metric": "temp", "tracked_metric": "mood",
                "r": 0.65, "n_days": 10, "direction": "positive",
            }],
        }
        insights = weather.format_weather_insights(result)
        assert len(insights) == 1
        assert "Istanbul" in insights[0]
        assert "mood" in insights[0]
        assert "rise together" in insights[0]

    def test_respects_limit(self, weather):
        correlations = [
            {"weather_metric": "temp", "tracked_metric": f"metric{i}",
             "r": 0.5, "n_days": 5, "direction": "positive"}
            for i in range(5)
        ]
        result = {"location": {"name": "X"}, "days": 30, "correlations": correlations}
        assert len(weather.format_weather_insights(result, limit=2)) == 2
