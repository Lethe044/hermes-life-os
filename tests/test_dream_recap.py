"""Tests for demo/dream_recap.py."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def dream_recap(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "dream_recap"):
        if mod in sys.modules:
            del sys.modules[mod]
    import dream_recap as dr
    importlib.reload(dr)
    import storage
    storage.set_active_profile(None)
    return dr


def _write_dream(storage, days_ago, symbols=None, emotions=None, tone="neutral", vividness=5):
    dt = datetime.utcnow() - timedelta(days=days_ago)
    storage.write_memory({
        "type": "dream", "content": "dream", "symbols": symbols or [],
        "emotions": emotions or [], "tone": tone, "vividness": vividness,
        "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


class TestComputeDreamRecap:
    def test_no_dreams_returns_zeroed_result(self, dream_recap):
        result = dream_recap.compute_dream_recap(30)
        assert result["total_dreams"] == 0
        assert result["most_common_tone"] is None

    def test_totals_and_avg_vividness(self, dream_recap):
        import storage
        _write_dream(storage, 1, vividness=8)
        _write_dream(storage, 2, vividness=4)
        result = dream_recap.compute_dream_recap(30)
        assert result["total_dreams"] == 2
        assert result["avg_vividness"] == 6.0

    def test_most_common_tone(self, dream_recap):
        import storage
        _write_dream(storage, 1, tone="anxious")
        _write_dream(storage, 2, tone="anxious")
        _write_dream(storage, 3, tone="peaceful")
        result = dream_recap.compute_dream_recap(30)
        assert result["most_common_tone"] == "anxious"

    def test_recurring_symbols_across_dreams(self, dream_recap):
        import storage
        _write_dream(storage, 1, symbols=["water", "flying"])
        _write_dream(storage, 2, symbols=["water"])
        _write_dream(storage, 3, symbols=["fire"])
        result = dream_recap.compute_dream_recap(30)
        assert ("water", 2) in result["recurring_symbols"]
        assert not any(s == "fire" for s, _ in result["recurring_symbols"])

    def test_symbol_repeated_within_one_dream_only_counts_once(self, dream_recap):
        import storage
        _write_dream(storage, 1, symbols=["water", "water"])
        result = dream_recap.compute_dream_recap(30)
        assert result["recurring_symbols"] == []

    def test_recurring_emotions(self, dream_recap):
        import storage
        _write_dream(storage, 1, emotions=["fear"])
        _write_dream(storage, 2, emotions=["fear"])
        result = dream_recap.compute_dream_recap(30)
        assert ("fear", 2) in result["recurring_emotions"]

    def test_non_dream_entries_excluded(self, dream_recap):
        import storage
        storage.write_memory({"type": "mood", "content": "ok", "score": 5})
        result = dream_recap.compute_dream_recap(30)
        assert result["total_dreams"] == 0


class TestFormatDreamRecap:
    def test_no_dreams_message(self, dream_recap):
        result = {"days": 30, "total_dreams": 0, "avg_vividness": 0.0,
                  "most_common_tone": None, "recurring_symbols": [], "recurring_emotions": []}
        text = dream_recap.format_dream_recap(result)
        assert "No dreams logged" in text

    def test_with_data_shows_recurring(self, dream_recap):
        result = {"days": 30, "total_dreams": 3, "avg_vividness": 6.0,
                  "most_common_tone": "anxious", "recurring_symbols": [("water", 2)],
                  "recurring_emotions": [("fear", 2)]}
        text = dream_recap.format_dream_recap(result)
        assert "water (2x)" in text
        assert "fear (2x)" in text
