"""Tests for local persistence (demo/storage.py), isolated via a temp HOME
so these tests never touch the real ~/.hermes/life-os data on the dev machine."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    """Reload storage.py with HOME pointed at a temp dir, so each test
    gets a fresh, isolated .hermes/life-os directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if "storage" in sys.modules:
        del sys.modules["storage"]
    import storage as s
    importlib.reload(s)
    return s


class TestProfile:
    def test_default_profile(self, storage):
        p = storage.load_profile()
        assert p == {"name": "friend", "onboarded": False}

    def test_save_and_load_profile(self, storage):
        storage.save_profile({"name": "Alex", "onboarded": True})
        assert storage.load_profile() == {"name": "Alex", "onboarded": True}


class TestHabitsAndGoals:
    def test_default_habits_empty(self, storage):
        assert storage.load_habits() == []

    def test_save_and_load_habits(self, storage):
        storage.save_habits([{"name": "run", "streak": 3}])
        assert storage.load_habits() == [{"name": "run", "streak": 3}]

    def test_save_and_load_goals(self, storage):
        storage.save_goals([{"name": "ship project", "progress": 50}])
        assert storage.load_goals() == [{"name": "ship project", "progress": 50}]


class TestHydration:
    def test_default_hydration(self, storage):
        h = storage.load_hydration()
        assert h == {"today": 0, "goal": 8, "log": []}

    def test_save_and_load_hydration(self, storage):
        storage.save_hydration({"today": 5, "goal": 8, "log": [{"glasses": 5}]})
        assert storage.load_hydration()["today"] == 5


class TestMemoryJournal:
    def test_write_and_search_memory(self, storage):
        storage.write_memory({"type": "mood", "content": "great day", "score": 9})
        results = storage.search_memory("great day")
        assert len(results) == 1
        assert results[0]["type"] == "mood"
        assert results[0]["score"] == 9

    def test_write_memory_adds_timestamp(self, storage):
        storage.write_memory({"type": "mood", "content": "x", "score": 5})
        results = storage.search_memory("x")
        assert "timestamp" in results[0]

    def test_search_memory_no_match(self, storage):
        storage.write_memory({"type": "mood", "content": "great day", "score": 9})
        assert storage.search_memory("nonexistent query xyz") == []

    def test_search_memory_empty_file(self, storage):
        assert storage.search_memory("anything") == []

    def test_search_memory_respects_limit(self, storage):
        for i in range(5):
            storage.write_memory({"type": "mood", "content": f"day {i}", "score": i})
        results = storage.search_memory("day", limit=2)
        assert len(results) == 2

    def test_get_recent_memory_within_window(self, storage):
        storage.write_memory({"type": "mood", "content": "today", "score": 7})
        recent = storage.get_recent_memory(days=7)
        assert len(recent) == 1

    def test_memory_count(self, storage):
        assert storage.memory_count() == 0
        storage.write_memory({"type": "mood", "content": "a", "score": 5})
        storage.write_memory({"type": "mood", "content": "b", "score": 6})
        assert storage.memory_count() == 2

    def test_search_memory_ignores_corrupt_lines(self, storage):
        storage.write_memory({"type": "mood", "content": "valid", "score": 5})
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write("not valid json\n")
        # Should not raise, and should still find the valid entry
        results = storage.search_memory("valid")
        assert len(results) == 1


class TestLoadSaveRoundtripDefaults:
    def test_load_missing_file_returns_default(self, storage):
        assert storage.load_nutrition() == []
        assert storage.load_sleep() == []
        assert storage.load_fitness() == []
        assert storage.load_focus() == []
        assert storage.load_mental() == []

    def test_corrupt_json_file_falls_back_to_default(self, storage, tmp_path):
        storage.PROFILE_FILE.write_text("{not valid json", encoding="utf-8")
        # Should not raise; falls back to default
        assert storage.load_profile() == {"name": "friend", "onboarded": False}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
