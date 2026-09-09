"""Tests for demo/reading_pace.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def reading_pace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "reading_pace"):
        if mod in sys.modules:
            del sys.modules[mod]
    import reading_pace as rp
    importlib.reload(rp)
    import storage
    storage.set_active_profile(None)
    return rp


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestComputeReadingPace:
    def test_no_sessions_returns_zeroed_result(self, reading_pace):
        result = reading_pace.compute_reading_pace("Unknown Book")
        assert result["total_sessions"] == 0
        assert result["total_pages"] is None

    def test_title_matching_case_insensitive(self, reading_pace):
        import storage
        storage.save_reading([{"date": _days_ago(1), "title": "Atomic Habits", "pages": 20}])
        result = reading_pace.compute_reading_pace("atomic habits")
        assert result["total_sessions"] == 1

    def test_pages_per_day_average(self, reading_pace):
        import storage
        storage.save_reading([
            {"date": _days_ago(1), "title": "Book A", "pages": 20},
            {"date": _days_ago(2), "title": "Book A", "pages": 30},
        ])
        result = reading_pace.compute_reading_pace("Book A")
        assert result["total_pages_read"] == 50
        assert result["days_active"] == 2
        assert result["pages_per_day"] == 25.0

    def test_multiple_sessions_same_day_count_as_one_active_day(self, reading_pace):
        import storage
        storage.save_reading([
            {"date": _days_ago(1), "title": "Book A", "pages": 10},
            {"date": _days_ago(1), "title": "Book A", "pages": 10},
        ])
        result = reading_pace.compute_reading_pace("Book A")
        assert result["days_active"] == 1
        assert result["pages_per_day"] == 20.0

    def test_no_total_pages_means_no_estimate(self, reading_pace):
        import storage
        storage.save_reading([{"date": _days_ago(1), "title": "Book A", "pages": 20}])
        result = reading_pace.compute_reading_pace("Book A")
        assert result["estimated_days_remaining"] is None

    def test_total_pages_enables_estimate(self, reading_pace):
        import storage
        storage.save_reading([
            {"date": _days_ago(2), "title": "Book A", "pages": 50, "total_pages": 300},
            {"date": _days_ago(1), "title": "Book A", "pages": 50},
        ])
        result = reading_pace.compute_reading_pace("Book A")
        assert result["total_pages"] == 300
        assert result["pages_remaining"] == 200
        assert result["estimated_days_remaining"] == 4  # 200 / 50 per day, ceil

    def test_most_recent_total_pages_used(self, reading_pace):
        import storage
        storage.save_reading([
            {"date": _days_ago(3), "title": "Book A", "pages": 10, "total_pages": 250},
            {"date": _days_ago(1), "title": "Book A", "pages": 10, "total_pages": 300},
        ])
        result = reading_pace.compute_reading_pace("Book A")
        assert result["total_pages"] == 300

    def test_finished_book_shows_zero_remaining(self, reading_pace):
        import storage
        storage.save_reading([{"date": _days_ago(1), "title": "Book A", "pages": 300, "total_pages": 300}])
        result = reading_pace.compute_reading_pace("Book A")
        assert result["pages_remaining"] == 0

    def test_overshoot_does_not_go_negative(self, reading_pace):
        import storage
        storage.save_reading([{"date": _days_ago(1), "title": "Book A", "pages": 350, "total_pages": 300}])
        result = reading_pace.compute_reading_pace("Book A")
        assert result["pages_remaining"] == 0


class TestFormatReadingPace:
    def test_no_sessions_message(self, reading_pace):
        result = {"title": "Ghost Book", "total_sessions": 0, "total_pages_read": 0,
                  "days_active": 0, "pages_per_day": 0.0, "total_pages": None,
                  "pages_remaining": None, "estimated_days_remaining": None,
                  "estimated_finish_date": None}
        text = reading_pace.format_reading_pace(result)
        assert "No reading logged for 'Ghost Book'" in text

    def test_no_total_pages_message(self, reading_pace):
        result = {"title": "Book A", "total_sessions": 1, "total_pages_read": 20,
                  "days_active": 1, "pages_per_day": 20.0, "total_pages": None,
                  "pages_remaining": None, "estimated_days_remaining": None,
                  "estimated_finish_date": None}
        text = reading_pace.format_reading_pace(result)
        assert "No total page count on file" in text

    def test_with_estimate_shows_finish_date(self, reading_pace):
        result = {"title": "Book A", "total_sessions": 2, "total_pages_read": 100,
                  "days_active": 2, "pages_per_day": 50.0, "total_pages": 300,
                  "pages_remaining": 200, "estimated_days_remaining": 4,
                  "estimated_finish_date": "2026-01-05"}
        text = reading_pace.format_reading_pace(result)
        assert "4 day(s) left" in text
        assert "2026-01-05" in text

    def test_finished_message(self, reading_pace):
        result = {"title": "Book A", "total_sessions": 1, "total_pages_read": 300,
                  "days_active": 1, "pages_per_day": 300.0, "total_pages": 300,
                  "pages_remaining": 0, "estimated_days_remaining": None,
                  "estimated_finish_date": None}
        text = reading_pace.format_reading_pace(result)
        assert "Looks finished!" in text
