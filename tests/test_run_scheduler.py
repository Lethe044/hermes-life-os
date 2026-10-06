"""Tests for demo/run_scheduler.py's make_runner - specifically the
nudge_check special-casing (LLM-free, deterministic)."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def run_scheduler_module(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "budgets", "reminders", "nudges", "backup", "run_scheduler"):
        if mod in sys.modules:
            del sys.modules[mod]
    import run_scheduler as rs
    importlib.reload(rs)
    return rs


class TestMakeRunnerNudgeCheck:
    def test_nudge_check_returns_empty_string_when_nothing_notable(self, run_scheduler_module):
        runner = run_scheduler_module.make_runner(client=None, model="unused")
        assert runner("nudge_check") == ""

    def test_nudge_check_never_touches_the_llm_client(self, run_scheduler_module):
        """Passing an obviously-broken 'client' must not matter for
        nudge_check - it's LLM-free by design."""
        runner = run_scheduler_module.make_runner(client="not-a-real-client", model="unused")
        result = runner("nudge_check")  # must not raise
        assert isinstance(result, str)

    def test_nudge_check_surfaces_real_anomalies(self, run_scheduler_module):
        import storage
        now = datetime.now(timezone.utc)
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            for i in range(2, 7):
                ts = (now - timedelta(days=i)).strftime("%Y-%m-%dT09:00:00Z")
                f.write(json.dumps({"type": "stress", "score": 3, "timestamp": ts}) + "\n")
            f.write(json.dumps({
                "type": "stress", "score": 18,
                "timestamp": now.strftime("%Y-%m-%dT09:00:00Z"),
            }) + "\n")

        runner = run_scheduler_module.make_runner(client=None, model="unused")
        result = runner("nudge_check")
        assert "stress" in result


class TestMakeRunnerBackup:
    def test_backup_returns_empty_string_on_success(self, run_scheduler_module):
        """Silent on success - empty string means 'don't notify'."""
        runner = run_scheduler_module.make_runner(client=None, model="unused")
        assert runner("backup") == ""

    def test_backup_never_touches_the_llm_client(self, run_scheduler_module):
        runner = run_scheduler_module.make_runner(client="not-a-real-client", model="unused")
        result = runner("backup")  # must not raise
        assert isinstance(result, str)

    def test_backup_actually_writes_a_file(self, run_scheduler_module):
        import storage
        runner = run_scheduler_module.make_runner(client=None, model="unused")
        runner("backup")
        backups = list((storage.HERMES_DIR / "backups").glob("backup-*.json"))
        assert len(backups) == 1

    def test_backup_failure_is_surfaced_not_swallowed(self, run_scheduler_module, monkeypatch):
        """If run_backup() blows up, the runner must report it (so it
        reaches the notifier) instead of raising or going silent."""
        import backup as backup_module

        def boom(**kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(backup_module, "run_backup", boom)
        runner = run_scheduler_module.make_runner(client=None, model="unused")
        result = runner("backup")
        assert "Backup failed" in result
        assert "disk full" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestBuildDynamicSource:
    def test_returns_reminders_scheduler_source(self, run_scheduler_module):
        import reminders
        assert run_scheduler_module.build_dynamic_source() is reminders.scheduler_source

    def test_delivers_due_reminder_through_scheduler(self, run_scheduler_module):
        import reminders
        from scheduler import run_scheduler
        reminders.create_reminder("drink water", "14:00")
        notified = []
        run_scheduler(
            schedule=[], notifier=lambda t, m: notified.append((t, m)),
            max_iterations=1, clock=lambda: datetime(2026, 10, 5, 14, 0),
            sleeper=lambda s: None,
            dynamic_source=run_scheduler_module.build_dynamic_source(),
        )
        assert notified == [("Hermes Life OS - Reminder", "drink water")]


class TestMakeRunnerBudgetNudge:
    def test_nudge_check_surfaces_over_budget(self, run_scheduler_module):
        import storage
        storage.save_budgets([{"category": "food", "limit": 10}])
        storage.save_spending([{"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                                "category": "food", "amount": 50}])
        runner = run_scheduler_module.make_runner(client=None, model="unused")
        assert "food" in runner("nudge_check")
