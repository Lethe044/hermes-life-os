"""Tests for demo/export_tool.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def export_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "data_export", "export_tool"):
        if mod in sys.modules:
            del sys.modules[mod]
    import export_tool as et
    importlib.reload(et)
    import storage
    storage.set_active_profile(None)
    return et


class TestRunExport:
    def test_invalid_format_raises(self, export_tool):
        with pytest.raises(ValueError):
            export_tool.run_export("xml")

    def test_json_export_writes_file(self, export_tool):
        import storage
        storage.write_memory({"type": "mood", "content": "ok", "score": 5})
        result = export_tool.run_export("json")
        assert result["format"] == "json"
        assert Path(result["path"]).exists()
        assert result["count"] == 1

    def test_csv_export_writes_file(self, export_tool):
        import storage
        storage.write_memory({"type": "mood", "content": "ok", "score": 5,
                               "timestamp": "2026-01-01T10:00:00Z"})
        result = export_tool.run_export("csv")
        assert result["format"] == "csv"
        assert Path(result["path"]).exists()
        assert Path(result["path"]).suffix == ".csv"

    def test_markdown_export_writes_directory(self, export_tool):
        import storage
        storage.write_memory({"type": "mood", "content": "ok", "score": 5,
                               "timestamp": "2026-01-01T10:00:00Z"})
        result = export_tool.run_export("markdown")
        assert result["format"] == "markdown"
        assert Path(result["path"]).is_dir()
        assert result["count"] == 1

    def test_exports_land_in_exports_subdirectory(self, export_tool):
        result = export_tool.run_export("json")
        assert "exports" in Path(result["path"]).parts

    def test_default_format_is_json(self, export_tool):
        result = export_tool.run_export()
        assert result["format"] == "json"


class TestFormatExportResult:
    def test_json_message(self, export_tool):
        result = {"format": "json", "path": "/tmp/x.json", "count": 5}
        text = export_tool.format_export_result(result)
        assert "5 memory entries" in text
        assert "/tmp/x.json" in text

    def test_csv_message(self, export_tool):
        result = {"format": "csv", "path": "/tmp/x.csv", "count": 3}
        text = export_tool.format_export_result(result)
        assert "3 daily rows" in text

    def test_markdown_message(self, export_tool):
        result = {"format": "markdown", "path": "/tmp/x", "count": 2}
        text = export_tool.format_export_result(result)
        assert "2 day-files" in text
