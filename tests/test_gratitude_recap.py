"""Tests for demo/gratitude_recap.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def gratitude_recap(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "gratitude_recap"):
        if mod in sys.modules:
            del sys.modules[mod]
    import gratitude_recap as gr
    importlib.reload(gr)
    import storage
    storage.set_active_profile(None)
    return gr


def _days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


class TestTokenize:
    def test_lowercases_and_strips_punctuation(self, gratitude_recap):
        assert gratitude_recap._tokenize("Sunny, warm weather!") == ["sunny", "warm", "weather"]

    def test_stopwords_and_short_words_removed(self, gratitude_recap):
        assert gratitude_recap._tokenize("I am so grateful for my dog") == ["grateful", "dog"]


class TestComputeGratitudeRecap:
    def test_no_entries_returns_zeroed_result(self, gratitude_recap):
        result = gratitude_recap.compute_gratitude_recap(30)
        assert result["total_entries"] == 0
        assert result["top_words"] == []

    def test_totals(self, gratitude_recap):
        import storage
        storage.save_mental([
            {"date": _days_ago(1), "type": "gratitude", "items": ["my dog", "sunny weather"]},
            {"date": _days_ago(2), "type": "gratitude", "items": ["good coffee"]},
        ])
        result = gratitude_recap.compute_gratitude_recap(30)
        assert result["total_entries"] == 2
        assert result["total_items"] == 3

    def test_top_words_frequency(self, gratitude_recap):
        import storage
        storage.save_mental([
            {"date": _days_ago(1), "type": "gratitude", "items": ["my dog"]},
            {"date": _days_ago(2), "type": "gratitude", "items": ["my dog again"]},
            {"date": _days_ago(3), "type": "gratitude", "items": ["good coffee"]},
        ])
        result = gratitude_recap.compute_gratitude_recap(30)
        assert result["top_words"][0] == ("dog", 2)

    def test_recent_items_most_recent_first(self, gratitude_recap):
        import storage
        storage.save_mental([
            {"date": _days_ago(5), "type": "gratitude", "items": ["old thing"]},
            {"date": _days_ago(1), "type": "gratitude", "items": ["new thing"]},
        ])
        result = gratitude_recap.compute_gratitude_recap(30)
        assert result["recent_items"][0] == "new thing"

    def test_non_gratitude_mental_entries_excluded(self, gratitude_recap):
        import storage
        storage.save_mental([{"date": _days_ago(1), "type": "meditation", "duration": 10}])
        result = gratitude_recap.compute_gratitude_recap(30)
        assert result["total_entries"] == 0

    def test_outside_window_excluded(self, gratitude_recap):
        import storage
        storage.save_mental([{"date": _days_ago(60), "type": "gratitude", "items": ["old"]}])
        result = gratitude_recap.compute_gratitude_recap(30)
        assert result["total_entries"] == 0


class TestFormatGratitudeRecap:
    def test_no_entries_message(self, gratitude_recap):
        result = {"days": 30, "total_entries": 0, "total_items": 0,
                  "top_words": [], "recent_items": []}
        text = gratitude_recap.format_gratitude_recap(result)
        assert "No gratitude entries logged" in text

    def test_with_data_shows_themes_and_recent(self, gratitude_recap):
        result = {"days": 30, "total_entries": 2, "total_items": 3,
                  "top_words": [("dog", 2), ("coffee", 1)],
                  "recent_items": ["my dog", "good coffee"]}
        text = gratitude_recap.format_gratitude_recap(result)
        assert "dog (2)" in text
        assert "my dog; good coffee" in text
