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
        assert summary == {"config_files": 0, "memory_lines": 0}


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
