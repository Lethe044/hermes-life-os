"""Tests for demo/doctor.py - the read-only data health check."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def doc(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("LIFE_OS_PROFILE", raising=False)
    for mod in ("storage", "crypto_store", "data_export", "backup", "budgets", "reminders", "doctor"):
        if mod in sys.modules:
            del sys.modules[mod]
    import doctor as d
    importlib.reload(d)
    d.storage.set_active_profile(None)
    return d


def _levels(findings, area=None):
    return [f["level"] for f in findings if area is None or f["area"] == area]


def _messages(findings, level=None, area=None):
    return [f["message"] for f in findings
            if (level is None or f["level"] == level) and (area is None or f["area"] == area)]


def _snapshot(directory: Path):
    """Relative path -> sha1 of every file under directory."""
    return {str(p.relative_to(directory)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


class TestCheckEncryption:
    def test_off(self, doc):
        f = doc.check_encryption()
        assert _levels(f) == ["ok"] and "off" in f[0]["message"]

    def test_on(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        f = doc.check_encryption()
        assert _levels(f) == ["ok"] and "on" in f[0]["message"]

    def test_key_set_but_encryption_unusable(self, doc, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        def boom(_):
            raise RuntimeError("cryptography is not installed")
        monkeypatch.setattr(doc.storage, "encrypt_text", boom)
        f = doc.check_encryption()
        assert _levels(f) == ["error"] and "cryptography is not installed" in f[0]["message"]


class TestCheckStores:
    def test_no_files_yet(self, doc):
        f = doc.check_stores()
        assert _levels(f) == ["ok"] and "No data files yet" in f[0]["message"]

    def test_healthy_stores(self, doc):
        doc.storage.save_habits([{"name": "a"}])
        doc.storage.save_profile({"name": "Alex"})
        f = doc.check_stores()
        assert _levels(f) == ["ok"] and "All 2 data file(s)" in f[0]["message"]

    def test_corrupt_json_names_the_restore_command(self, doc):
        doc.storage.save_spending([{"amount": 1}])
        doc.storage.data_store_path("spending").write_text("{not json", encoding="utf-8")
        f = doc.check_stores()
        assert _levels(f) == ["error"]
        assert "corrupt" in f[0]["message"]
        assert "hermes-life-os-restore --latest --only spending" in f[0]["message"]
        assert f[0]["area"] == "spending"

    def test_truncated_file(self, doc):
        doc.storage.save_goals([{"name": "x", "target": 5}])
        path = doc.storage.data_store_path("goals")
        path.write_text(path.read_text(encoding="utf-8")[:10], encoding="utf-8")
        assert _levels(doc.check_stores()) == ["error"]

    def test_empty_file_is_corrupt(self, doc):
        doc.storage.data_store_path("habits").write_text("", encoding="utf-8")
        assert _levels(doc.check_stores()) == ["error"]

    def test_wrong_type_list_store(self, doc):
        doc.storage.data_store_path("habits").write_text('{"a": 1}', encoding="utf-8")
        msg = _messages(doc.check_stores(), "error")[0]
        assert "should hold a JSON list but holds a dict" in msg

    def test_wrong_type_dict_store(self, doc):
        doc.storage.data_store_path("profile").write_text("[1]", encoding="utf-8")
        msg = _messages(doc.check_stores(), "error")[0]
        assert "should hold a JSON object but holds a list" in msg

    def test_unreadable_bytes(self, doc):
        doc.storage.data_store_path("habits").write_bytes(b"\xff\xfe\x00bad")
        msg = _messages(doc.check_stores(), "error")[0]
        assert "cannot be read" in msg

    def test_every_problem_is_reported(self, doc):
        doc.storage.data_store_path("habits").write_text("{", encoding="utf-8")
        doc.storage.data_store_path("goals").write_text("{", encoding="utf-8")
        doc.storage.save_budgets([{"category": "x", "limit": 1}])
        f = doc.check_stores()
        assert _levels(f).count("error") == 2
        assert "ok" not in _levels(f)  # no "all healthy" line when something is wrong

    def test_encrypted_file_without_a_key(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        doc.storage.save_spending([{"amount": 1}])
        monkeypatch.delenv("LIFE_OS_ENCRYPTION_KEY")
        msg = _messages(doc.check_stores(), "error")[0]
        assert "LIFE_OS_ENCRYPTION_KEY is not set" in msg

    def test_encrypted_file_with_the_wrong_key(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "right")
        doc.storage.save_spending([{"amount": 1}])
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "wrong")
        msg = _messages(doc.check_stores(), "error")[0]
        assert "cannot be decrypted" in msg and "overwrite" in msg

    def test_encrypted_file_with_the_right_key_is_healthy(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        doc.storage.save_spending([{"amount": 1}])
        assert _levels(doc.check_stores()) == ["ok"]

    def test_plaintext_file_while_a_key_is_set_is_a_warning(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        doc.storage.save_spending([{"amount": 1}])
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        f = doc.check_stores()
        assert _levels(f) == ["warn"] and "plaintext" in f[0]["message"]

    def test_wrong_type_takes_precedence_over_plaintext_warning(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        doc.storage.data_store_path("habits").write_text('{"a": 1}', encoding="utf-8")
        assert _levels(doc.check_stores()) == ["error"]


class TestCheckMemory:
    def _write(self, doc, lines):
        doc.storage.MEMORY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_no_file(self, doc):
        assert _levels(doc.check_memory()) == ["ok"]

    def test_healthy_singular_and_plural(self, doc):
        doc.storage.write_memory({"type": "t"})
        assert "1 memory entry, all readable" in doc.check_memory()[0]["message"]
        doc.storage.write_memory({"type": "t"})
        assert "2 memory entries, all readable" in doc.check_memory()[0]["message"]

    def test_unreadable_lines_counted(self, doc):
        doc.storage.write_memory({"type": "t"})
        with open(doc.storage.MEMORY_FILE, "a", encoding="utf-8") as fh:
            fh.write("garbage line\n{also bad\n")
        f = doc.check_memory()
        assert _levels(f) == ["error"]
        assert "2 of 3 line(s)" in f[0]["message"]

    def test_blank_lines_are_ignored(self, doc):
        self._write(doc, ['{"id": "a", "type": "t"}', "", "   ", '{"id": "b", "type": "t"}'])
        assert "2 memory entries" in doc.check_memory()[0]["message"]

    def test_non_object_json_line_is_unreadable(self, doc):
        self._write(doc, ['{"id": "a"}', "[1, 2]", '"just a string"'])
        assert "2 of 3 line(s)" in _messages(doc.check_memory(), "error")[0]

    def test_duplicate_ids_warn(self, doc):
        self._write(doc, ['{"id": "a"}', '{"id": "a"}', '{"id": "b"}'])
        f = doc.check_memory()
        assert _levels(f) == ["warn"] and "1 entry id(s)" in f[0]["message"] and "a" in f[0]["message"]

    def test_entries_without_ids_are_fine(self, doc):
        self._write(doc, ['{"type": "old"}', '{"type": "old"}'])
        assert _levels(doc.check_memory()) == ["ok"]

    def test_unreadable_and_duplicates_both_reported(self, doc):
        self._write(doc, ['{"id": "a"}', '{"id": "a"}', "junk"])
        assert sorted(_levels(doc.check_memory())) == ["error", "warn"]

    def test_encrypted_memory_with_the_right_key(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        doc.storage.write_memory({"type": "t"})
        assert _levels(doc.check_memory()) == ["ok"]

    def test_encrypted_memory_with_the_wrong_key(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "right")
        doc.storage.write_memory({"type": "t"})
        doc.storage.write_memory({"type": "t"})
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "wrong")
        assert "2 of 2 line(s)" in _messages(doc.check_memory(), "error")[0]

    def test_unreadable_bytes(self, doc):
        doc.storage.MEMORY_FILE.write_bytes(b"\xff\xfe\x00not utf8\n")
        assert "cannot be read" in _messages(doc.check_memory(), "error")[0]


class TestCheckLeftovers:
    def test_none(self, doc):
        assert _levels(doc.check_leftovers()) == ["ok"]

    def test_tmp_files_warn_by_name(self, doc):
        (doc.storage.HERMES_DIR / "memory.jsonl.tmp").write_text("x", encoding="utf-8")
        (doc.storage.HERMES_DIR / "habits.json.tmp").write_text("x", encoding="utf-8")
        f = doc.check_leftovers()
        assert _levels(f) == ["warn", "warn"]
        assert any("memory.jsonl.tmp" in m for m in _messages(f))

    def test_other_files_are_not_leftovers(self, doc):
        (doc.storage.HERMES_DIR / "notes.txt").write_text("x", encoding="utf-8")
        assert _levels(doc.check_leftovers()) == ["ok"]


class TestCheckBackups:
    NOW = datetime(2026, 10, 5, 21, 0, 0)

    def test_no_data_no_backups_is_fine(self, doc):
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["ok"] and "nothing to back up" in f[0]["message"]

    def test_data_but_no_backups_warns(self, doc):
        doc.storage.save_habits([{"name": "a"}])
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["warn"] and "No backups yet" in f[0]["message"]

    def test_memory_alone_counts_as_data(self, doc):
        doc.storage.write_memory({"type": "t"})
        assert _levels(doc.check_backups(self.NOW)) == ["warn"]

    def test_fresh_complete_backup_is_ok(self, doc):
        doc.storage.save_habits([{"name": "a"}])
        doc.backup.run_backup(now=datetime(2026, 10, 5, 20, 30, 0))
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["ok"] and "readable and complete" in f[0]["message"]

    def test_stale_backup_warns(self, doc):
        doc.backup.run_backup(now=datetime(2026, 10, 1, 20, 30, 0))
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["warn"] and "4 day(s) old" in f[0]["message"]

    def test_two_day_old_backup_is_fine(self, doc):
        doc.backup.run_backup(now=datetime(2026, 10, 3, 20, 30, 0))
        assert _levels(doc.check_backups(self.NOW)) == ["ok"]

    def test_incomplete_legacy_backup_warns(self, doc):
        d = doc.backup.backups_dir()
        d.mkdir(parents=True)
        (d / "backup-2026-10-05-200000.json").write_text(json.dumps({"habits": [], "memory": []}), encoding="utf-8")
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["warn"] and "predates complete backups" in f[0]["message"]

    def test_unreadable_newest_is_an_error(self, doc):
        d = doc.backup.backups_dir()
        d.mkdir(parents=True)
        (d / "backup-2026-10-05-200000.json").write_text("garbage", encoding="utf-8")
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["error"] and "cannot be read" in f[0]["message"]

    def test_unreadable_older_backup_warns(self, doc):
        doc.backup.run_backup(now=datetime(2026, 10, 5, 20, 30, 0))
        (doc.backup.backups_dir() / "backup-2026-10-01-000000.json").write_text("garbage", encoding="utf-8")
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["warn"] and "1 older backup(s)" in f[0]["message"]

    def test_plaintext_newest_backup_while_key_is_set_warns(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        doc.backup.run_backup(now=datetime(2026, 10, 5, 20, 30, 0))
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["warn"] and "not encrypted" in f[0]["message"]

    def test_encrypted_newest_backup_with_the_key_is_ok(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        doc.backup.run_backup(now=datetime(2026, 10, 5, 20, 30, 0))
        assert _levels(doc.check_backups(self.NOW)) == ["ok"]

    def test_encrypted_newest_backup_with_the_wrong_key_is_an_error(self, doc, monkeypatch):
        pytest.importorskip("cryptography")
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "right")
        doc.backup.run_backup(now=datetime(2026, 10, 5, 20, 30, 0))
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "wrong")
        f = doc.check_backups(self.NOW)
        assert _levels(f) == ["error"] and "different passphrase" in f[0]["message"]

    def test_stale_and_incomplete_both_reported(self, doc):
        d = doc.backup.backups_dir()
        d.mkdir(parents=True)
        (d / "backup-2026-09-01-000000.json").write_text(json.dumps({"habits": []}), encoding="utf-8")
        assert _levels(doc.check_backups(self.NOW)) == ["warn", "warn"]


class TestCheckReminders:
    NOW = datetime(2026, 10, 5, 12, 0, 0)

    def test_none(self, doc):
        assert _levels(doc.check_reminders(self.NOW)) == ["ok"]

    def test_all_fine(self, doc):
        doc.storage.save_reminders([
            {"id": "a", "text": "stretch", "time": "09:00", "days": []},
            {"id": "b", "text": "note", "time": None, "days": []},
            {"id": "c", "text": "later", "time": "09:00", "days": [], "date": "2026-12-01"},
        ])
        f = doc.check_reminders(self.NOW)
        assert _levels(f) == ["ok"] and "3 reminder(s)" in f[0]["message"]

    def test_unparseable_time_warns_with_id(self, doc):
        doc.storage.save_reminders([{"id": "a", "text": "stretch", "time": "after lunch", "days": []}])
        f = doc.check_reminders(self.NOW)
        assert _levels(f) == ["warn"]
        assert "'after lunch'" in f[0]["message"] and "[a]" in f[0]["message"] and "never fire" in f[0]["message"]

    def test_paused_reminder_with_bad_time_is_not_reported(self, doc):
        doc.storage.save_reminders([{"id": "a", "text": "x", "time": "soonish", "days": [], "enabled": False}])
        assert _levels(doc.check_reminders(self.NOW)) == ["ok"]

    def test_duplicate_ids_are_an_error(self, doc):
        doc.storage.save_reminders([{"id": "a", "text": "x"}, {"id": "a", "text": "y"}])
        f = doc.check_reminders(self.NOW)
        assert "error" in _levels(f) and "a" in _messages(f, "error")[0]

    def test_past_one_offs_warn_with_count(self, doc):
        doc.storage.save_reminders([
            {"id": "a", "text": "x", "time": "09:00", "days": [], "date": "2026-10-01"},
            {"id": "b", "text": "y", "time": "09:00", "days": [], "date": "2026-10-04"},
            {"id": "c", "text": "z", "time": "09:00", "days": [], "date": "2026-10-05"},
        ])
        f = doc.check_reminders(self.NOW)
        assert _levels(f) == ["warn"] and "2 one-off reminder(s)" in f[0]["message"]
        assert "clear_past_reminders" in f[0]["message"]

    def test_real_reminders_created_through_the_module_are_clean(self, doc):
        import reminders
        importlib.reload(reminders)
        reminders.create_reminder("stretch", "9am", ["mon"])
        reminders.remind_me_in("oven", 10)
        assert "warn" not in _levels(doc.check_reminders()) and "error" not in _levels(doc.check_reminders())


class TestCheckBudgets:
    def test_none(self, doc):
        assert _levels(doc.check_budgets()) == ["ok"]

    def test_valid(self, doc):
        doc.storage.save_budgets([{"category": "food", "limit": 100, "alert_pct": 90}])
        f = doc.check_budgets()
        assert _levels(f) == ["ok"] and "1 budget(s)" in f[0]["message"]

    @pytest.mark.parametrize("bad", ["400", None, True, [], {}])
    def test_non_numeric_limit_is_an_error(self, doc, bad):
        doc.storage.save_budgets([{"category": "food", "limit": bad}])
        f = doc.check_budgets()
        assert _levels(f) == ["error"] and "non-numeric limit" in f[0]["message"]

    def test_negative_limit_warns(self, doc):
        doc.storage.save_budgets([{"category": "food", "limit": -5}])
        assert _levels(doc.check_budgets()) == ["warn"]

    def test_zero_limit_is_valid(self, doc):
        doc.storage.save_budgets([{"category": "food", "limit": 0}])
        assert _levels(doc.check_budgets()) == ["ok"]

    def test_duplicate_categories_case_insensitive(self, doc):
        doc.storage.save_budgets([{"category": "Food", "limit": 1}, {"category": "food", "limit": 2}])
        f = doc.check_budgets()
        assert _levels(f) == ["warn"] and "food" in f[0]["message"]

    @pytest.mark.parametrize("bad", ["abc", 0, 101, -3, True])
    def test_invalid_alert_pct_warns(self, doc, bad):
        doc.storage.save_budgets([{"category": "food", "limit": 100, "alert_pct": bad}])
        f = doc.check_budgets()
        assert _levels(f) == ["warn"] and "default of 80%" in f[0]["message"]


class TestRunChecks:
    def test_findings_have_the_expected_shape(self, doc):
        for f in doc.run_checks():
            assert set(f) == {"level", "area", "message"}
            assert f["level"] in ("ok", "warn", "error")

    def test_fresh_profile_has_no_errors_or_warnings(self, doc):
        assert set(_levels(doc.run_checks())) == {"ok"}

    def test_a_healthy_profile_with_everything(self, doc):
        import reminders
        importlib.reload(reminders)
        doc.storage.save_habits([{"name": "a"}])
        doc.storage.write_memory({"type": "t"})
        reminders.create_reminder("stretch", "09:00")
        doc.storage.save_budgets([{"category": "food", "limit": 100}])
        doc.backup.run_backup()
        assert set(_levels(doc.run_checks())) == {"ok"}

    def test_problems_in_several_areas_are_all_found(self, doc):
        doc.storage.data_store_path("habits").write_text("{", encoding="utf-8")
        doc.storage.save_budgets([{"category": "food", "limit": "x"}])
        (doc.storage.HERMES_DIR / "memory.jsonl.tmp").write_text("x", encoding="utf-8")
        areas = {f["area"] for f in doc.run_checks() if f["level"] != "ok"}
        assert {"habits", "budgets", "temp files", "backups"} <= areas

    def test_unusable_encryption_limits_the_checks(self, doc, monkeypatch):
        monkeypatch.setenv("LIFE_OS_ENCRYPTION_KEY", "pw")
        def boom(_):
            raise RuntimeError("no cryptography")
        monkeypatch.setattr(doc.storage, "encrypt_text", boom)
        areas = [f["area"] for f in doc.run_checks()]
        assert areas == ["encryption", "temp files"]

    def test_never_modifies_anything(self, doc):
        doc.storage.save_habits([{"name": "a"}])
        doc.storage.data_store_path("goals").write_text("{broken", encoding="utf-8")
        doc.storage.write_memory({"type": "t"})
        (doc.storage.HERMES_DIR / "memory.jsonl.tmp").write_text("x", encoding="utf-8")
        doc.backup.run_backup()
        before = _snapshot(doc.storage.HERMES_DIR)
        doc.run_checks()
        doc.run_checks()
        assert _snapshot(doc.storage.HERMES_DIR) == before


class TestSummarizeAndFormat:
    FINDINGS = [
        {"level": "ok", "area": "stores", "message": "fine"},
        {"level": "warn", "area": "backups", "message": "old"},
        {"level": "error", "area": "habits", "message": "broken"},
        {"level": "ok", "area": "memory", "message": "fine too"},
    ]

    def test_summarize(self, doc):
        assert doc.summarize(self.FINDINGS) == {"errors": 1, "warnings": 1, "ok": 2}

    def test_summarize_empty(self, doc):
        assert doc.summarize([]) == {"errors": 0, "warnings": 0, "ok": 0}

    def test_report_lists_errors_then_warnings_then_ok(self, doc):
        out = doc.format_report(self.FINDINGS)
        assert out.index("[ERROR]") < out.index("[WARN]") < out.index("[OK]")

    def test_report_verdicts(self, doc):
        assert "1 error(s) and 1 warning(s) found - fix the errors first." in doc.format_report(self.FINDINGS)
        assert "No errors, 1 warning(s)." in doc.format_report([self.FINDINGS[0], self.FINDINGS[1]])
        assert "Everything looks healthy." in doc.format_report([self.FINDINGS[0]])

    def test_report_names_the_profile(self, doc):
        doc.storage.set_active_profile("alex")
        assert "profile 'alex'" in doc.format_report([])

    def test_report_is_plain_ascii(self, doc):
        doc.storage.data_store_path("habits").write_text("{", encoding="utf-8")
        doc.storage.save_budgets([{"category": "food", "limit": "x"}])
        assert doc.format_report(doc.run_checks()).isascii()


class TestMainCLI:
    def test_healthy_exits_zero(self, doc, capsys):
        assert doc.main([]) == 0
        assert "health check" in capsys.readouterr().out

    def test_warnings_alone_exit_zero(self, doc, capsys):
        doc.storage.save_habits([{"name": "a"}])  # data, no backup -> a warning
        assert doc.main([]) == 0
        assert "[WARN]" in capsys.readouterr().out

    def test_errors_exit_one(self, doc, capsys):
        doc.storage.data_store_path("habits").write_text("{", encoding="utf-8")
        assert doc.main([]) == 1
        assert "[ERROR]" in capsys.readouterr().out

    def test_strict_makes_warnings_fail(self, doc):
        doc.storage.save_habits([{"name": "a"}])
        assert doc.main(["--strict"]) == 1

    def test_strict_with_no_warnings_passes(self, doc):
        assert doc.main(["--strict"]) == 0

    def test_json_output(self, doc, capsys):
        doc.storage.save_habits([{"name": "a"}])
        assert doc.main(["--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["profile"] == "default"
        assert payload["summary"]["warnings"] == 1
        assert all({"level", "area", "message"} == set(f) for f in payload["findings"])

    def test_profile_flag(self, doc, capsys):
        doc.main(["--profile", "alex"])
        assert doc.storage.ACTIVE_PROFILE == "alex"
        assert "profile 'alex'" in capsys.readouterr().out

    def test_profile_from_environment(self, doc, capsys, monkeypatch):
        monkeypatch.setenv("LIFE_OS_PROFILE", "sam")
        doc.main([])
        assert doc.storage.ACTIVE_PROFILE == "sam"

    def test_checks_the_named_profile_not_the_default(self, doc):
        doc.storage.save_habits([{"name": "default data"}])
        doc.storage.data_store_path("habits").write_text("{", encoding="utf-8")
        assert doc.main(["--profile", "clean"]) == 0
        assert doc.main(["--profile", "default"]) == 1
