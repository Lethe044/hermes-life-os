"""Tests for opt-in encryption at rest (demo/storage.py + crypto_store.py)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

pytest.importorskip("cryptography")


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    """Reload storage.py with HOME pointed at a temp dir and no
    encryption key set - each test opts in explicitly."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
    for mod in ("storage", "crypto_store"):
        if mod in sys.modules:
            del sys.modules[mod]
    import storage as s
    importlib.reload(s)
    return s


class TestEncryptionOffByDefault:
    def test_plaintext_when_no_key_set(self, storage):
        storage.save_profile({"name": "Alex", "onboarded": True})
        raw = storage.PROFILE_FILE.read_text(encoding="utf-8")
        assert '"name": "Alex"' in raw  # readable plain JSON, not a token

    def test_memory_plaintext_when_no_key_set(self, storage):
        storage.write_memory({"type": "mood", "score": 7})
        raw = storage.MEMORY_FILE.read_text(encoding="utf-8")
        assert '"type": "mood"' in raw


class TestEncryptionOnWhenKeySet:
    def test_saved_file_is_not_plaintext(self, storage, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")
        storage.save_profile({"name": "Alex", "onboarded": True})
        raw = storage.PROFILE_FILE.read_text(encoding="utf-8")
        assert "Alex" not in raw  # not readable as plaintext

    def test_round_trip_with_correct_passphrase(self, storage, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")
        storage.save_profile({"name": "Alex", "onboarded": True})
        assert storage.load_profile() == {"name": "Alex", "onboarded": True}

    def test_memory_lines_are_individually_encrypted(self, storage, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")
        storage.write_memory({"type": "mood", "score": 7})
        storage.write_memory({"type": "sleep", "hours": 6})

        raw_lines = storage.MEMORY_FILE.read_text(encoding="utf-8").strip().splitlines()
        assert len(raw_lines) == 2
        for line in raw_lines:
            assert "mood" not in line and "sleep" not in line  # opaque tokens

        entries = storage.get_recent_memory(days=30)
        assert len(entries) == 2
        assert {e["type"] for e in entries} == {"mood", "sleep"}

    def test_wrong_passphrase_does_not_leak_or_crash(self, storage, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")
        storage.save_profile({"name": "Alex", "onboarded": True})

        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "a totally different passphrase")
        # must not raise, and must not silently return the real data
        result = storage.load_profile()
        assert result != {"name": "Alex", "onboarded": True}

    def test_salt_file_created_per_profile(self, storage, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")
        storage.save_profile({"name": "Alex", "onboarded": True})
        assert (storage.HERMES_DIR / ".salt").exists()

        storage.set_active_profile("jamie")
        storage.save_profile({"name": "Jamie", "onboarded": True})
        assert (storage.HERMES_DIR / ".salt").exists()

        # different profiles get different salts -> different derived keys
        default_salt = (storage.HERMES_ROOT / ".salt").read_bytes()
        jamie_salt = (storage.HERMES_ROOT / "profiles" / "jamie" / ".salt").read_bytes()
        assert default_salt != jamie_salt


class TestBackwardCompatibleMigration:
    """Encryption must not strand pre-existing plaintext data - it should
    read transparently and get encrypted on next write, with no separate
    'migrate' step required."""

    def test_reads_preexisting_plaintext_after_key_is_set(self, storage, monkeypatch):
        # written while encryption is off
        storage.save_profile({"name": "Alex", "onboarded": True})

        # now turn encryption on for subsequent operations
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")
        assert storage.load_profile() == {"name": "Alex", "onboarded": True}

    def test_file_becomes_encrypted_after_next_save(self, storage, monkeypatch):
        storage.save_profile({"name": "Alex", "onboarded": True})

        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")
        storage.save_profile({"name": "Alex", "onboarded": True, "updated": True})

        raw = storage.PROFILE_FILE.read_text(encoding="utf-8")
        assert "Alex" not in raw

    def test_mixed_plaintext_and_encrypted_memory_lines_both_readable(self, storage, monkeypatch):
        storage.write_memory({"type": "mood", "score": 5})  # plaintext line

        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")
        storage.write_memory({"type": "mood", "score": 8})  # encrypted line

        entries = storage.get_recent_memory(days=30)
        assert len(entries) == 2
        assert {e["score"] for e in entries} == {5, 8}
