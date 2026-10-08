"""Tests for demo/restore.py - restoring JSON backups."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def rs(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("LIFE_OS_PROFILE", raising=False)
    for mod in ("storage", "crypto_store", "data_export", "backup", "restore"):
        if mod in sys.modules:
            del sys.modules[mod]
    import restore as r
    importlib.reload(r)
    r.storage.set_active_profile(None)
    return r


def _write(tmp_path, payload, name="b.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pre_restore_files(rs):
    directory = rs.backup.backups_dir()
    return list(directory.glob("pre-restore-*")) if directory.exists() else []


def _entry(i, kind="mood"):
    return {"id": f"id{i}", "type": kind, "score": i, "timestamp": f"2026-01-0{i}T09:00:00Z"}


class TestLoadBackupFile:
    def test_missing_file(self, rs, tmp_path):
        with pytest.raises(rs.RestoreError, match="not found"):
            rs.load_backup_file(tmp_path / "nope.json")

    def test_directory_is_not_a_file(self, rs, tmp_path):
        with pytest.raises(rs.RestoreError, match="not found"):
            rs.load_backup_file(tmp_path)

    def test_invalid_json(self, rs, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(rs.RestoreError, match="Could not read"):
            rs.load_backup_file(path)

    def test_json_list_rejected(self, rs, tmp_path):
        with pytest.raises(rs.RestoreError, match="expected a JSON object"):
            rs.load_backup_file(_write(tmp_path, [1, 2]))

    def test_valid(self, rs, tmp_path):
        assert rs.load_backup_file(_write(tmp_path, {"habits": []})) == {"habits": []}


class TestValidatePayload:
    def test_valid_payload_has_no_problems(self, rs):
        assert rs.validate_payload({"habits": [], "profile": {}, "memory": [{"id": "a"}]}) == []

    @pytest.mark.parametrize("name,bad", [
        ("profile", []), ("hydration", []), ("templates", []),
        ("habits", {}), ("spending", "x"), ("reminders", 5), ("budgets", {"a": 1}),
    ])
    def test_wrong_type_per_store(self, rs, name, bad):
        problems = rs.validate_payload({name: bad, "memory": []})
        assert len(problems) == 1 and f"'{name}'" in problems[0]

    def test_memory_must_be_list(self, rs):
        problems = rs.validate_payload({"memory": {"a": 1}})
        assert any("'memory' should be a JSON list" in p for p in problems)

    def test_memory_entries_must_be_objects(self, rs):
        problems = rs.validate_payload({"memory": [{"id": "a"}, "x", 3]})
        assert any("2 entries" in p for p in problems)

    def test_single_bad_memory_entry_wording(self, rs):
        problems = rs.validate_payload({"memory": ["x"]})
        assert any("1 entry that is not" in p for p in problems)

    def test_all_problems_reported_together(self, rs):
        problems = rs.validate_payload({"habits": {}, "profile": [], "memory": "x"})
        assert len(problems) == 3

    def test_no_known_sections_is_a_problem(self, rs):
        assert rs.validate_payload({"hello": "world"})
        assert rs.validate_payload({})

    def test_unknown_keys_alone_with_a_known_section_are_fine(self, rs):
        assert rs.validate_payload({"habits": [], "future_thing": 1}) == []


class TestParseOnly:
    def test_none_means_everything(self, rs):
        assert rs.parse_only(None) is None

    def test_comma_string(self, rs):
        assert rs.parse_only("spending,budgets") == ["spending", "budgets"]

    def test_list(self, rs):
        assert rs.parse_only(["spending", "memory"]) == ["spending", "memory"]

    def test_normalizes_case_whitespace_and_duplicates(self, rs):
        assert rs.parse_only(" Spending , BUDGETS,spending ,") == ["spending", "budgets"]

    @pytest.mark.parametrize("bad", ["", " , ", []])
    def test_empty_selection_rejected(self, rs, bad):
        with pytest.raises(rs.RestoreError, match="at least one"):
            rs.parse_only(bad)

    def test_unknown_name_rejected_with_valid_list(self, rs):
        with pytest.raises(rs.RestoreError, match="Unknown section.*bogus.*Valid sections"):
            rs.parse_only("spending,bogus")

    def test_known_sections_include_memory_and_all_stores(self, rs):
        names = rs.known_sections()
        assert "memory" in names
        assert set(rs.storage.data_store_names()) <= set(names)


class TestPlanRestore:
    def test_counts_current_and_incoming(self, rs):
        rs.storage.save_habits([{"name": "a"}])
        plan = rs.plan_restore({"habits": [{"name": "x"}, {"name": "y"}]})
        assert plan["sections"] == [{"name": "habits", "current": 1, "incoming": 2}]

    def test_sections_not_in_backup_are_skipped(self, rs):
        plan = rs.plan_restore({"habits": []})
        assert "spending" in plan["skipped_not_in_backup"]
        assert "habits" not in plan["skipped_not_in_backup"]

    def test_only_limits_sections(self, rs):
        plan = rs.plan_restore({"habits": [], "goals": []}, only="goals")
        assert [s["name"] for s in plan["sections"]] == ["goals"]
        assert "habits" in plan["skipped_not_selected"]

    def test_only_section_missing_from_backup_is_an_error(self, rs):
        with pytest.raises(rs.RestoreError, match="no section.*goals"):
            rs.plan_restore({"habits": []}, only="goals")

    def test_invalid_payload_raises(self, rs):
        with pytest.raises(rs.RestoreError, match="failed validation"):
            rs.plan_restore({"habits": {}})

    def test_meta_is_not_reported_as_ignored(self, rs):
        plan = rs.plan_restore({"habits": [], "_meta": {"format_version": 2}})
        assert plan["ignored_keys"] == []

    def test_unknown_keys_reported_sorted(self, rs):
        plan = rs.plan_restore({"habits": [], "zeta": 1, "alpha": 2})
        assert plan["ignored_keys"] == ["alpha", "zeta"]

    def test_memory_counts(self, rs):
        rs.storage.write_memory({"type": "t"})
        plan = rs.plan_restore({"memory": [_entry(1), _entry(2)]})
        assert plan["sections"] == [{"name": "memory", "current": 1, "incoming": 2}]

    def test_plan_writes_nothing(self, rs):
        rs.storage.save_habits([{"name": "keep"}])
        rs.plan_restore({"habits": []})
        assert rs.storage.load_habits() == [{"name": "keep"}]


class TestRestoreBackup:
    def test_replaces_a_store(self, rs, tmp_path):
        rs.storage.save_spending([{"amount": 1}])
        path = _write(tmp_path, {"spending": [{"amount": 99}]})
        result = rs.restore_backup(path)
        assert rs.storage.load_spending() == [{"amount": 99}]
        assert result["restored"] == {"spending": 1}

    def test_replaces_dict_stores(self, rs, tmp_path):
        path = _write(tmp_path, {"profile": {"name": "Alex"}, "templates": {"t": []},
                                 "hydration": {"today": 3, "goal": 8, "log": []}})
        rs.restore_backup(path)
        assert rs.storage.load_profile() == {"name": "Alex"}
        assert rs.storage.load_templates() == {"t": []}
        assert rs.storage.load_hydration()["today"] == 3

    def test_replaces_memory_and_keeps_ids(self, rs, tmp_path):
        rs.storage.write_memory({"type": "old"})
        path = _write(tmp_path, {"memory": [_entry(1), _entry(2)]})
        rs.restore_backup(path)
        assert [e["id"] for e in rs.storage.get_all_memory()] == ["id1", "id2"]

    def test_empty_section_in_backup_clears_current_data(self, rs, tmp_path):
        rs.storage.save_reminders([{"id": "r"}])
        rs.restore_backup(_write(tmp_path, {"reminders": []}))
        assert rs.storage.load_reminders() == []

    def test_sections_missing_from_backup_are_left_untouched(self, rs, tmp_path):
        """An old (pre-1.38.0) backup has no spending/reminders sections;
        restoring it must not wipe them."""
        rs.storage.save_spending([{"amount": 7}])
        rs.storage.save_reminders([{"id": "r"}])
        rs.storage.save_habits([{"name": "old"}])
        rs.restore_backup(_write(tmp_path, {"habits": [{"name": "restored"}]}))
        assert rs.storage.load_habits() == [{"name": "restored"}]
        assert rs.storage.load_spending() == [{"amount": 7}]
        assert rs.storage.load_reminders() == [{"id": "r"}]

    def test_only_restores_selected_sections(self, rs, tmp_path):
        rs.storage.save_habits([{"name": "keep"}])
        rs.storage.save_goals([{"name": "old goal"}])
        path = _write(tmp_path, {"habits": [], "goals": [{"name": "new goal"}]})
        result = rs.restore_backup(path, only="goals")
        assert rs.storage.load_habits() == [{"name": "keep"}]
        assert rs.storage.load_goals() == [{"name": "new goal"}]
        assert list(result["restored"]) == ["goals"]

    def test_unknown_keys_ignored_not_written(self, rs, tmp_path):
        path = _write(tmp_path, {"habits": [], "weird": [1]})
        result = rs.restore_backup(path)
        assert result["ignored_keys"] == ["weird"]
        assert not (rs.storage.HERMES_DIR / "weird.json").exists()

    def test_invalid_backup_writes_nothing_even_for_valid_sections(self, rs, tmp_path):
        rs.storage.save_habits([{"name": "keep"}])
        rs.storage.write_memory({"type": "keep"})
        path = _write(tmp_path, {"habits": [], "profile": [], "memory": []})
        with pytest.raises(rs.RestoreError):
            rs.restore_backup(path)
        assert rs.storage.load_habits() == [{"name": "keep"}]
        assert len(rs.storage.get_all_memory()) == 1
        assert _pre_restore_files(rs) == []

    def test_unreadable_file_raises(self, rs, tmp_path):
        with pytest.raises(rs.RestoreError):
            rs.restore_backup(tmp_path / "missing.json")

    def test_bad_only_name_writes_nothing(self, rs, tmp_path):
        rs.storage.save_habits([{"name": "keep"}])
        with pytest.raises(rs.RestoreError):
            rs.restore_backup(_write(tmp_path, {"habits": []}), only="bogus")
        assert rs.storage.load_habits() == [{"name": "keep"}]

    def test_restores_into_the_active_profile(self, rs, tmp_path):
        rs.storage.set_active_profile("alex")
        rs.restore_backup(_write(tmp_path, {"habits": [{"name": "alex habit"}]}))
        assert rs.storage.load_habits() == [{"name": "alex habit"}]
        rs.storage.set_active_profile(None)
        assert rs.storage.load_habits() == []


class TestDryRun:
    def test_dry_run_changes_nothing(self, rs, tmp_path):
        rs.storage.save_habits([{"name": "keep"}])
        rs.storage.write_memory({"type": "keep"})
        path = _write(tmp_path, {"habits": [], "memory": []})
        result = rs.restore_backup(path, dry_run=True)
        assert result["dry_run"] is True
        assert result["restored"] == {}
        assert rs.storage.load_habits() == [{"name": "keep"}]
        assert len(rs.storage.get_all_memory()) == 1

    def test_dry_run_writes_no_safety_backup(self, rs, tmp_path):
        result = rs.restore_backup(_write(tmp_path, {"habits": []}), dry_run=True)
        assert result["safety_backup"] is None
        assert not rs.backup.backups_dir().exists()

    def test_dry_run_still_validates(self, rs, tmp_path):
        with pytest.raises(rs.RestoreError):
            rs.restore_backup(_write(tmp_path, {"habits": {}}), dry_run=True)


class TestSafetyBackup:
    def test_written_before_replacing_and_contains_previous_data(self, rs, tmp_path):
        rs.storage.save_habits([{"name": "before"}])
        rs.storage.write_memory({"type": "before"})
        result = rs.restore_backup(_write(tmp_path, {"habits": [{"name": "after"}], "memory": []}))
        safety = Path(result["safety_backup"])
        assert safety.exists()
        saved = json.loads(safety.read_text(encoding="utf-8"))
        assert saved["habits"] == [{"name": "before"}]
        assert len(saved["memory"]) == 1

    def test_safety_backup_can_undo_the_restore(self, rs, tmp_path):
        rs.storage.save_habits([{"name": "before"}])
        result = rs.restore_backup(_write(tmp_path, {"habits": [{"name": "after"}]}))
        rs.restore_backup(result["safety_backup"])
        assert rs.storage.load_habits() == [{"name": "before"}]

    def test_safety_backup_is_never_rotated_away(self, rs, tmp_path):
        result = rs.restore_backup(_write(tmp_path, {"habits": []}))
        assert not rs.backup.BACKUP_FILENAME_RE.match(Path(result["safety_backup"]).name)
        rs.backup.rotate_backups(rs.backup.backups_dir(), keep=0)
        assert Path(result["safety_backup"]).exists()

    def test_safety_backup_does_not_count_as_a_regular_backup(self, rs, tmp_path):
        rs.restore_backup(_write(tmp_path, {"habits": []}))
        assert rs.backup.list_backups() == []

    def test_safety_backup_names_are_unique_within_one_second(self, rs):
        now = datetime(2026, 10, 1, 12, 0, 0)
        first = rs.write_safety_backup(now)
        second = rs.write_safety_backup(now)
        third = rs.write_safety_backup(now)
        assert len({first, second, third}) == 3
        assert first.name == "pre-restore-2026-10-01-120000.json"
        assert second.name == "pre-restore-2026-10-01-120000-1.json"

    def test_can_be_disabled(self, rs, tmp_path):
        result = rs.restore_backup(_write(tmp_path, {"habits": []}), safety_backup=False)
        assert result["safety_backup"] is None
        assert not rs.backup.backups_dir().exists()


class TestFullRoundTrip:
    def _seed_everything(self, storage):
        for name in storage.data_store_names():
            expected = storage.DATA_STORES[name][3]
            storage.save_store(name, {"marker": name} if expected is dict else [{"marker": name}])
        storage.write_memory({"id": "m1", "type": "mood", "score": 7})

    def test_backup_then_restore_brings_everything_back(self, rs):
        storage = rs.storage
        self._seed_everything(storage)
        before = {n: storage.load_store(n) for n in storage.data_store_names()}
        backup_path = rs.backup.run_backup()

        for name in storage.data_store_names():
            storage.save_store(name, {} if storage.DATA_STORES[name][3] is dict else [])
        storage.replace_all_memory([])

        result = rs.restore_backup(backup_path)
        assert set(result["restored"]) == set(storage.data_store_names()) | {"memory"}
        for name, value in before.items():
            assert storage.load_store(name) == value, name
        assert [e["id"] for e in storage.get_all_memory()] == ["m1"]

    def test_restore_from_a_pre_1_38_backup(self, rs, tmp_path):
        """Format 1: only nine stores, no _meta."""
        legacy = {"profile": {"name": "Old"}, "habits": [{"name": "h"}], "goals": [],
                  "nutrition": [], "sleep": [], "hydration": {"today": 1, "goal": 8, "log": []},
                  "fitness": [], "focus": [], "mental": [], "memory": [_entry(1)]}
        rs.storage.save_spending([{"amount": 5}])
        result = rs.restore_backup(_write(tmp_path, legacy))
        assert rs.storage.load_profile()["name"] == "Old"
        assert rs.storage.load_spending() == [{"amount": 5}]
        assert "spending" in result["skipped_not_in_backup"]

    def test_restore_under_encryption_writes_encrypted_files(self, rs, tmp_path, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        rs.restore_backup(_write(tmp_path, {"spending": [{"amount": 123456}], "memory": [_entry(1)]}),
                          safety_backup=False)
        raw = rs.storage.data_store_path("spending").read_text(encoding="utf-8")
        assert "123456" not in raw
        assert rs.storage.load_spending() == [{"amount": 123456}]
        assert "id1" not in rs.storage.MEMORY_FILE.read_text(encoding="utf-8")
        assert rs.storage.get_all_memory()[0]["id"] == "id1"


class TestFormatRestoreResult:
    def test_dry_run_wording(self, rs, tmp_path):
        rs.storage.save_habits([{"name": "a"}])
        result = rs.restore_backup(_write(tmp_path, {"habits": [{"name": "x"}, {"name": "y"}]}), dry_run=True)
        out = rs.format_restore_result(result)
        assert "Would replace 1 section(s)" in out
        assert "habits: 1 -> 2 item(s)" in out
        assert "Dry run - nothing was changed." in out

    def test_real_run_wording_and_safety_path(self, rs, tmp_path):
        result = rs.restore_backup(_write(tmp_path, {"habits": []}))
        out = rs.format_restore_result(result)
        assert "Replaced 1 section(s)" in out
        assert "Safety copy of your previous data:" in out
        assert "Dry run" not in out

    def test_lists_not_selected_and_ignored(self, rs, tmp_path):
        result = rs.restore_backup(_write(tmp_path, {"habits": [], "goals": [], "extra": 1}),
                                   only="habits", dry_run=True)
        out = rs.format_restore_result(result)
        assert "Left untouched (not selected):" in out
        assert "goals" in out.split("not selected):")[1].split("\n")[0]
        assert "unknown keys in the file: extra" in out

    def test_lists_sections_not_in_backup(self, rs, tmp_path):
        result = rs.restore_backup(_write(tmp_path, {"habits": []}), dry_run=True)
        out = rs.format_restore_result(result)
        assert "Left untouched (not in this backup):" in out
        assert "spending" in out

    def test_nothing_to_restore(self, rs):
        out = rs.format_restore_result({"sections": [], "skipped_not_in_backup": [],
                                        "skipped_not_selected": [], "ignored_keys": [],
                                        "dry_run": True, "safety_backup": None, "restored": {}})
        assert out.startswith("Nothing to restore.")


class TestMainCLI:
    def _backup_with_habit(self, rs, name="x"):
        rs.storage.save_habits([{"name": name}])
        return rs.backup.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))

    def test_no_arguments_is_a_usage_error(self, rs):
        with pytest.raises(SystemExit) as e:
            rs.main([])
        assert e.value.code == 2

    def test_path_and_latest_together_is_a_usage_error(self, rs, tmp_path):
        with pytest.raises(SystemExit) as e:
            rs.main([str(tmp_path / "x.json"), "--latest"])
        assert e.value.code == 2

    def test_list_with_no_backups(self, rs, capsys):
        rs.main(["--list"])
        assert "No backups found" in capsys.readouterr().out

    def test_list_shows_backups_newest_first(self, rs, capsys):
        rs.backup.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        rs.backup.run_backup(now=datetime(2026, 10, 2, 20, 30, 0))
        rs.main(["--list"])
        out = capsys.readouterr().out
        assert out.index("2026-10-02") < out.index("2026-10-01")
        assert "ok" in out

    def test_list_flags_unreadable_backup(self, rs, capsys):
        rs.backup.backups_dir().mkdir(parents=True)
        (rs.backup.backups_dir() / "backup-2026-10-01-000000.json").write_text("garbage", encoding="utf-8")
        rs.main(["--list"])
        assert "UNREADABLE" in capsys.readouterr().out

    def test_latest_with_no_backups_exits_1(self, rs, capsys):
        with pytest.raises(SystemExit) as e:
            rs.main(["--latest"])
        assert e.value.code == 1
        assert "No backups found" in capsys.readouterr().out

    def test_dry_run_prints_plan_and_changes_nothing(self, rs, capsys):
        self._backup_with_habit(rs, "from backup")
        rs.storage.save_habits([{"name": "current"}])
        rs.main(["--latest", "--dry-run"])
        out = capsys.readouterr().out
        assert "Would replace" in out and "Dry run" in out
        assert rs.storage.load_habits() == [{"name": "current"}]

    def test_yes_restores_without_prompting(self, rs, capsys, monkeypatch):
        self._backup_with_habit(rs, "from backup")
        rs.storage.save_habits([{"name": "current"}])
        monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("should not prompt"))
        rs.main(["--latest", "--yes"])
        assert rs.storage.load_habits() == [{"name": "from backup"}]
        assert "Replaced" in capsys.readouterr().out

    def test_prompt_yes_restores(self, rs, monkeypatch):
        self._backup_with_habit(rs, "from backup")
        rs.storage.save_habits([{"name": "current"}])
        monkeypatch.setattr("builtins.input", lambda *a: "y")
        rs.main(["--latest"])
        assert rs.storage.load_habits() == [{"name": "from backup"}]

    def test_prompt_no_cancels(self, rs, capsys, monkeypatch):
        self._backup_with_habit(rs, "from backup")
        rs.storage.save_habits([{"name": "current"}])
        monkeypatch.setattr("builtins.input", lambda *a: "n")
        rs.main(["--latest"])
        assert "Cancelled" in capsys.readouterr().out
        assert rs.storage.load_habits() == [{"name": "current"}]

    def test_explicit_path(self, rs, tmp_path):
        path = _write(tmp_path, {"habits": [{"name": "via path"}]})
        rs.main([str(path), "--yes"])
        assert rs.storage.load_habits() == [{"name": "via path"}]

    def test_invalid_file_exits_1_and_changes_nothing(self, rs, tmp_path, capsys):
        rs.storage.save_habits([{"name": "keep"}])
        path = _write(tmp_path, {"habits": {}})
        with pytest.raises(SystemExit) as e:
            rs.main([str(path), "--yes"])
        assert e.value.code == 1
        assert "Restore failed" in capsys.readouterr().out
        assert rs.storage.load_habits() == [{"name": "keep"}]

    def test_missing_file_exits_1(self, rs, tmp_path, capsys):
        with pytest.raises(SystemExit) as e:
            rs.main([str(tmp_path / "nope.json"), "--yes"])
        assert e.value.code == 1

    def test_only_flag(self, rs, tmp_path):
        rs.storage.save_habits([{"name": "keep"}])
        path = _write(tmp_path, {"habits": [], "goals": [{"name": "g"}]})
        rs.main([str(path), "--only", "goals", "--yes"])
        assert rs.storage.load_habits() == [{"name": "keep"}]
        assert rs.storage.load_goals() == [{"name": "g"}]

    def test_bad_only_flag_exits_1(self, rs, tmp_path):
        with pytest.raises(SystemExit) as e:
            rs.main([str(_write(tmp_path, {"habits": []})), "--only", "bogus", "--yes"])
        assert e.value.code == 1

    def test_no_safety_backup_flag(self, rs, tmp_path):
        rs.main([str(_write(tmp_path, {"habits": []})), "--no-safety-backup", "--yes"])
        assert _pre_restore_files(rs) == []

    def test_default_run_writes_safety_backup(self, rs, tmp_path):
        rs.main([str(_write(tmp_path, {"habits": []})), "--yes"])
        assert len(_pre_restore_files(rs)) == 1

    def test_profile_flag(self, rs, tmp_path):
        path = _write(tmp_path, {"habits": [{"name": "alex"}]})
        rs.main([str(path), "--profile", "alex", "--yes"])
        assert rs.storage.ACTIVE_PROFILE == "alex"
        assert rs.storage.load_habits() == [{"name": "alex"}]

    def test_profile_from_environment(self, rs, tmp_path, monkeypatch):
        monkeypatch.setenv("LIFE_OS_PROFILE", "sam")
        rs.main([str(_write(tmp_path, {"habits": [{"name": "sam"}]})), "--yes"])
        assert rs.storage.ACTIVE_PROFILE == "sam"

    def test_dry_run_never_prompts(self, rs, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("should not prompt"))
        path = _write(tmp_path, {"habits": [], "goals": []})
        rs.main([str(path), "--only", "habits", "--dry-run"])
        assert "Would replace" in capsys.readouterr().out


class TestEncryptedBackupRestore:
    @pytest.fixture(autouse=True)
    def _needs_crypto(self):
        pytest.importorskip("cryptography")

    def _make_encrypted_backup(self, rs, monkeypatch, key="pw"):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", key)
        rs.storage.save_habits([{"name": "kept"}])
        rs.storage.write_memory({"id": "m1", "type": "t"})
        return rs.backup.run_backup()

    def test_round_trip(self, rs, monkeypatch):
        path = self._make_encrypted_backup(rs, monkeypatch)
        rs.storage.save_habits([])
        rs.storage.replace_all_memory([])
        rs.restore_backup(path)
        assert rs.storage.load_habits() == [{"name": "kept"}]
        assert [e["id"] for e in rs.storage.get_all_memory()] == ["m1"]

    def test_wrong_key_gives_a_helpful_error_and_changes_nothing(self, rs, monkeypatch):
        path = self._make_encrypted_backup(rs, monkeypatch, key="right")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "wrong")
        before = rs.storage.data_store_path("habits").read_text(encoding="utf-8")
        with pytest.raises(rs.RestoreError, match="LIFE_OS_ENCRYPTION_KEY"):
            rs.restore_backup(path)
        assert rs.storage.data_store_path("habits").read_text(encoding="utf-8") == before

    def test_missing_key_gives_a_helpful_error(self, rs, monkeypatch):
        path = self._make_encrypted_backup(rs, monkeypatch)
        monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY")
        with pytest.raises(rs.RestoreError, match="LIFE_OS_ENCRYPTION_KEY"):
            rs.restore_backup(path)

    def test_safety_backup_is_encrypted_under_the_key(self, rs, tmp_path, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        rs.storage.save_habits([{"name": "very-private-habit"}])
        result = rs.restore_backup(_write(tmp_path, {"goals": []}))
        raw = Path(result["safety_backup"]).read_text(encoding="utf-8")
        assert "very-private-habit" not in raw
        # ... and it can itself be restored with the same key
        rs.restore_backup(result["safety_backup"], safety_backup=False)
        assert rs.storage.load_habits() == [{"name": "very-private-habit"}]

    def test_plaintext_backup_restores_fine_while_a_key_is_active(self, rs, tmp_path, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        rs.restore_backup(_write(tmp_path, {"habits": [{"name": "plain"}]}), safety_backup=False)
        assert rs.storage.load_habits() == [{"name": "plain"}]

    def test_json_list_error_message_unchanged(self, rs, tmp_path):
        with pytest.raises(rs.RestoreError, match="expected a JSON object"):
            rs.load_backup_file(_write(tmp_path, [1]))
