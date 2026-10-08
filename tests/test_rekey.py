"""Tests for demo/rekey.py - encryption passphrase rotation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

pytest.importorskip("cryptography")


@pytest.fixture()
def rekey_module(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
    for mod in ("storage", "crypto_store", "rekey"):
        if mod in sys.modules:
            del sys.modules[mod]
    import rekey as rk
    importlib.reload(rk)
    rk.storage.set_active_profile(None)
    return rk


class TestRekeyChangePassphrase:
    def test_round_trip_readable_with_new_key_after_rekey(self, rekey_module):
        storage = rekey_module.storage
        import os
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "old-passphrase"
        storage.save_profile({"name": "Alex", "onboarded": True})
        storage.write_memory({"type": "mood", "score": 7})
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        summary = rekey_module.rekey("old-passphrase", "new-passphrase")
        assert summary["config_files"] >= 1
        assert summary["memory_lines"] >= 1

        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "new-passphrase"
        assert storage.load_profile()["name"] == "Alex"
        entries = storage.get_all_memory()
        assert any(e.get("type") == "mood" for e in entries)
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

    def test_old_key_no_longer_decrypts_after_rekey(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "old-passphrase"
        storage.save_profile({"name": "Alex"})
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        rekey_module.rekey("old-passphrase", "new-passphrase")

        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "old-passphrase"
        # storage._load() silently falls back to defaults on a decrypt
        # failure - so this should NOT come back as "Alex" anymore.
        result = storage.load_profile()
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]
        assert result.get("name") != "Alex"

    def test_wrong_old_passphrase_raises_before_writing_anything(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "correct-old-key"
        storage.save_profile({"name": "Alex"})
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        original_raw = storage.PROFILE_FILE.read_text(encoding="utf-8")

        with pytest.raises(rekey_module.RekeyError):
            rekey_module.rekey("totally-wrong-key", "new-passphrase")

        # File must be untouched - decrypt-all-first-then-write means a
        # failure never leaves a partially re-keyed profile.
        assert storage.PROFILE_FILE.read_text(encoding="utf-8") == original_raw

    def test_mixed_plaintext_and_encrypted_history_tolerated(self, rekey_module):
        """Encryption is opt-in and can be turned on mid-usage, so a
        profile can legitimately have some plaintext entries (written
        before the key was set) alongside encrypted ones. Re-keying
        must handle that mix, not treat it as a wrong passphrase."""
        import os
        storage = rekey_module.storage

        # First entry written before encryption was ever turned on.
        storage.write_memory({"type": "mood", "score": 5, "note": "plaintext-era"})

        # Second entry written after LIFE_OS_ENCRYPTION_KEY was set.
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "old-passphrase"
        storage.write_memory({"type": "mood", "score": 9, "note": "encrypted-era"})
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        summary = rekey_module.rekey("old-passphrase", "new-passphrase")
        assert summary["memory_lines"] == 2

        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "new-passphrase"
        notes = {e.get("note") for e in storage.get_all_memory()}
        assert notes == {"plaintext-era", "encrypted-era"}
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

    def test_genuinely_corrupt_line_still_raises(self, rekey_module):
        """A line that's neither decryptable nor valid JSON (e.g.
        ciphertext under a truly wrong key) must still raise - the
        mixed-plaintext tolerance above shouldn't paper over real
        wrong-passphrase cases."""
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "the-real-old-key"
        storage.write_memory({"type": "mood", "score": 5})
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        with pytest.raises(rekey_module.RekeyError):
            rekey_module.rekey("a-completely-different-key", "new-passphrase")

    def test_salt_file_is_rotated(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "old-passphrase"
        storage.save_profile({"name": "Alex"})
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        import crypto_store
        salt_path = storage.HERMES_DIR / crypto_store.SALT_FILE_NAME
        old_salt = salt_path.read_bytes()

        rekey_module.rekey("old-passphrase", "new-passphrase")

        new_salt = salt_path.read_bytes()
        assert new_salt != old_salt


class TestRekeyEnableEncryption:
    def test_plaintext_to_encrypted(self, rekey_module):
        storage = rekey_module.storage
        storage.save_profile({"name": "Alex"})  # no key set - plaintext
        raw_before = storage.PROFILE_FILE.read_text(encoding="utf-8")
        assert "Alex" in raw_before

        rekey_module.rekey(None, "brand-new-passphrase")

        raw_after = storage.PROFILE_FILE.read_text(encoding="utf-8")
        assert "Alex" not in raw_after  # now encrypted, unreadable as plaintext

        import os
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "brand-new-passphrase"
        assert storage.load_profile()["name"] == "Alex"
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]


class TestRekeyDisableEncryption:
    def test_encrypted_to_plaintext(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "old-passphrase"
        storage.save_profile({"name": "Alex"})
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        rekey_module.rekey("old-passphrase", None)

        raw_after = storage.PROFILE_FILE.read_text(encoding="utf-8")
        assert '"name": "Alex"' in raw_after  # plain, readable JSON again

    def test_salt_file_removed_when_disabling(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "old-passphrase"
        storage.save_profile({"name": "Alex"})
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        import crypto_store
        salt_path = storage.HERMES_DIR / crypto_store.SALT_FILE_NAME
        assert salt_path.exists()

        rekey_module.rekey("old-passphrase", None)
        assert not salt_path.exists()


class TestRekeyEmptyProfile:
    def test_no_files_yet_returns_zero_counts(self, rekey_module):
        summary = rekey_module.rekey(None, "some-passphrase")
        assert summary == {"config_files": 0, "memory_lines": 0,
                           "backup_files": 0, "backups_skipped": 0}


class TestMainCLI:
    def test_disable_and_new_key_are_mutually_exclusive(self, rekey_module, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["rekey.py", "--new-key", "x", "--disable"])
        with pytest.raises(SystemExit):
            rekey_module.main()

    def test_confirmation_prompt_cancel_makes_no_changes(self, rekey_module, monkeypatch, capsys):
        storage = rekey_module.storage
        storage.save_profile({"name": "Alex"})
        raw_before = storage.PROFILE_FILE.read_text(encoding="utf-8")

        monkeypatch.setattr(sys, "argv", ["rekey.py", "--new-key", "new-pass"])
        monkeypatch.setattr("builtins.input", lambda prompt: "n")
        rekey_module.main()

        assert storage.PROFILE_FILE.read_text(encoding="utf-8") == raw_before
        assert "Cancelled" in capsys.readouterr().out

    def test_yes_flag_skips_confirmation(self, rekey_module, monkeypatch, capsys):
        storage = rekey_module.storage
        storage.save_profile({"name": "Alex"})

        monkeypatch.setattr(sys, "argv", ["rekey.py", "--new-key", "new-pass", "--yes"])
        monkeypatch.setattr("builtins.input",
                            lambda prompt: (_ for _ in ()).throw(AssertionError("should not prompt")))
        rekey_module.main()

        out = capsys.readouterr().out
        assert "Done" in out

    def test_old_key_defaults_to_env_var(self, rekey_module, monkeypatch, capsys):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "env-old-key"
        storage.save_profile({"name": "Alex"})

        monkeypatch.setattr(sys, "argv", ["rekey.py", "--new-key", "new-pass", "--yes"])
        rekey_module.main()
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        out = capsys.readouterr().out
        assert "Done" in out
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "new-pass"
        assert storage.load_profile()["name"] == "Alex"
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]


def _seed_every_store(storage):
    """Writes a distinct, valid value into every registered store."""
    seeded = {}
    for name in storage.data_store_names():
        expected = storage.DATA_STORES[name][3]
        value = {"marker": name} if expected is dict else [{"marker": name}]
        storage.save_store(name, value)
        seeded[name] = value
    return seeded


class TestRekeyCoversEveryStore:
    """Regression: rekey used to re-encrypt only 9 hard-coded files. The
    others stayed on the old key, and once the salt rotated they read back
    as empty - silent, unrecoverable data loss."""

    def test_config_file_attrs_match_registry(self, rekey_module):
        storage = rekey_module.storage
        assert sorted(rekey_module.CONFIG_FILE_ATTRS) == sorted(e[0] for e in storage.DATA_STORES.values())

    def test_every_store_survives_a_passphrase_change(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "old-passphrase"
        seeded = _seed_every_store(storage)
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        summary = rekey_module.rekey("old-passphrase", "new-passphrase")
        assert summary["config_files"] == len(seeded)

        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "new-passphrase"
        try:
            for name, value in seeded.items():
                assert storage.load_store(name) == value, name
        finally:
            del os.environ["LIFE_OS_ENCRYPTION_KEY"]

    def test_spending_and_reminders_specifically_survive(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "a"
        storage.save_spending([{"amount": 42, "category": "food", "date": "2026-10-01"}])
        storage.save_reminders([{"id": "r1", "text": "stretch"}])
        storage.save_budgets([{"category": "food", "limit": 100}])
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        rekey_module.rekey("a", "b")

        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "b"
        try:
            assert storage.load_spending()[0]["amount"] == 42
            assert storage.load_reminders()[0]["text"] == "stretch"
            assert storage.load_budgets()[0]["limit"] == 100
        finally:
            del os.environ["LIFE_OS_ENCRYPTION_KEY"]

    def test_plaintext_to_encrypted_encrypts_every_store(self, rekey_module):
        import json
        storage = rekey_module.storage
        _seed_every_store(storage)
        rekey_module.rekey(None, "new-passphrase")
        for name in storage.data_store_names():
            raw = storage.data_store_path(name).read_text(encoding="utf-8")
            with pytest.raises(ValueError):
                json.loads(raw)  # ciphertext, not plaintext JSON
            assert "marker" not in raw  # plaintext content is not visible

    def test_encrypted_to_plaintext_decrypts_every_store(self, rekey_module):
        import json
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "pw"
        seeded = _seed_every_store(storage)
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        rekey_module.rekey("pw", None)

        for name, value in seeded.items():
            raw = storage.data_store_path(name).read_text(encoding="utf-8")
            assert json.loads(raw) == value, name

    def test_summary_counts_only_files_that_exist(self, rekey_module):
        storage = rekey_module.storage
        storage.save_spending([{"amount": 1}])
        storage.save_reminders([{"id": "r"}])
        summary = rekey_module.rekey(None, "pw")
        assert summary["config_files"] == 2

    def test_wrong_old_key_still_fails_before_writing_for_new_stores(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "right"
        storage.save_spending([{"amount": 9}])
        path = storage.data_store_path("spending")
        before = path.read_text(encoding="utf-8")
        del os.environ["LIFE_OS_ENCRYPTION_KEY"]

        with pytest.raises(rekey_module.RekeyError):
            rekey_module.rekey("wrong", "new")
        assert path.read_text(encoding="utf-8") == before


class TestRekeyCoversBackups:
    """Backups are written encrypted under the active key. Without rekey
    handling them, a passphrase change would strand them for good."""

    def _backup(self, rekey_module, key, name="backup-2026-10-01-203000.json"):
        import os
        import data_export
        storage = rekey_module.storage
        directory = storage.HERMES_DIR / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        if key:
            os.environ["LIFE_OS_ENCRYPTION_KEY"] = key
        try:
            storage.save_habits([{"name": "habit-in-backup"}])
            importlib.reload(data_export)
            data_export.export_json(str(directory / name), encrypt=True)
        finally:
            os.environ.pop("LIFE_OS_ENCRYPTION_KEY", None)
        return directory / name

    def _readable_with(self, rekey_module, path, key):
        import json
        import os
        storage = rekey_module.storage
        if key:
            os.environ["LIFE_OS_ENCRYPTION_KEY"] = key
        try:
            raw = path.read_text(encoding="utf-8")
            try:
                return json.loads(raw)
            except ValueError:
                decrypted = storage.decrypt_text(raw)
                return json.loads(decrypted) if decrypted != raw else None
        finally:
            os.environ.pop("LIFE_OS_ENCRYPTION_KEY", None)

    def test_encrypted_backup_follows_a_passphrase_change(self, rekey_module):
        path = self._backup(rekey_module, "old")
        summary = rekey_module.rekey("old", "new")
        assert summary["backup_files"] == 1
        assert self._readable_with(rekey_module, path, "new")["habits"] == [{"name": "habit-in-backup"}]
        assert self._readable_with(rekey_module, path, "old") is None

    def test_plaintext_backup_is_encrypted_when_encryption_is_enabled(self, rekey_module):
        path = self._backup(rekey_module, None)
        assert "habit-in-backup" in path.read_text(encoding="utf-8")
        rekey_module.rekey(None, "new")
        assert "habit-in-backup" not in path.read_text(encoding="utf-8")
        assert self._readable_with(rekey_module, path, "new")["habits"] == [{"name": "habit-in-backup"}]

    def test_backups_are_decrypted_when_encryption_is_disabled(self, rekey_module):
        import json
        path = self._backup(rekey_module, "old")
        rekey_module.rekey("old", None)
        assert json.loads(path.read_text(encoding="utf-8"))["habits"] == [{"name": "habit-in-backup"}]

    def test_restore_safety_copies_are_included(self, rekey_module):
        path = self._backup(rekey_module, "old", name="pre-restore-2026-10-01-203000.json")
        summary = rekey_module.rekey("old", "new")
        assert summary["backup_files"] == 1
        assert self._readable_with(rekey_module, path, "new") is not None

    def test_corrupt_backup_is_skipped_and_does_not_block(self, rekey_module):
        good = self._backup(rekey_module, "old")
        bad = good.parent / "backup-2026-09-01-000000.json"
        bad.write_text("not json and not a token", encoding="utf-8")
        summary = rekey_module.rekey("old", "new")
        assert summary["backup_files"] == 1
        assert summary["backups_skipped"] == 1
        assert bad.read_text(encoding="utf-8") == "not json and not a token"
        assert self._readable_with(rekey_module, good, "new") is not None

    def test_unrelated_files_in_backups_dir_are_untouched(self, rekey_module):
        path = self._backup(rekey_module, "old")
        notes = path.parent / "notes.txt"
        notes.write_text("keep me", encoding="utf-8")
        rekey_module.rekey("old", "new")
        assert notes.read_text(encoding="utf-8") == "keep me"

    def test_no_backups_dir_is_fine(self, rekey_module):
        assert rekey_module.rekey(None, "pw")["backup_files"] == 0

    def test_wrong_old_key_skips_backups_but_still_fails_on_configs(self, rekey_module):
        import os
        storage = rekey_module.storage
        os.environ["LIFE_OS_ENCRYPTION_KEY"] = "right"
        storage.save_profile({"name": "Alex"})
        path = self._backup(rekey_module, "right")
        before = path.read_text(encoding="utf-8")
        os.environ.pop("LIFE_OS_ENCRYPTION_KEY", None)
        with pytest.raises(rekey_module.RekeyError):
            rekey_module.rekey("wrong", "new")
        assert path.read_text(encoding="utf-8") == before

    def test_cli_reports_backup_count(self, rekey_module, monkeypatch, capsys):
        self._backup(rekey_module, None)
        monkeypatch.setattr(sys, "argv", ["rekey.py", "--new-key", "pw", "--yes"])
        rekey_module.main()
        assert "1 backup file(s)" in capsys.readouterr().out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
