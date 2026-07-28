"""Tests for demo/nudges.py - deterministic, LLM-free proactive nudge generation."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def nudges(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "nudges"):
        if mod in sys.modules:
            del sys.modules[mod]
    import nudges as n
    importlib.reload(n)
    return n


def _seed_recent(storage, entry_type, score_field, values):
    now = datetime.now(timezone.utc)
    with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
        for i, value in enumerate(values):
            ts = (now - timedelta(days=len(values) - i)).strftime("%Y-%m-%dT09:00:00Z")
            f.write(json.dumps({"type": entry_type, score_field: value, "timestamp": ts}) + "\n")


class TestGenerateNudges:
    def test_no_data_returns_empty(self, nudges):
        assert nudges.generate_nudges() == []

    def test_flags_anomaly(self, nudges):
        import storage
        _seed_recent(storage, "stress", "score", [3, 3, 3, 3, 3, 15])
        result = nudges.generate_nudges()
        assert any("stress" in n for n in result)

    def test_flags_lagging_metric_linked_goal(self, nudges):
        import storage
        storage.save_goals([{
            "name": "Sleep well", "metric": "sleep", "target": 9,
            "direction": "at_least", "window_days": 7,
        }])
        _seed_recent(storage, "sleep", "hours", [4, 4, 4, 4, 4, 4, 4])  # way under target
        result = nudges.generate_nudges()
        assert any("Sleep well" in n for n in result)

    def test_does_not_flag_healthy_goal(self, nudges):
        import storage
        storage.save_goals([{
            "name": "Sleep well", "metric": "sleep", "target": 6,
            "direction": "at_least", "window_days": 7,
        }])
        _seed_recent(storage, "sleep", "hours", [8, 8, 8, 8, 8, 8, 8])  # well above target
        result = nudges.generate_nudges()
        assert not any("Sleep well" in n for n in result)

    def test_respects_max_nudges(self, nudges):
        import storage
        # seed enough anomalies/goals to exceed max_nudges if uncapped
        _seed_recent(storage, "stress", "score", [3, 3, 3, 3, 3, 20])
        _seed_recent(storage, "mood", "score", [8, 8, 8, 8, 8, 1])
        for i in range(5):
            storage.save_goals([
                {"name": f"goal{i}", "metric": "hydration", "target": 10,
                 "direction": "at_least", "window_days": 7}
                for i in range(5)
            ])
        result = nudges.generate_nudges(max_nudges=2)
        assert len(result) <= 2

    def test_manual_goals_never_flagged(self, nudges):
        import storage
        storage.save_goals([{"name": "Read more", "progress": 5}])  # no metric linkage
        result = nudges.generate_nudges()
        assert not any("Read more" in n for n in result)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
