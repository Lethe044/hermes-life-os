"""Tests for demo/leaderboard.py. Uses a temp HOME so multiple
"profiles" can be created and cross-checked without touching real
data."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def leaderboard(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "life_score", "achievements", "leaderboard"):
        if mod in sys.modules:
            del sys.modules[mod]
    import leaderboard as lb
    importlib.reload(lb)
    import storage
    storage.set_active_profile(None)
    return lb


class TestOptIn:
    def test_default_not_opted_in(self, leaderboard):
        assert leaderboard.is_opted_in() is False

    def test_join_sets_opted_in(self, leaderboard):
        leaderboard.set_opt_in(True)
        assert leaderboard.is_opted_in() is True

    def test_leave_unsets_opted_in(self, leaderboard):
        leaderboard.set_opt_in(True)
        leaderboard.set_opt_in(False)
        assert leaderboard.is_opted_in() is False

    def test_opt_in_persists_across_reload(self, leaderboard):
        import storage
        leaderboard.set_opt_in(True)
        assert storage.load_profile()["leaderboard_opt_in"] is True

    def test_checking_opt_in_restores_active_profile(self, leaderboard):
        import storage
        storage.set_active_profile("alex")
        leaderboard.is_opted_in("sam")  # checks a different profile
        assert storage.ACTIVE_PROFILE == "alex"  # restored, not left on "sam"

    def test_set_opt_in_for_specific_profile_restores_active_profile(self, leaderboard):
        import storage
        storage.set_active_profile("alex")
        leaderboard.set_opt_in(True, profile="sam")
        assert storage.ACTIVE_PROFILE == "alex"
        assert leaderboard.is_opted_in("sam") is True
        assert leaderboard.is_opted_in("alex") is False


class TestGetLeaderboard:
    def test_empty_when_nobody_opted_in(self, leaderboard):
        assert leaderboard.get_leaderboard() == []

    def test_includes_only_opted_in_profiles(self, leaderboard):
        import storage
        storage.set_active_profile("alex")
        leaderboard.set_opt_in(True)
        storage.write_memory({"type": "mood", "content": "day", "score": 8})

        storage.set_active_profile("sam")
        # sam does NOT opt in

        entries = leaderboard.get_leaderboard()
        assert len(entries) == 1
        assert entries[0]["profile"] == "alex"

    def test_restores_original_active_profile(self, leaderboard):
        import storage
        storage.set_active_profile("alex")
        leaderboard.set_opt_in(True)
        storage.set_active_profile("sam")
        leaderboard.set_opt_in(True)

        storage.set_active_profile("original_caller")
        leaderboard.get_leaderboard()
        assert storage.ACTIVE_PROFILE == "original_caller"

    def test_sorted_by_avg_life_score_descending(self, leaderboard):
        import storage
        storage.set_active_profile("low_scorer")
        leaderboard.set_opt_in(True)
        storage.write_memory({"type": "mood", "content": "meh", "score": 2})

        storage.set_active_profile("high_scorer")
        leaderboard.set_opt_in(True)
        storage.write_memory({"type": "mood", "content": "great", "score": 9})

        entries = leaderboard.get_leaderboard()
        assert entries[0]["profile"] == "high_scorer"
        assert entries[1]["profile"] == "low_scorer"

    def test_profile_with_no_score_sorts_last(self, leaderboard):
        import storage
        storage.set_active_profile("scored")
        leaderboard.set_opt_in(True)
        storage.write_memory({"type": "mood", "content": "day", "score": 5})

        storage.set_active_profile("unscored")
        leaderboard.set_opt_in(True)  # opted in but never logged anything

        entries = leaderboard.get_leaderboard()
        assert entries[-1]["profile"] == "unscored"
        assert entries[-1]["avg_life_score"] is None

    def test_achievement_count_reflected(self, leaderboard):
        import storage
        storage.set_active_profile("achiever")
        leaderboard.set_opt_in(True)
        storage.write_memory({"type": "workout", "content": "run"})

        entries = leaderboard.get_leaderboard()
        assert entries[0]["achievements_earned"] >= 1


class TestFormatLeaderboard:
    def test_empty_returns_friendly_message(self, leaderboard):
        result = leaderboard.format_leaderboard([])
        assert "No one has joined" in result

    def test_top_three_get_medals(self, leaderboard):
        entries = [
            {"display_name": "A", "avg_life_score": 90, "logging_streak": 5, "achievements_earned": 2},
            {"display_name": "B", "avg_life_score": 80, "logging_streak": 3, "achievements_earned": 1},
            {"display_name": "C", "avg_life_score": 70, "logging_streak": 1, "achievements_earned": 0},
            {"display_name": "D", "avg_life_score": 60, "logging_streak": 0, "achievements_earned": 0},
        ]
        result = leaderboard.format_leaderboard(entries)
        lines = result.split("\n")
        assert "\U0001F947" in lines[0]
        assert "\U0001F948" in lines[1]
        assert "\U0001F949" in lines[2]
        assert lines[3].startswith("4.")

    def test_none_score_shown_as_na(self, leaderboard):
        entries = [{"display_name": "A", "avg_life_score": None, "logging_streak": 0, "achievements_earned": 0}]
        result = leaderboard.format_leaderboard(entries)
        assert "N/A" in result


class TestModuleImportableStandalone:
    """Regression test: leaderboard.py once lacked the sys.path.insert
    every other CLI-entry-point module has, so it worked when imported
    from within the demo/ dir but crashed with ModuleNotFoundError when
    invoked via its installed console-script entry point (a different
    working directory/sys.path). Simulates that by importing fresh
    without demo/ already on sys.path."""

    def test_importable_without_demo_dir_preinserted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "leaderboard"):
            if mod in sys.modules:
                del sys.modules[mod]
        original_path = list(sys.path)
        try:
            sys.path = [p for p in sys.path if "demo" not in p]
            import importlib.util
            demo_dir = Path(__file__).parent.parent / "demo"
            spec = importlib.util.spec_from_file_location("leaderboard_fresh", demo_dir / "leaderboard.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # must not raise ModuleNotFoundError
        finally:
            sys.path = original_path


class TestMainCli:
    def test_join_via_cli(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "analytics", "life_score", "achievements", "leaderboard"):
            if mod in sys.modules:
                del sys.modules[mod]
        import leaderboard as lb
        importlib.reload(lb)
        monkeypatch.setattr(sys, "argv", ["leaderboard.py", "join"])
        lb.main()
        assert lb.is_opted_in() is True
