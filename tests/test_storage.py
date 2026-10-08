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

    def test_write_memory_preserves_explicit_timestamp(self, storage):
        """Needed for bulk/historical import (health_import.py) - a caller
        that already supplies a timestamp must not have it silently
        overwritten with 'now'."""
        storage.write_memory({"type": "sleep", "hours": 7, "timestamp": "2020-01-01T09:00:00Z"})
        results = storage.search_memory("sleep")
        assert results[0]["timestamp"] == "2020-01-01T09:00:00Z"

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

    def test_get_memory_window_isolates_a_past_range(self, storage):
        import json
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            for days_ago, label in [(2, "this_week"), (10, "last_week"), (20, "two_weeks_ago")]:
                ts = (now - timedelta(days=days_ago)).strftime("%Y-%m-%dT09:00:00Z")
                f.write(json.dumps({"type": "mood", "content": label, "timestamp": ts}) + "\n")

        this_week = storage.get_recent_memory(days=7)
        last_week = storage.get_memory_window(14, 7)

        assert [e["content"] for e in this_week] == ["this_week"]
        assert [e["content"] for e in last_week] == ["last_week"]

    def test_get_memory_window_empty_when_file_missing(self, storage):
        assert storage.get_memory_window(14, 7) == []

    def test_get_memory_by_date_range_inclusive_bounds(self, storage):
        import json
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            for date in ["2026-02-28", "2026-03-01", "2026-03-15", "2026-03-31", "2026-04-01"]:
                f.write(json.dumps({"type": "mood", "score": 5, "timestamp": f"{date}T09:00:00Z"}) + "\n")

        march = storage.get_memory_by_date_range("2026-03-01", "2026-03-31")
        dates = {e["timestamp"][:10] for e in march}
        assert dates == {"2026-03-01", "2026-03-15", "2026-03-31"}

    def test_get_memory_by_date_range_invalid_dates_returns_empty(self, storage):
        storage.write_memory({"type": "mood", "score": 5})
        assert storage.get_memory_by_date_range("not-a-date", "also-not-a-date") == []

    def test_get_memory_by_date_range_no_file_returns_empty(self, storage):
        assert storage.get_memory_by_date_range("2026-01-01", "2026-01-31") == []

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


def _sample_for(storage, name):
    """A small, valid, non-default value for a registered store."""
    expected = storage.DATA_STORES[name][3]
    return {"sample": name, "n": 1} if expected is dict else [{"sample": name}]


class TestDataStoreRegistry:
    def test_registry_has_every_expected_store(self, storage):
        assert set(storage.data_store_names()) == {
            "profile", "habits", "goals", "nutrition", "sleep", "hydration", "fitness",
            "focus", "mental", "spending", "social", "substance", "reading", "medication",
            "achievements", "templates", "budgets", "reminders",
        }

    def test_every_file_constant_is_registered(self, storage):
        """Drift guard: adding a new *_FILE path to storage.py without
        registering it in DATA_STORES would leave it out of backups,
        restore and rekey."""
        file_attrs = {n for n in dir(storage) if n.endswith("_FILE") and n != "MEMORY_FILE"}
        registered = {entry[0] for entry in storage.DATA_STORES.values()}
        assert file_attrs == registered

    def test_registry_entries_are_wired_correctly(self, storage):
        for name, (file_attr, loader, saver, expected) in storage.DATA_STORES.items():
            assert isinstance(getattr(storage, file_attr), Path), name
            assert callable(getattr(storage, loader)), name
            assert callable(getattr(storage, saver)), name
            assert expected in (list, dict), name

    def test_loader_default_matches_declared_type(self, storage):
        for name in storage.data_store_names():
            assert isinstance(storage.load_store(name), storage.DATA_STORES[name][3]), name

    def test_save_and_load_by_name_round_trip(self, storage):
        for name in storage.data_store_names():
            value = _sample_for(storage, name)
            storage.save_store(name, value)
            assert storage.load_store(name) == value, name

    def test_save_by_name_uses_the_real_saver(self, storage):
        storage.save_store("spending", [{"amount": 5}])
        assert storage.load_spending() == [{"amount": 5}]

    def test_store_paths_are_distinct_and_in_data_dir(self, storage):
        paths = storage.data_store_paths()
        assert len(set(paths)) == len(paths) == len(storage.DATA_STORES)
        assert all(p.parent == storage.HERMES_DIR for p in paths)

    def test_store_path_follows_active_profile(self, storage):
        default_path = storage.data_store_path("budgets")
        storage.set_active_profile("alex")
        assert storage.data_store_path("budgets") != default_path
        assert "alex" in str(storage.data_store_path("budgets"))

    def test_unknown_store_raises_keyerror(self, storage):
        with pytest.raises(KeyError):
            storage.load_store("nope")
        with pytest.raises(KeyError):
            storage.save_store("nope", [])
        with pytest.raises(KeyError):
            storage.data_store_path("nope")


class TestReplaceAllMemory:
    def test_replaces_everything(self, storage):
        storage.write_memory({"type": "old", "content": "gone"})
        n = storage.replace_all_memory([{"id": "a1", "type": "new", "timestamp": "2026-01-01T00:00:00Z"}])
        assert n == 1
        entries = storage.get_all_memory()
        assert [e["id"] for e in entries] == ["a1"]

    def test_empty_list_clears_memory(self, storage):
        storage.write_memory({"type": "old"})
        assert storage.replace_all_memory([]) == 0
        assert storage.get_all_memory() == []

    def test_works_when_no_memory_file_exists_yet(self, storage):
        assert storage.replace_all_memory([{"id": "x", "type": "t"}]) == 1
        assert len(storage.get_all_memory()) == 1

    def test_accepts_any_iterable(self, storage):
        assert storage.replace_all_memory(iter([{"id": "x"}, {"id": "y"}])) == 2

    def test_no_temp_file_left_behind(self, storage):
        storage.replace_all_memory([{"id": "x"}])
        assert not list(storage.HERMES_DIR.glob("*.tmp"))

    def test_encrypted_under_active_key(self, storage, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "secret-passphrase")
        storage.replace_all_memory([{"id": "x", "content": "private thought"}])
        raw = storage.MEMORY_FILE.read_text(encoding="utf-8")
        assert "private thought" not in raw
        assert storage.get_all_memory()[0]["content"] == "private thought"


class TestEncryptDecryptText:
    def test_no_key_is_identity(self, storage, monkeypatch):
        monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
        assert storage.encrypt_text("hello") == "hello"
        assert storage.decrypt_text("hello") == "hello"

    def test_round_trip_with_key(self, storage, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        token = storage.encrypt_text("secret text")
        assert token != "secret text" and "secret" not in token
        assert storage.decrypt_text(token) == "secret text"

    def test_encryption_is_not_deterministic(self, storage, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        assert storage.encrypt_text("x") != storage.encrypt_text("x")

    def test_plaintext_passes_through_decrypt_unchanged(self, storage, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        assert storage.decrypt_text('{"a": 1}') == '{"a": 1}'

    def test_wrong_key_returns_input_unchanged(self, storage, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "right")
        token = storage.encrypt_text("secret")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "wrong")
        assert storage.decrypt_text(token) == token

    def test_surrounding_whitespace_tolerated(self, storage, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        token = storage.encrypt_text("secret")
        assert storage.decrypt_text("\n" + token + "\n") == "secret"

    def test_non_ascii_garbage_does_not_raise(self, storage, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        assert storage.decrypt_text("güvenli yedek") == "güvenli yedek"
