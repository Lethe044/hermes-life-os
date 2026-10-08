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
    for mod in ("storage", "analytics", "budgets", "data_export", "backup", "nudges"):
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


class TestBudgetNudges:
    def _spend(self, storage, category, amount):
        from datetime import datetime
        storage.save_spending([{"date": datetime.utcnow().strftime("%Y-%m-%d"),
                                "category": category, "amount": amount}])

    def test_over_budget_nudge(self, nudges):
        import storage
        storage.save_budgets([{"category": "food", "limit": 100}])
        self._spend(storage, "food", 150)
        result = nudges.generate_nudges()
        assert any("food" in n and "over" in n for n in result)

    def test_nearly_used_budget_nudge(self, nudges):
        import storage
        storage.save_budgets([{"category": "food", "limit": 100}])
        self._spend(storage, "food", 90)
        assert any("90.0% used" in n for n in nudges.generate_nudges())

    def test_comfortable_budget_no_nudge(self, nudges):
        import storage
        storage.save_budgets([{"category": "food", "limit": 100}])
        self._spend(storage, "food", 10)
        assert not any("food" in n for n in nudges.generate_nudges())

    def test_no_budgets_no_budget_nudge(self, nudges):
        assert nudges.generate_nudges() == []

    def test_budget_nudges_capped(self, nudges):
        import storage
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cats = ["a", "b", "c", "d"]
        storage.save_budgets([{"category": c, "limit": 10} for c in cats])
        storage.save_spending([{"date": today, "category": c, "amount": 50} for c in cats])
        result = nudges.generate_nudges(max_nudges=10)
        assert sum(1 for n in result if n.startswith("Budget ")) == nudges.MAX_BUDGET_NUDGES


class TestBudgetNudgeThresholds:
    def _spend(self, storage, category, amount):
        from datetime import datetime
        storage.save_spending([{"date": datetime.utcnow().strftime("%Y-%m-%d"),
                                "category": category, "amount": amount}])

    def test_custom_threshold_triggers_a_nudge_the_default_would_not(self, nudges):
        import storage
        storage.save_budgets([{"category": "food", "limit": 100, "alert_pct": 50}])
        self._spend(storage, "food", 60)
        assert any("60.0% used" in n for n in nudges.generate_nudges())

    def test_custom_high_threshold_silences_the_default_nudge(self, nudges):
        import storage
        storage.save_budgets([{"category": "food", "limit": 100, "alert_pct": 95}])
        self._spend(storage, "food", 85)
        assert not any("food" in n for n in nudges.generate_nudges())


class TestBackupNudge:
    def _backup(self, nudges_module, when):
        import backup
        return backup.run_backup(now=when)

    def test_no_backup_no_nudge(self, nudges):
        assert not any("backup" in n.lower() for n in nudges.generate_nudges())

    def test_stale_backup_nudges(self, nudges):
        self._backup(nudges, datetime.now() - timedelta(days=10))
        result = nudges.generate_nudges()
        assert any("10 days old" in n for n in result)

    def test_fresh_backup_no_nudge(self, nudges):
        self._backup(nudges, datetime.now() - timedelta(hours=2))
        assert not any("backup" in n.lower() for n in nudges.generate_nudges())

    def test_unreadable_backup_nudges(self, nudges):
        import backup
        d = backup.backups_dir()
        d.mkdir(parents=True)
        (d / ("backup-" + datetime.now().strftime("%Y-%m-%d-%H%M%S") + ".json")).write_text("junk", encoding="utf-8")
        assert any("could not be read" in n for n in nudges.generate_nudges())

    def test_stale_backup_nudge_respects_max_nudges(self, nudges):
        self._backup(nudges, datetime.now() - timedelta(days=10))
        assert len(nudges.generate_nudges(max_nudges=1)) <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
