"""Shared pytest setup."""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_day_start(monkeypatch):
    """A LIFE_OS_DAY_START_HOUR set in the developer's own shell would shift
    "today" for every test; tests that care set it themselves."""
    monkeypatch.delenv("LIFE_OS_DAY_START_HOUR", raising=False)


import importlib
import sys
from datetime import datetime
from pathlib import Path

DEMO_DIR = Path(__file__).parent.parent / "demo"
sys.path.insert(0, str(DEMO_DIR))

PLANNER_NOW = datetime(2026, 10, 13, 9, 0)  # a Tuesday


@pytest.fixture()
def planner(tmp_path, monkeypatch):
    """tools.py with every demo module freshly imported against a temp HOME and the
    clock frozen at Tuesday 2026-10-13 09:00. Call planner.dispatch_tool(name, args);
    planner.set_now(datetime) moves the clock."""
    import clock
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None) or ""
        if path.startswith(str(DEMO_DIR)) and name != "clock":
            del sys.modules[name]
    state = {"now": PLANNER_NOW}
    monkeypatch.setattr(clock, "now", lambda: state["now"])
    import tools
    importlib.reload(tools)
    import storage
    storage.set_active_profile(None)
    tools.set_now = lambda when: state.__setitem__("now", when)
    return tools
