"""
Hermes Life OS - Plugin System
================================
Drop a .py file into ~/.hermes/life-os/plugins/ (or point
LIFE_OS_PLUGINS_DIR somewhere else) and Hermes picks it up automatically
next run - new tools the LLM agent can call, with zero core code changes
and no fork required.

A plugin is just a normal Python module that defines:

    TOOLS: list[dict]
        Same schema as demo/tools.py's TOOLS list - one entry per new
        tool, in OpenAI function-calling format.

    def dispatch(name: str, inp: dict) -> str | None:
        Called for every tool call Hermes doesn't recognize as a
        built-in. Return a string result if this plugin handles
        `name`, or None to let Hermes fall through to the next plugin.

Optional:
    PLUGIN_NAME: str        - shown in `python demo/plugins.py list` and
                               in any load-error messages. Defaults to
                               the filename (without .py) if omitted.

Minimal example - a plugin that adds a "roll_dice" tool:

    # ~/.hermes/life-os/plugins/dice.py
    import random

    PLUGIN_NAME = "dice"

    TOOLS = [
        {"type": "function", "function": {
            "name": "roll_dice",
            "description": "Roll an N-sided die.",
            "parameters": {"type": "object", "properties": {
                "sides": {"type": "integer", "description": "Default 6."},
            }, "required": []},
        }},
    ]

    def dispatch(name, inp):
        if name == "roll_dice":
            sides = int(inp.get("sides") or 6)
            return f"Rolled a {sides}-sided die: {random.randint(1, sides)}"
        return None  # not one of ours - let Hermes keep looking

See docs/PLUGINS.md for a longer walkthrough (state, calling other
tools' storage helpers, packaging a plugin for others to install) and
demo/plugins_examples/ for two more complete examples.

Safety model - please read before installing someone else's plugin:
    - Plugins run with full Python privileges in this process, exactly
      like any other Python file you'd run yourself. Only install
      plugins you wrote or trust, the same rule as `pip install`.
    - A plugin that fails to import (syntax error, missing dependency,
      exception at module level) is skipped and reported - it never
      crashes the rest of Hermes.
    - A plugin tool name that collides with a *built-in* tool name is
      dropped and reported; built-ins always win, so a bad plugin can
      never shadow core functionality like `remember` or `log_sleep`.
    - Two plugins defining the same tool name: the first one loaded
      (alphabetical by filename) wins, and the collision is reported so
      it's easy to notice and rename.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

DispatchFn = Callable[[str, Dict[str, Any]], Optional[str]]


def plugins_dir() -> Path:
    """Where plugin .py files are discovered. Override with
    LIFE_OS_PLUGINS_DIR (e.g. to share a plugins folder across
    profiles, or point at a synced/version-controlled directory).
    Default: ~/.hermes/life-os/plugins/ - a sibling of the profile
    data, so it survives profile switches."""
    override = os.environ.get("LIFE_OS_PLUGINS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".hermes" / "life-os" / "plugins"


def discover_plugin_files(directory: Optional[Path] = None) -> List[Path]:
    """Every top-level *.py file in the plugins directory, alphabetical
    by filename (this order also decides collision winners). Files
    starting with '_' are ignored (handy for a local
    "_scratch.py" that isn't ready yet, or shared helper modules a
    plugin imports itself)."""
    directory = directory or plugins_dir()
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.glob("*.py")
        if p.is_file() and not p.name.startswith("_")
    )


def load_plugin_module(path: Path):
    """Imports a single plugin file as its own isolated module (named
    hermes_life_os_plugin_<stem> so it can never collide with a real
    package). Raises on failure - callers decide how to report that;
    load_plugins() below catches everything so one bad plugin can't
    take the rest of the app down."""
    module_name = f"hermes_life_os_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_plugins(
    directory: Optional[Path] = None,
    built_in_names: Optional[Set[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Tuple[str, DispatchFn]], List[str]]:
    """Loads every plugin in `directory` (default: plugins_dir()).
    Never raises - a broken plugin is reported in the returned
    `errors` list and simply skipped.

    Returns (tools, dispatchers, errors):
        tools       - TOOLS-schema dicts ready to append to the
                      built-in TOOLS list. Entries colliding with
                      built_in_names (or an earlier-loaded plugin) are
                      dropped and explained in `errors` instead.
        dispatchers - ordered [(plugin_name, dispatch_fn), ...],
                      tried in this order by dispatch_plugin_tool().
        errors      - human-readable strings describing anything that
                      failed to load or was skipped, for logging/CLI
                      display. Empty list means a fully clean load.
    """
    built_in_names = set(built_in_names or ())
    tools: List[Dict[str, Any]] = []
    dispatchers: List[Tuple[str, DispatchFn]] = []
    errors: List[str] = []
    seen_names = set(built_in_names)

    for path in discover_plugin_files(directory):
        try:
            module = load_plugin_module(path)
        except Exception as e:  # noqa: BLE001 - a plugin can raise literally anything
            errors.append(f"{path.name}: failed to load - {e}")
            continue

        plugin_name = getattr(module, "PLUGIN_NAME", path.stem)
        dispatch_fn = getattr(module, "dispatch", None)
        if not callable(dispatch_fn):
            errors.append(f"{path.name}: no dispatch(name, inp) function found - skipped")
            continue

        plugin_tools = getattr(module, "TOOLS", [])
        if not isinstance(plugin_tools, list):
            errors.append(f"{path.name}: TOOLS must be a list - skipped")
            continue

        accepted: List[Dict[str, Any]] = []
        for tool in plugin_tools:
            try:
                tool_name = tool["function"]["name"]
            except (KeyError, TypeError):
                errors.append(f"{path.name}: malformed TOOLS entry (missing function.name) - skipped")
                continue
            if tool_name in seen_names:
                reason = "a built-in tool" if tool_name in built_in_names else "an earlier plugin"
                errors.append(
                    f"{path.name}: tool '{tool_name}' collides with {reason} - skipped"
                )
                continue
            seen_names.add(tool_name)
            accepted.append(tool)

        tools.extend(accepted)
        # Registered even with zero accepted tools (e.g. a plugin that
        # only overrides behavior via dispatch for now) - dispatch is
        # still tried, harmlessly returning None for anything it
        # doesn't recognize.
        dispatchers.append((plugin_name, dispatch_fn))

    return tools, dispatchers, errors


def dispatch_plugin_tool(
    name: str, inp: Dict[str, Any], dispatchers: List[Tuple[str, DispatchFn]]
) -> Optional[str]:
    """Tries each loaded plugin's dispatch() in load order until one
    returns a non-None result. A plugin that raises doesn't crash the
    caller - the exception is turned into an error string result
    instead, clearly attributed to the plugin that raised it."""
    for plugin_name, fn in dispatchers:
        try:
            result = fn(name, inp)
        except Exception as e:  # noqa: BLE001
            return f"Plugin '{plugin_name}' raised an error handling '{name}': {e}"
        if result is not None:
            return result
    return None


def main() -> None:
    """`python demo/plugins.py` - lists every discovered plugin, the
    tools it contributes, and any load errors. Useful after dropping a
    new file in the plugins folder to confirm it was picked up (and
    why, if it wasn't)."""
    directory = plugins_dir()
    print(f"Plugins directory: {directory}")
    if not directory.is_dir():
        print("(directory does not exist yet - create it and drop a .py file in)")
        return

    tools, dispatchers, errors = load_plugins(directory)
    if not dispatchers and not errors:
        print("No plugins found.")
    for plugin_name, _fn in dispatchers:
        print(f"  \u2713 {plugin_name}")
    if tools:
        print("\nTools contributed:")
        for t in tools:
            fn = t.get("function", {})
            print(f"  - {fn.get('name')}: {fn.get('description', '')}")
    if errors:
        print("\nWarnings/errors:")
        for e in errors:
            print(f"  ! {e}")


if __name__ == "__main__":
    main()
