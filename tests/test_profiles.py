"""Tests for multi-profile support in demo/storage.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    """Reload storage.py with HOME pointed at a temp dir, fresh for
    every test - matches the pattern used in test_storage.py."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if "storage" in sys.modules:
        del sys.modules["storage"]
    import storage as s
    importlib.reload(s)
    return s


class TestDefaultProfileIsBackwardCompatible:
    def test_no_profile_uses_original_layout(self, storage, tmp_path):
        assert storage.ACTIVE_PROFILE == "default"
        assert storage.HERMES_DIR == tmp_path / ".hermes" / "life-os"
        assert storage.MEMORY_FILE == storage.HERMES_DIR / "memory.jsonl"

    def test_explicit_default_same_as_none(self, storage):
        storage.set_active_profile(None)
        default_dir = storage.HERMES_DIR
        storage.set_active_profile("default")
        assert storage.HERMES_DIR == default_dir


class TestProfileSwitching:
    def test_switching_profile_changes_all_paths(self, storage, tmp_path):
        storage.set_active_profile("alex")
        assert storage.ACTIVE_PROFILE == "alex"
        expected = tmp_path / ".hermes" / "life-os" / "profiles" / "alex"
        assert storage.HERMES_DIR == expected
        assert storage.MEMORY_FILE == expected / "memory.jsonl"
        assert storage.PROFILE_FILE == expected / "profile.json"
        assert storage.HABITS_FILE == expected / "habits.json"

    def test_profile_dir_is_created(self, storage):
        storage.set_active_profile("jamie")
        assert storage.HERMES_DIR.exists()

    def test_profiles_are_isolated_from_each_other(self, storage):
        storage.set_active_profile("alex")
        storage.save_profile({"name": "Alex", "onboarded": True})
        storage.save_habits([{"name": "run", "streak": 3}])

        storage.set_active_profile("jamie")
        # jamie's data must not see alex's data
        assert storage.load_profile() == {"name": "friend", "onboarded": False}
        assert storage.load_habits() == []

        storage.set_active_profile("alex")
        # switching back to alex must still see alex's own data
        assert storage.load_profile() == {"name": "Alex", "onboarded": True}
        assert storage.load_habits() == [{"name": "run", "streak": 3}]

    def test_default_profile_isolated_from_named_profiles(self, storage):
        storage.save_profile({"name": "Default Person", "onboarded": True})

        storage.set_active_profile("alex")
        assert storage.load_profile() == {"name": "friend", "onboarded": False}

        storage.set_active_profile(None)
        assert storage.load_profile() == {"name": "Default Person", "onboarded": True}

    def test_write_memory_respects_active_profile(self, storage):
        storage.set_active_profile("alex")
        storage.write_memory({"type": "mood", "score": 8})
        assert storage.memory_count() == 1

        storage.set_active_profile("jamie")
        assert storage.memory_count() == 0

        storage.set_active_profile("alex")
        assert storage.memory_count() == 1


class TestListProfiles:
    def test_no_profiles_yet(self, storage):
        # fresh temp HOME with no data written at all
        assert storage.list_profiles() == []

    def test_default_only_after_using_default(self, storage):
        storage.save_profile({"name": "X", "onboarded": True})
        assert storage.list_profiles() == ["default"]

    def test_lists_named_profiles_sorted(self, storage):
        storage.set_active_profile("zoe")
        storage.save_profile({"name": "Zoe", "onboarded": True})
        storage.set_active_profile("alex")
        storage.save_profile({"name": "Alex", "onboarded": True})

        assert storage.list_profiles() == ["alex", "zoe"]

    def test_default_listed_first_alongside_named_profiles(self, storage):
        storage.set_active_profile(None)
        storage.save_profile({"name": "Me", "onboarded": True})
        storage.set_active_profile("alex")
        storage.save_profile({"name": "Alex", "onboarded": True})

        assert storage.list_profiles() == ["default", "alex"]


class TestEmptyOrDefaultProfileNameNormalizesToDefault:
    def test_empty_string_is_default(self, storage, tmp_path):
        storage.set_active_profile("")
        assert storage.ACTIVE_PROFILE == "default"
        assert storage.HERMES_DIR == tmp_path / ".hermes" / "life-os"
