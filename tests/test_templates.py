"""Tests for demo/templates.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def templates(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "templates"):
        if mod in sys.modules:
            del sys.modules[mod]
    import templates as t
    importlib.reload(t)
    import storage
    storage.set_active_profile(None)
    return t


class TestSaveAndGetTemplate:
    def test_get_nonexistent_returns_none(self, templates):
        assert templates.get_template("usual breakfast") is None

    def test_save_and_get_roundtrip(self, templates):
        templates.save_template("usual breakfast", "log_meal", {"food": "oatmeal", "calories": 300})
        result = templates.get_template("usual breakfast")
        assert result == {"tool_name": "log_meal", "params": {"food": "oatmeal", "calories": 300}}

    def test_get_case_insensitive(self, templates):
        templates.save_template("Usual Breakfast", "log_meal", {"food": "oatmeal"})
        assert templates.get_template("usual breakfast") is not None

    def test_save_overwrites_existing(self, templates):
        templates.save_template("usual breakfast", "log_meal", {"food": "oatmeal"})
        templates.save_template("usual breakfast", "log_meal", {"food": "eggs"})
        result = templates.get_template("usual breakfast")
        assert result["params"] == {"food": "eggs"}


class TestListTemplates:
    def test_empty_list(self, templates):
        assert templates.list_templates() == []

    def test_lists_all_sorted_alphabetically(self, templates):
        templates.save_template("zebra run", "log_workout", {"workout_type": "run"})
        templates.save_template("apple snack", "log_meal", {"food": "apple"})
        result = templates.list_templates()
        assert [t["name"] for t in result] == ["apple snack", "zebra run"]

    def test_list_includes_tool_name_and_params(self, templates):
        templates.save_template("usual breakfast", "log_meal", {"food": "oatmeal"})
        result = templates.list_templates()
        assert result[0]["tool_name"] == "log_meal"
        assert result[0]["params"] == {"food": "oatmeal"}


class TestDeleteTemplate:
    def test_delete_nonexistent_returns_false(self, templates):
        assert templates.delete_template("usual breakfast") is False

    def test_delete_existing_returns_true(self, templates):
        templates.save_template("usual breakfast", "log_meal", {"food": "oatmeal"})
        assert templates.delete_template("usual breakfast") is True
        assert templates.get_template("usual breakfast") is None

    def test_delete_case_insensitive(self, templates):
        templates.save_template("Usual Breakfast", "log_meal", {"food": "oatmeal"})
        assert templates.delete_template("usual breakfast") is True


class TestFormatTemplateList:
    def test_empty_list_message(self, templates):
        text = templates.format_template_list([])
        assert "No log templates saved" in text

    def test_with_data_shows_tool_and_params(self, templates):
        result = [{"name": "usual breakfast", "tool_name": "log_meal",
                    "params": {"food": "oatmeal", "calories": 300}}]
        text = templates.format_template_list(result)
        assert "usual breakfast: log_meal(food=oatmeal, calories=300)" in text
