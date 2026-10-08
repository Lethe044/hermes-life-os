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


def _legacy_backup(directory, name="backup-2026-09-01-000000.json"):
    """A format-1 backup: nine stores, no _meta."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = {k: [] for k in ("habits", "goals", "nutrition", "sleep", "fitness", "focus", "mental")}
    payload.update({"profile": {}, "hydration": {}, "memory": [{"id": "a"}, {"id": "b"}]})
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestRunBackupKeepClamp:
    def test_keep_zero_still_keeps_the_new_backup(self, backup_module):
        out = backup_module.run_backup(keep=0)
        assert out.exists()
        assert backup_module.list_backups() == [out]

    def test_negative_keep_does_not_raise_or_delete(self, backup_module):
        out = backup_module.run_backup(keep=-5)
        assert out.exists()

    def test_keep_zero_keeps_exactly_one_of_several(self, backup_module):
        for day in (1, 2, 3):
            backup_module.run_backup(keep=7, now=datetime(2026, 1, day, 12, 0, 0))
        newest = backup_module.run_backup(keep=0, now=datetime(2026, 1, 4, 12, 0, 0))
        assert backup_module.list_backups() == [newest]


class TestBackupContents:
    def test_backup_contains_every_store(self, backup_module):
        out = backup_module.run_backup()
        payload = json.loads(out.read_text(encoding="utf-8"))
        for name in backup_module.storage.data_store_names():
            assert name in payload, name
        assert payload["_meta"]["format_version"] == 2

    def test_backup_contains_spending_budgets_and_reminders(self, backup_module):
        storage = backup_module.storage
        storage.save_spending([{"amount": 3}])
        storage.save_budgets([{"category": "food", "limit": 10}])
        storage.save_reminders([{"id": "r", "text": "x"}])
        payload = json.loads(backup_module.run_backup().read_text(encoding="utf-8"))
        assert payload["spending"] == [{"amount": 3}]
        assert payload["budgets"] == [{"category": "food", "limit": 10}]
        assert payload["reminders"] == [{"id": "r", "text": "x"}]


class TestListAndLatest:
    def test_empty(self, backup_module):
        assert backup_module.list_backups() == []
        assert backup_module.latest_backup() is None

    def test_newest_first(self, backup_module):
        a = backup_module.run_backup(now=datetime(2026, 1, 1, 12, 0, 0))
        b = backup_module.run_backup(now=datetime(2026, 1, 2, 12, 0, 0))
        assert backup_module.list_backups() == [b, a]
        assert backup_module.latest_backup() == b

    def test_ignores_unrelated_files(self, backup_module):
        out = backup_module.run_backup()
        (backup_module.backups_dir() / "notes.txt").write_text("hi", encoding="utf-8")
        (backup_module.backups_dir() / "pre-restore-2026-01-01-000000.json").write_text("{}", encoding="utf-8")
        assert backup_module.list_backups() == [out]


class TestDescribeBackup:
    def test_full_backup(self, backup_module):
        backup_module.storage.write_memory({"type": "t"})
        out = backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        info = backup_module.describe_backup(out)
        assert info["readable"] is True
        assert info["name"] == "backup-2026-10-01-203000.json"
        assert info["created"] == datetime(2026, 10, 1, 20, 30, 0)
        assert info["format_version"] == 2
        assert info["stores"]["memory"] == 1
        assert info["missing_stores"] == []
        assert info["size_bytes"] > 0

    def test_legacy_backup_reports_missing_stores(self, backup_module):
        path = _legacy_backup(backup_module.backups_dir())
        info = backup_module.describe_backup(path)
        assert info["readable"] is True
        assert info["format_version"] == 1
        assert {"spending", "budgets", "reminders", "templates"} <= set(info["missing_stores"])
        assert "habits" not in info["missing_stores"]
        assert info["stores"]["memory"] == 2

    def test_corrupt_file_is_unreadable_not_an_error(self, backup_module):
        d = backup_module.backups_dir()
        d.mkdir(parents=True)
        path = d / "backup-2026-10-01-000000.json"
        path.write_text("not json at all", encoding="utf-8")
        info = backup_module.describe_backup(path)
        assert info["readable"] is False
        assert info["stores"] == {}

    def test_json_list_is_unreadable(self, backup_module):
        d = backup_module.backups_dir()
        d.mkdir(parents=True)
        path = d / "backup-2026-10-01-000000.json"
        path.write_text("[1, 2]", encoding="utf-8")
        assert backup_module.describe_backup(path)["readable"] is False

    def test_missing_file(self, backup_module):
        info = backup_module.describe_backup(backup_module.backups_dir() / "backup-2026-10-01-000000.json")
        assert info["readable"] is False
        assert info["size_bytes"] == 0

    def test_non_standard_filename_has_no_created(self, backup_module, tmp_path):
        path = tmp_path / "custom.json"
        path.write_text("{}", encoding="utf-8")
        assert backup_module.describe_backup(path)["created"] is None


class TestFormatBackupStatus:
    def test_no_backups(self, backup_module):
        out = backup_module.format_backup_status()
        assert "No backups yet" in out
        assert "backup_now" in out

    def test_recent_backup_wording(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        out = backup_module.format_backup_status(now=datetime(2026, 10, 1, 20, 45, 0))
        assert "1 backup(s) saved" in out
        assert "less than an hour ago" in out
        assert "backup-2026-10-01-203000.json" in out
        assert "predates" not in out

    def test_hours_wording(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        out = backup_module.format_backup_status(now=datetime(2026, 10, 1, 23, 0, 0))
        assert "2 hour(s) ago" in out

    def test_days_wording(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        out = backup_module.format_backup_status(now=datetime(2026, 10, 5, 21, 0, 0))
        assert "4 day(s) ago" in out

    def test_counts_all_backups_and_reports_newest(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        backup_module.run_backup(now=datetime(2026, 10, 2, 20, 30, 0))
        out = backup_module.format_backup_status(now=datetime(2026, 10, 2, 21, 0, 0))
        assert "2 backup(s) saved" in out
        assert "Newest: backup-2026-10-02-203000.json" in out

    def test_reports_memory_entries_and_sections(self, backup_module):
        backup_module.storage.write_memory({"type": "t"})
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        out = backup_module.format_backup_status(now=datetime(2026, 10, 1, 21, 0, 0))
        assert "holds 1 memory entries across 19 data sections" in out

    def test_legacy_newest_backup_is_flagged_incomplete(self, backup_module):
        _legacy_backup(backup_module.backups_dir())
        out = backup_module.format_backup_status(now=datetime(2026, 9, 2, 0, 0, 0))
        assert "predates complete backups" in out
        assert "spending" in out

    def test_corrupt_newest_backup_warns(self, backup_module):
        d = backup_module.backups_dir()
        d.mkdir(parents=True)
        (d / "backup-2026-10-01-000000.json").write_text("garbage", encoding="utf-8")
        out = backup_module.format_backup_status(now=datetime(2026, 10, 1, 1, 0, 0))
        assert "could not be read" in out

    def test_mentions_how_to_restore(self, backup_module):
        backup_module.run_backup()
        assert "hermes-life-os-restore" in backup_module.format_backup_status()

    def test_filename_with_impossible_date_does_not_crash(self, backup_module):
        """The name matches the backup pattern but is not a real date, so
        its age cannot be computed - status must still render."""
        d = backup_module.backups_dir()
        d.mkdir(parents=True)
        (d / "backup-2026-13-45-999999.json").write_text("{}", encoding="utf-8")
        out = backup_module.format_backup_status()
        assert "Newest: backup-2026-13-45-999999.json (0.0 KB)." in out


class TestEncryptedBackups:
    @pytest.fixture(autouse=True)
    def _needs_crypto(self):
        pytest.importorskip("cryptography")

    def test_backup_without_key_is_plain_json(self, backup_module, monkeypatch):
        monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
        out = backup_module.run_backup()
        assert isinstance(json.loads(out.read_text(encoding="utf-8")), dict)
        assert backup_module.describe_backup(out)["encrypted"] is False

    def test_backup_with_key_is_encrypted_on_disk(self, backup_module, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        backup_module.storage.save_habits([{"name": "very-private-habit"}])
        out = backup_module.run_backup()
        raw = out.read_text(encoding="utf-8")
        assert "very-private-habit" not in raw
        with pytest.raises(ValueError):
            json.loads(raw)

    def test_encrypted_backup_is_readable_with_the_key(self, backup_module, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        backup_module.storage.write_memory({"type": "t"})
        out = backup_module.run_backup()
        info = backup_module.describe_backup(out)
        assert info["readable"] is True and info["encrypted"] is True
        assert info["stores"]["memory"] == 1
        assert backup_module.read_backup_payload(out)["_meta"]["format_version"] == 2

    def test_wrong_key_makes_it_unreadable_not_an_error(self, backup_module, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "right")
        out = backup_module.run_backup()
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "wrong")
        info = backup_module.describe_backup(out)
        assert info["readable"] is False
        assert backup_module.read_backup_payload(out) is None

    def test_no_key_makes_encrypted_backup_unreadable(self, backup_module, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        out = backup_module.run_backup()
        monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY")
        assert backup_module.describe_backup(out)["readable"] is False

    def test_plaintext_backup_stays_readable_after_enabling_a_key(self, backup_module, monkeypatch):
        monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
        out = backup_module.run_backup(now=datetime(2026, 1, 1, 12, 0, 0))
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        info = backup_module.describe_backup(out)
        assert info["readable"] is True and info["encrypted"] is False

    def test_status_mentions_encryption(self, backup_module, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        out = backup_module.format_backup_status(now=datetime(2026, 10, 1, 21, 0, 0))
        assert "encrypted with your LIFE_OS_ENCRYPTION_KEY" in out

    def test_status_with_wrong_key_points_at_the_passphrase(self, backup_module, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "right")
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "wrong")
        out = backup_module.format_backup_status(now=datetime(2026, 10, 1, 21, 0, 0))
        assert "different passphrase" in out

    def test_plaintext_status_has_no_encryption_line(self, backup_module, monkeypatch):
        monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        out = backup_module.format_backup_status(now=datetime(2026, 10, 1, 21, 0, 0))
        assert "encrypted with" not in out


class TestBackupAlert:
    def test_no_backups_means_no_alert(self, backup_module):
        assert backup_module.backup_alert(now=datetime(2026, 10, 10)) is None

    def test_fresh_backup_means_no_alert(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 9, 20, 30, 0))
        assert backup_module.backup_alert(now=datetime(2026, 10, 10, 12, 0, 0)) is None

    def test_just_under_the_limit_means_no_alert(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        assert backup_module.backup_alert(now=datetime(2026, 10, 4, 20, 29, 0)) is None

    def test_stale_backup_alerts_with_age(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        msg = backup_module.backup_alert(now=datetime(2026, 10, 6, 21, 0, 0))
        assert "5 days old" in msg
        assert "backup_now" in msg

    def test_exactly_at_the_limit_alerts(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        assert backup_module.backup_alert(now=datetime(2026, 10, 4, 20, 30, 0)) is not None

    def test_custom_stale_days(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        now = datetime(2026, 10, 6, 21, 0, 0)
        assert backup_module.backup_alert(now=now, stale_days=10) is None
        assert backup_module.backup_alert(now=now, stale_days=1) is not None

    def test_only_the_newest_backup_counts(self, backup_module):
        backup_module.run_backup(now=datetime(2026, 9, 1, 20, 30, 0))
        backup_module.run_backup(now=datetime(2026, 10, 9, 20, 30, 0))
        assert backup_module.backup_alert(now=datetime(2026, 10, 10)) is None

    def test_unreadable_newest_backup_alerts(self, backup_module):
        d = backup_module.backups_dir()
        d.mkdir(parents=True)
        (d / "backup-2026-10-09-000000.json").write_text("garbage", encoding="utf-8")
        msg = backup_module.backup_alert(now=datetime(2026, 10, 9, 1, 0, 0))
        assert "could not be read" in msg

    def test_backup_with_impossible_date_in_name_does_not_crash(self, backup_module):
        d = backup_module.backups_dir()
        d.mkdir(parents=True)
        (d / "backup-2026-13-45-999999.json").write_text("{}", encoding="utf-8")
        assert backup_module.backup_alert() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
