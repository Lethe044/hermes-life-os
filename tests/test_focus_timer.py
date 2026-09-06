"""Tests for demo/focus_timer.py. time.sleep is always mocked so these
tests run instantly regardless of the requested duration - no test
here actually waits in real time."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def focus_timer(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "tools", "focus_timer"):
        if mod in sys.modules:
            del sys.modules[mod]
    import focus_timer as ft
    importlib.reload(ft)
    import storage
    storage.set_active_profile(None)
    return ft


class TestCountdown:
    def test_completes_without_raising(self, focus_timer):
        with patch("time.sleep"):
            focus_timer._countdown(3, "Test")  # no real waiting - time.sleep is mocked

    def test_calls_sleep_once_per_second(self, focus_timer):
        with patch("time.sleep") as mock_sleep:
            focus_timer._countdown(5, "Test")
        assert mock_sleep.call_count == 5

    def test_propagates_keyboard_interrupt(self, focus_timer):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                focus_timer._countdown(10, "Test")


class TestRunFocusSession:
    def test_completes_and_logs_by_default(self, focus_timer):
        with patch("time.sleep"):
            completed = focus_timer.run_focus_session(1, task="writing")
        assert completed is True

    def test_logged_session_appears_in_focus_data(self, focus_timer):
        from storage import load_focus
        with patch("time.sleep"):
            focus_timer.run_focus_session(1, task="writing")
        entries = load_focus()
        assert len(entries) == 1
        assert entries[0]["duration"] == 1

    def test_no_log_flag_skips_logging(self, focus_timer):
        from storage import load_focus
        with patch("time.sleep"):
            focus_timer.run_focus_session(1, task="writing", log=False)
        assert load_focus() == []

    def test_ctrl_c_returns_false_and_does_not_log(self, focus_timer):
        from storage import load_focus
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            completed = focus_timer.run_focus_session(5, task="writing")
        assert completed is False
        assert load_focus() == []

    def test_unnamed_task_gets_a_default_label(self, focus_timer):
        from storage import load_focus
        with patch("time.sleep"):
            focus_timer.run_focus_session(1, task="")
        assert load_focus()[0]["task"] == "focus session"


class TestRunBreak:
    def test_completes_without_raising(self, focus_timer):
        with patch("time.sleep"):
            focus_timer.run_break(1)  # should not raise

    def test_ctrl_c_handled_gracefully(self, focus_timer):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            focus_timer.run_break(1)  # should not propagate


class TestMainCli:
    def test_default_session_completes_and_logs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "tools", "focus_timer"):
            if mod in sys.modules:
                del sys.modules[mod]
        import focus_timer as ft
        importlib.reload(ft)

        monkeypatch.setattr(sys, "argv", ["focus_timer.py", "1", "--task", "reading"])
        with patch("time.sleep"):
            ft.main()

        from storage import load_focus
        assert len(load_focus()) == 1

    def test_break_runs_after_completed_session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "tools", "focus_timer"):
            if mod in sys.modules:
                del sys.modules[mod]
        import focus_timer as ft
        importlib.reload(ft)

        monkeypatch.setattr(sys, "argv", ["focus_timer.py", "1", "--break", "1"])
        with patch("time.sleep") as mock_sleep:
            ft.main()
        # 60 seconds of focus + 60 seconds of break = 120 sleep() calls
        assert mock_sleep.call_count == 120

    def test_no_log_flag_via_cli(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "tools", "focus_timer"):
            if mod in sys.modules:
                del sys.modules[mod]
        import focus_timer as ft
        importlib.reload(ft)

        monkeypatch.setattr(sys, "argv", ["focus_timer.py", "1", "--no-log"])
        with patch("time.sleep"):
            ft.main()

        from storage import load_focus
        assert load_focus() == []
