"""docs/TOOLS.md is generated from the schemas and must stay in sync."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_tool_reference_is_up_to_date(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "demo" / "toolsdoc.py"), "--check"],
                            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert result.returncode == 0, "docs/TOOLS.md is out of date: run `python demo/toolsdoc.py`"


def test_every_tool_is_listed_once(planner):
    import toolsdoc
    text = toolsdoc.render()
    for schema in planner.TOOLS:
        name = schema["function"]["name"]
        assert text.count(f"| `{name}` |") <= 1
    for name in ("plan_my_day", "export_calendar", "add_library_item", "log_life_wheel", "add_priority"):
        assert f"| `{name}` |" in text


def test_no_pipe_breaks_the_table():
    import toolsdoc
    for line in toolsdoc.render().splitlines():
        if line.startswith("| `"):
            assert line.count("|") == 4
