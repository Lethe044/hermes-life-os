"""Tests for demo/data_export.py - JSON backup and CSV summary export."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def data_export(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "data_export"):
        if mod in sys.modules:
            del sys.modules[mod]
    import data_export as de
    importlib.reload(de)
    return de


def _seed(storage, n_days=3):
    for i in range(1, n_days + 1):
        ts = f"2026-01-0{i}T09:00:00Z"
        with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "mood", "score": i + 4, "timestamp": ts}) + "\n")
            f.write(json.dumps({"type": "sleep", "hours": 6 + i, "timestamp": ts}) + "\n")


class TestExportJson:
    def test_empty_export_has_all_sections(self, data_export, tmp_path):
        out = tmp_path / "backup.json"
        count = data_export.export_json(str(out))
        assert count == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert set(payload.keys()) == {
            "profile", "habits", "goals", "nutrition", "sleep",
            "hydration", "fitness", "focus", "mental", "memory",
        }
        assert payload["memory"] == []

    def test_exports_all_memory_entries(self, data_export, tmp_path):
        _seed(data_export.storage, n_days=3)
        out = tmp_path / "backup.json"
        count = data_export.export_json(str(out))
        assert count == 6  # 3 days x 2 entries

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert len(payload["memory"]) == 6

    def test_exports_habits_and_goals(self, data_export, tmp_path):
        data_export.storage.save_habits([{"name": "run", "streak": 5}])
        data_export.storage.save_goals([{"name": "sleep well", "progress": 80}])
        out = tmp_path / "backup.json"
        data_export.export_json(str(out))
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["habits"] == [{"name": "run", "streak": 5}]
        assert payload["goals"] == [{"name": "sleep well", "progress": 80}]


class TestExportCsv:
    def test_empty_export_has_only_header(self, data_export, tmp_path):
        out = tmp_path / "summary.csv"
        count = data_export.export_csv(str(out))
        assert count == 0
        content = out.read_text(encoding="utf-8")
        assert content.strip() == "date,sleep_hours,mood,stress,energy,hydration"

    def test_one_row_per_day(self, data_export, tmp_path):
        _seed(data_export.storage, n_days=3)
        out = tmp_path / "summary.csv"
        count = data_export.export_csv(str(out))
        assert count == 3
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 4  # header + 3 days

    def test_values_correct_and_blank_when_missing(self, data_export, tmp_path):
        import csv as csv_module
        _seed(data_export.storage, n_days=1)  # only mood + sleep, no stress/energy/hydration
        out = tmp_path / "summary.csv"
        data_export.export_csv(str(out))

        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv_module.DictReader(f))
        assert rows[0]["date"] == "2026-01-01"
        assert rows[0]["sleep_hours"] == "7.0"
        assert rows[0]["mood"] == "5.0"
        assert rows[0]["stress"] == ""  # not logged that day


class TestExportMarkdown:
    def test_no_data_writes_nothing(self, data_export, tmp_path):
        out_dir = tmp_path / "vault"
        count = data_export.export_markdown(str(out_dir))
        assert count == 0
        assert out_dir.exists()  # directory still created
        assert list(out_dir.glob("*.md")) == []

    def test_one_file_per_day(self, data_export, tmp_path):
        _seed(data_export.storage, n_days=3)
        out_dir = tmp_path / "vault"
        count = data_export.export_markdown(str(out_dir))
        assert count == 3
        assert (out_dir / "2026-01-01.md").exists()
        assert (out_dir / "2026-01-02.md").exists()
        assert (out_dir / "2026-01-03.md").exists()

    def test_frontmatter_contains_metrics(self, data_export, tmp_path):
        _seed(data_export.storage, n_days=1)
        out_dir = tmp_path / "vault"
        data_export.export_markdown(str(out_dir))
        content = (out_dir / "2026-01-01.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "mood:" in content
        assert "sleep:" in content
        assert "tags: hermes-life-os" in content

    def test_body_lists_entries_with_type_and_content(self, data_export, tmp_path):
        data_export.storage.write_memory({
            "type": "mood", "content": "felt great", "score": 8,
            "timestamp": "2026-02-01T09:00:00Z",
        })
        out_dir = tmp_path / "vault"
        data_export.export_markdown(str(out_dir))
        content = (out_dir / "2026-02-01.md").read_text(encoding="utf-8")
        assert "# 2026-02-01" in content
        assert "**mood**: felt great" in content

    def test_days_limits_to_recent_window(self, data_export, tmp_path):
        import time as time_module
        # One very old entry (outside any reasonable "recent" window)
        # plus a "now" entry - only the second should be included when
        # `days` is passed.
        data_export.storage.write_memory({
            "type": "mood", "content": "ancient", "score": 5,
            "timestamp": "2000-01-01T09:00:00Z",
        })
        data_export.storage.write_memory({"type": "mood", "content": "recent", "score": 7})

        out_dir = tmp_path / "vault"
        count = data_export.export_markdown(str(out_dir), days=7)
        assert count == 1  # only today's entry

    def test_creates_output_directory(self, data_export, tmp_path):
        nested = tmp_path / "a" / "b" / "vault"
        data_export.export_markdown(str(nested))
        assert nested.exists()

    def test_multiline_content_flattened_to_one_line(self, data_export, tmp_path):
        data_export.storage.write_memory({
            "type": "mood", "content": "line one\nline two", "score": 6,
            "timestamp": "2026-03-01T09:00:00Z",
        })
        out_dir = tmp_path / "vault"
        data_export.export_markdown(str(out_dir))
        content = (out_dir / "2026-03-01.md").read_text(encoding="utf-8")
        assert "line one line two" in content


class TestExportImportRoundTrip:
    def test_exported_csv_is_reimportable(self, data_export, tmp_path):
        """The whole point of a symmetric CSV format: export, then feed
        the same file straight into health_import.py's --csv importer."""
        import health_import
        importlib.reload(health_import)

        _seed(data_export.storage, n_days=2)
        out = tmp_path / "summary.csv"
        data_export.export_csv(str(out))

        # wipe and re-import into the same (now-empty) store
        data_export.storage.set_active_profile("reimported")
        count = health_import.import_csv(str(out))
        assert count > 0

        entries = data_export.storage.get_recent_memory(days=3650)
        types = {e["type"] for e in entries}
        assert "mood" in types and "sleep" in types


