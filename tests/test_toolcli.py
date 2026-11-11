"""The tool command line and the version flags."""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cli(planner, monkeypatch, capsys):
    import toolcli
    import storage

    def run(*argv, stdin=None):
        if stdin is not None:
            monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        code = toolcli.main(list(argv))
        out = capsys.readouterr()
        return code, out.out, out.err
    yield run
    storage.set_active_profile(None)


def test_list_and_match(cli):
    code, out, _ = cli("list")
    assert code == 0 and "add_task" in out and re.search(r"\d+ of \d+ tools", out)
    code, out, _ = cli("list", "--match", "flashcard")
    assert "add_flashcards" in out and "add_task" not in out
    assert "No tool matches 'zzzz'" in cli("list", "--match", "zzzz")[1]


def test_show(cli):
    code, out, _ = cli("show", "add_task")
    assert code == 0 and "text* (string)" in out and "priority (high/normal/low)" in out
    assert "Example: hermes-life-os-tool run add_task text=<text>" in out
    assert "No parameters." in cli("show", "get_inbox")[1]


def test_run_with_pairs_json_and_stdin(cli):
    code, out, _ = cli("run", "add_task", "text=Pay rent", "due=friday", "minutes=45")
    assert code == 0 and "Task added" in out and "~45 min" in out
    code, out, _ = cli("run", "add_task", "--json", '{"text": "From json", "priority": "high"}')
    assert "!high From json" in out
    code, out, _ = cli("run", "log_life_wheel", "--json", "-", stdin='{"scores": {"health": 7}}')
    assert "health" in out and "7/10" in out
    code, out, _ = cli("run", "add_task", "--json", '{"text": "old"}', "text=new")
    assert "new" in out and "old" not in out


def test_value_parsing():
    import toolcli
    assert toolcli.parse_pairs(["a=1", "b=true", 'c=["x"]', "d=plain text", "e=", "f=a=b"]) == \
        {"a": 1, "b": True, "c": ["x"], "d": "plain text", "e": "", "f": "a=b"}
    for bad in ("novalue", "=x"):
        with pytest.raises(ValueError):
            toolcli.parse_pairs([bad])


def test_errors_exit_with_status_one(cli):
    code, _, err = cli("run", "nope")
    assert code == 1 and "Unknown tool 'nope'" in err
    code, _, err = cli("run", "add_task", "text")
    assert code == 1 and "not key=value" in err
    code, _, err = cli("run", "add_task", "--json", "[1]")
    assert code == 1 and "must be a JSON object" in err
    code, _, err = cli("run", "add_task", "--json", "{oops")
    assert code == 1 and "not valid JSON" in err
    code, _, err = cli("show", "add_tas")
    assert code == 1 and "Did you mean: add_task" in err


def test_tool_errors_are_printed_not_raised(cli):
    code, out, _ = cli("run", "add_task", "text=")
    assert code == 0 and out.startswith("Task not added")


def test_profile_flag_isolates_data(cli):
    cli("--profile", "alex", "run", "add_task", "text=Alex only")
    import storage
    storage.set_active_profile(None)
    assert "Alex only" not in cli("run", "list_tasks")[1]
    assert "Alex only" in cli("--profile", "alex", "run", "list_tasks")[1]


def test_version_flags(capsys):
    import toolcli, versioninfo
    with pytest.raises(SystemExit) as e:
        toolcli.main(["--version"])
    assert e.value.code == 0 and capsys.readouterr().out.strip() == versioninfo.banner()
    assert re.fullmatch(r"hermes-life-os \d+\.\d+\.\d+", versioninfo.banner())


def test_version_matches_pyproject_and_init():
    import versioninfo
    pyproject = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    init = re.search(r'__version__ = "([^"]+)"', (ROOT / "demo" / "__init__.py").read_text()).group(1)
    assert versioninfo.get() == pyproject == init


def test_entry_point_is_declared():
    assert 'hermes-life-os-tool = "hermes_life_os.toolcli:main"' in (ROOT / "pyproject.toml").read_text()
