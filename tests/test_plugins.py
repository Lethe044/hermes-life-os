"""Tests for demo/plugins.py - the plugin discovery/loading/dispatch
system. Uses temp directories for plugin files so nothing here touches
a real ~/.hermes install."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

import plugins  # noqa: E402


def write_plugin(directory: Path, filename: str, source: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


GOOD_PLUGIN = """
    PLUGIN_NAME = "greeter"

    TOOLS = [
        {"type": "function", "function": {
            "name": "say_hello",
            "description": "Says hello.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }},
    ]

    def dispatch(name, inp):
        if name == "say_hello":
            return "Hello from the plugin!"
        return None
"""

BROKEN_IMPORT_PLUGIN = """
    this is not valid python (((
"""

NO_DISPATCH_PLUGIN = """
    TOOLS = []
"""

MALFORMED_TOOLS_PLUGIN = """
    TOOLS = [{"not": "a valid schema entry"}]

    def dispatch(name, inp):
        return None
"""

COLLIDING_PLUGIN = """
    PLUGIN_NAME = "collider"

    TOOLS = [
        {"type": "function", "function": {
            "name": "remember",
            "description": "Tries to shadow a built-in tool.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }},
    ]

    def dispatch(name, inp):
        return None
"""


class TestDiscovery:
    def test_no_directory_returns_empty(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        assert plugins.discover_plugin_files(missing) == []

    def test_discovers_py_files_alphabetically(self, tmp_path):
        write_plugin(tmp_path, "b.py", GOOD_PLUGIN)
        write_plugin(tmp_path, "a.py", GOOD_PLUGIN)
        found = plugins.discover_plugin_files(tmp_path)
        assert [p.name for p in found] == ["a.py", "b.py"]

    def test_ignores_underscore_prefixed_files(self, tmp_path):
        write_plugin(tmp_path, "_scratch.py", GOOD_PLUGIN)
        assert plugins.discover_plugin_files(tmp_path) == []

    def test_ignores_non_py_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hi", encoding="utf-8")
        assert plugins.discover_plugin_files(tmp_path) == []

    def test_plugins_dir_respects_env_override(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom-plugins"
        monkeypatch.setenv("LIFE_OS_PLUGINS_DIR", str(custom))
        assert plugins.plugins_dir() == custom

    def test_plugins_dir_default_lives_under_home(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LIFE_OS_PLUGINS_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert plugins.plugins_dir() == tmp_path / ".hermes" / "life-os" / "plugins"


class TestLoadPlugins:
    def test_loads_a_well_formed_plugin(self, tmp_path):
        write_plugin(tmp_path, "greeter.py", GOOD_PLUGIN)
        tools, dispatchers, errors = plugins.load_plugins(tmp_path)
        assert errors == []
        assert len(dispatchers) == 1
        assert dispatchers[0][0] == "greeter"
        assert [t["function"]["name"] for t in tools] == ["say_hello"]

    def test_dispatch_fn_actually_works(self, tmp_path):
        write_plugin(tmp_path, "greeter.py", GOOD_PLUGIN)
        _tools, dispatchers, _errors = plugins.load_plugins(tmp_path)
        result = plugins.dispatch_plugin_tool("say_hello", {}, dispatchers)
        assert result == "Hello from the plugin!"

    def test_unhandled_tool_returns_none(self, tmp_path):
        write_plugin(tmp_path, "greeter.py", GOOD_PLUGIN)
        _tools, dispatchers, _errors = plugins.load_plugins(tmp_path)
        assert plugins.dispatch_plugin_tool("nonexistent_tool", {}, dispatchers) is None

    def test_broken_plugin_is_skipped_not_raised(self, tmp_path):
        write_plugin(tmp_path, "broken.py", BROKEN_IMPORT_PLUGIN)
        tools, dispatchers, errors = plugins.load_plugins(tmp_path)
        assert tools == []
        assert dispatchers == []
        assert len(errors) == 1
        assert "broken.py" in errors[0]

    def test_plugin_without_dispatch_is_skipped(self, tmp_path):
        write_plugin(tmp_path, "nodispatch.py", NO_DISPATCH_PLUGIN)
        tools, dispatchers, errors = plugins.load_plugins(tmp_path)
        assert dispatchers == []
        assert "no dispatch" in errors[0]

    def test_malformed_tool_entry_is_dropped_but_plugin_still_loads(self, tmp_path):
        write_plugin(tmp_path, "malformed.py", MALFORMED_TOOLS_PLUGIN)
        tools, dispatchers, errors = plugins.load_plugins(tmp_path)
        assert tools == []
        assert len(dispatchers) == 1  # dispatch() still registered
        assert "malformed TOOLS entry" in errors[0]

    def test_collision_with_built_in_tool_is_dropped(self, tmp_path):
        write_plugin(tmp_path, "collider.py", COLLIDING_PLUGIN)
        tools, dispatchers, errors = plugins.load_plugins(
            tmp_path, built_in_names={"remember"}
        )
        assert tools == []
        assert len(dispatchers) == 1  # dispatch() itself is still wired up
        assert "collides with a built-in tool" in errors[0]

    def test_collision_between_two_plugins_first_wins(self, tmp_path):
        write_plugin(tmp_path, "a_first.py", GOOD_PLUGIN)
        write_plugin(tmp_path, "b_second.py", GOOD_PLUGIN.replace("greeter", "greeter2"))
        tools, dispatchers, errors = plugins.load_plugins(tmp_path)
        # both plugins loaded (dispatch registered for each)...
        assert len(dispatchers) == 2
        # ...but only the first plugin's say_hello tool schema survives
        assert len(tools) == 1
        assert any("collides with an earlier plugin" in e for e in errors)

    def test_one_broken_plugin_does_not_block_others(self, tmp_path):
        write_plugin(tmp_path, "a_broken.py", BROKEN_IMPORT_PLUGIN)
        write_plugin(tmp_path, "b_good.py", GOOD_PLUGIN)
        tools, dispatchers, errors = plugins.load_plugins(tmp_path)
        assert len(dispatchers) == 1
        assert dispatchers[0][0] == "greeter"
        assert len(errors) == 1

    def test_plugin_that_raises_at_call_time_is_reported_not_fatal(self, tmp_path):
        write_plugin(tmp_path, "raiser.py", """
            PLUGIN_NAME = "raiser"
            TOOLS = []
            def dispatch(name, inp):
                raise ValueError("boom")
        """)
        _tools, dispatchers, _errors = plugins.load_plugins(tmp_path)
        result = plugins.dispatch_plugin_tool("anything", {}, dispatchers)
        assert result is not None
        assert "raiser" in result
        assert "boom" in result

    def test_empty_directory_returns_empty_everything(self, tmp_path):
        tools, dispatchers, errors = plugins.load_plugins(tmp_path)
        assert (tools, dispatchers, errors) == ([], [], [])


class TestToolsIntegration:
    """Confirms tools.py actually merges plugin tools/dispatch in, using
    the real plugins_examples/ files shipped with the repo."""

    def test_example_plugins_load_cleanly(self, tmp_path, monkeypatch):
        examples_dir = Path(__file__).parent.parent / "demo" / "plugins_examples"
        tools, dispatchers, errors = plugins.load_plugins(examples_dir)
        assert errors == []
        names = {name for name, _fn in dispatchers}
        assert names == {"dice", "screen_time"}
        tool_names = {t["function"]["name"] for t in tools}
        assert {"roll_dice", "flip_coin", "log_screen_time", "get_screen_time_summary"} <= tool_names

    def test_dice_plugin_dispatch(self, tmp_path):
        examples_dir = Path(__file__).parent.parent / "demo" / "plugins_examples"
        _tools, dispatchers, _errors = plugins.load_plugins(examples_dir)
        result = plugins.dispatch_plugin_tool("flip_coin", {}, dispatchers)
        assert result in ("Heads", "Tails")

    def test_tools_module_merges_installed_plugin(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("LIFE_OS_PLUGINS_DIR", raising=False)
        plugin_dir = tmp_path / ".hermes" / "life-os" / "plugins"
        write_plugin(plugin_dir, "greeter.py", GOOD_PLUGIN)

        for mod in ("storage", "patterns", "analytics", "plugins", "tools"):
            if mod in sys.modules:
                del sys.modules[mod]
        import tools as tools_mod

        tool_names = {t["function"]["name"] for t in tools_mod.TOOLS}
        assert "say_hello" in tool_names
        assert tools_mod.dispatch_tool("say_hello", {}) == "Hello from the plugin!"
        assert tools_mod.dispatch_tool("totally_unknown_tool", {}) == "Unknown tool: totally_unknown_tool"

    def test_reload_plugins_picks_up_new_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("LIFE_OS_PLUGINS_DIR", raising=False)

        for mod in ("storage", "patterns", "analytics", "plugins", "tools"):
            if mod in sys.modules:
                del sys.modules[mod]
        import tools as tools_mod

        assert "say_hello" not in {t["function"]["name"] for t in tools_mod.TOOLS}

        plugin_dir = tmp_path / ".hermes" / "life-os" / "plugins"
        write_plugin(plugin_dir, "greeter.py", GOOD_PLUGIN)
        tools_mod.reload_plugins()

        assert "say_hello" in {t["function"]["name"] for t in tools_mod.TOOLS}
        assert tools_mod.dispatch_tool("say_hello", {}) == "Hello from the plugin!"
