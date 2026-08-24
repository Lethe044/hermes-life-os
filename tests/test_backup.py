"""Tests for demo/backup.py - rotating local JSON backups."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def backup_module(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "data_export", "backup"):
        if mod in sys.modules:
            del sys.modules[mod]
    import backup as b
    importlib.reload(b)
    b.storage.set_active_profile(None)
    return b


class TestRunBackup:
    def test_creates_backups_dir_and_file(self, backup_module):
        out_path = backup_module.run_backup()
        assert out_path.exists()
        assert out_path.parent == backup_module.backups_dir()

    def test_filename_matches_expected_pattern(self, backup_module):
        out_path = backup_module.run_backup(now=datetime(2026, 3, 4, 20, 30, 5))
        assert out_path.name == "backup-2026-03-04-203005.json"

    def test_content_is_valid_export_json(self, backup_module):
        import storage
        storage.save_profile({"name": "Alex"})

        out_path = backup_module.run_backup()
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert payload["profile"]["name"] == "Alex"
        assert "memory" in payload and "habits" in payload and "goals" in payload

    def test_respects_active_profile(self, backup_module):
        import storage
        storage.set_active_profile("alex")
        out_path = backup_module.run_backup()
        assert "profiles" in str(out_path) and "alex" in str(out_path)


class TestRotateBackups:
    def test_keeps_most_recent_n(self, backup_module, tmp_path):
        directory = tmp_path / "b"
        directory.mkdir()
        names = [
            "backup-2026-01-01-000000.json",
            "backup-2026-01-02-000000.json",
            "backup-2026-01-03-000000.json",
            "backup-2026-01-04-000000.json",
        ]
        for name in names:
            (directory / name).write_text("{}", encoding="utf-8")

        deleted = backup_module.rotate_backups(directory, keep=2)

        remaining = sorted(p.name for p in directory.iterdir())
        assert remaining == names[-2:]
        assert {p.name for p in deleted} == set(names[:2])

    def test_no_op_when_under_the_limit(self, backup_module, tmp_path):
        directory = tmp_path / "b"
        directory.mkdir()
        (directory / "backup-2026-01-01-000000.json").write_text("{}", encoding="utf-8")

        deleted = backup_module.rotate_backups(directory, keep=7)

        assert deleted == []
        assert len(list(directory.iterdir())) == 1

    def test_ignores_non_backup_files(self, backup_module, tmp_path):
        directory = tmp_path / "b"
        directory.mkdir()
        (directory / "notes.txt").write_text("hi", encoding="utf-8")
        (directory / "backup-2026-01-01-000000.json").write_text("{}", encoding="utf-8")

        backup_module.rotate_backups(directory, keep=0)

        remaining = [p.name for p in directory.iterdir()]
        assert remaining == ["notes.txt"]

    def test_rejects_negative_keep(self, backup_module, tmp_path):
        directory = tmp_path / "b"
        directory.mkdir()
        with pytest.raises(ValueError):
            backup_module.rotate_backups(directory, keep=-1)

    def test_missing_dir_returns_empty(self, backup_module, tmp_path):
        directory = tmp_path / "does-not-exist"
        assert backup_module.rotate_backups(directory, keep=5) == []


class TestRunBackupRotatesAutomatically:
    def test_old_backups_pruned_after_repeated_runs(self, backup_module):
        for day in range(1, 5):
            backup_module.run_backup(keep=2, now=datetime(2026, 1, day, 12, 0, 0))

        remaining = sorted(p.name for p in backup_module.backups_dir().iterdir())
        assert len(remaining) == 2
        assert remaining[-1] == "backup-2026-01-04-120000.json"


class TestMainCLI:
    def test_main_writes_backup_for_active_profile(self, backup_module, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["backup.py", "--keep", "3"])
        backup_module.main()
        out = capsys.readouterr().out
        assert "Backup written" in out
        assert len(list(backup_module.backups_dir().glob("backup-*.json"))) == 1

    def test_main_respects_profile_flag(self, backup_module, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["backup.py", "--profile", "alex"])
        backup_module.main()
        import storage
        assert storage.ACTIVE_PROFILE == "alex"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