class TestMainCli:
    def test_requires_at_least_one_format(self, data_export, capsys):
        with pytest.raises(SystemExit):
            sys.argv = ["data_export.py"]
            data_export.main()

    def test_writes_both_formats_via_cli(self, data_export, tmp_path):
        _seed(data_export.storage, n_days=2)
        json_out = tmp_path / "b.json"
        csv_out = tmp_path / "s.csv"
        sys.argv = ["data_export.py", "--json", str(json_out), "--csv", str(csv_out)]
        data_export.main()
        assert json_out.exists()
        assert csv_out.exists()

    def test_profile_flag_exports_correct_profile(self, data_export, tmp_path):
        data_export.storage.set_active_profile("alex")
        data_export.storage.write_memory({"type": "mood", "score": 9})
        data_export.storage.set_active_profile(None)

        out = tmp_path / "alex-backup.json"
        sys.argv = ["data_export.py", "--json", str(out), "--profile", "alex"]
        data_export.main()

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert len(payload["memory"]) == 1
        assert payload["memory"][0]["score"] == 9

    def test_markdown_flag_via_cli(self, data_export, tmp_path):
        _seed(data_export.storage, n_days=2)
        out_dir = tmp_path / "vault"
        sys.argv = ["data_export.py", "--markdown", str(out_dir)]
        data_export.main()
        assert len(list(out_dir.glob("*.md"))) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
