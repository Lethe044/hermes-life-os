"""Tests for editing/deleting individual memory.jsonl entries by id."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
    for mod in ("storage", "crypto_store"):
        if mod in sys.modules:
            del sys.modules[mod]
    import storage as s
    importlib.reload(s)
    return s


class TestEveryEntryGetsAnId:
    def test_write_memory_assigns_id(self, storage):
        storage.write_memory({"type": "mood", "score": 7})
        entries = storage.get_recent_memory(days=1)
        assert len(entries) == 1
        assert "id" in entries[0]
        assert len(entries[0]["id"]) == 8

    def test_ids_are_unique(self, storage):
        for _ in range(5):
            storage.write_memory({"type": "mood", "score": 5})
        entries = storage.get_recent_memory(days=1)
        ids = [e["id"] for e in entries]
        assert len(set(ids)) == 5

    def test_explicit_id_is_preserved_not_overwritten(self, storage):
        storage.write_memory({"type": "mood", "score": 7, "id": "custom01"})
        entries = storage.get_recent_memory(days=1)
        assert entries[0]["id"] == "custom01"


class TestDeleteMemoryEntry:
    def test_delete_existing_entry(self, storage):
        storage.write_memory({"type": "mood", "score": 4})
        storage.write_memory({"type": "mood", "score": 9})
        entries = storage.get_recent_memory(days=1)
        target_id = entries[0]["id"]

        assert storage.delete_memory_entry(target_id) is True
        remaining = storage.get_recent_memory(days=1)
        assert len(remaining) == 1
        assert all(e["id"] != target_id for e in remaining)

    def test_delete_nonexistent_entry_returns_false(self, storage):
        storage.write_memory({"type": "mood", "score": 4})
        assert storage.delete_memory_entry("doesnotexist") is False
        assert storage.memory_count() == 1

    def test_delete_only_removes_the_matching_entry(self, storage):
        storage.write_memory({"type": "mood", "score": 1, "id": "aaa"})
        storage.write_memory({"type": "mood", "score": 2, "id": "bbb"})
        storage.write_memory({"type": "mood", "score": 3, "id": "ccc"})

        storage.delete_memory_entry("bbb")
        remaining_ids = {e["id"] for e in storage.get_recent_memory(days=1)}
        assert remaining_ids == {"aaa", "ccc"}


class TestEditMemoryEntry:
    def test_edit_existing_entry(self, storage):
        storage.write_memory({"type": "mood", "score": 4, "id": "xyz"})
        assert storage.edit_memory_entry("xyz", {"score": 9}) is True

        entries = storage.get_recent_memory(days=1)
        assert entries[0]["score"] == 9
        assert entries[0]["id"] == "xyz"  # id unchanged

    def test_edit_preserves_original_timestamp_unless_overridden(self, storage):
        storage.write_memory({"type": "mood", "score": 4, "id": "xyz"})
        original_ts = storage.get_recent_memory(days=1)[0]["timestamp"]

        storage.edit_memory_entry("xyz", {"score": 9})
        assert storage.get_recent_memory(days=1)[0]["timestamp"] == original_ts

    def test_edit_nonexistent_entry_returns_false(self, storage):
        storage.write_memory({"type": "mood", "score": 4})
        assert storage.edit_memory_entry("doesnotexist", {"score": 9}) is False

    def test_edit_only_touches_the_matching_entry(self, storage):
        storage.write_memory({"type": "mood", "score": 1, "id": "aaa"})
        storage.write_memory({"type": "mood", "score": 2, "id": "bbb"})

        storage.edit_memory_entry("aaa", {"score": 100})
        scores = {e["id"]: e["score"] for e in storage.get_recent_memory(days=1)}
        assert scores == {"aaa": 100, "bbb": 2}


class TestEditDeleteUnderEncryption:
    def test_edit_and_delete_work_when_encrypted(self, storage, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "correct horse battery staple")

        storage.write_memory({"type": "mood", "score": 1, "id": "aaa"})
        storage.write_memory({"type": "mood", "score": 2, "id": "bbb"})

        assert storage.edit_memory_entry("aaa", {"score": 50}) is True
        assert storage.delete_memory_entry("bbb") is True

        entries = storage.get_recent_memory(days=1)
        assert len(entries) == 1
        assert entries[0]["id"] == "aaa"
        assert entries[0]["score"] == 50

        # file on disk must still be opaque, not plaintext
        raw = storage.MEMORY_FILE.read_text(encoding="utf-8")
        assert "mood" not in raw


class TestCrashSafety:
    def test_rewrite_uses_atomic_replace_not_partial_write(self, storage):
        """The rewrite path writes to a .tmp file and replaces in one
        step, so an interrupted rewrite can't leave memory.jsonl
        half-written. This test just confirms no stray .tmp file is
        left behind after a normal successful edit/delete."""
        storage.write_memory({"type": "mood", "score": 1, "id": "aaa"})
        storage.delete_memory_entry("aaa")
        tmp_path = storage.MEMORY_FILE.with_suffix(storage.MEMORY_FILE.suffix + ".tmp")
        assert not tmp_path.exists()
