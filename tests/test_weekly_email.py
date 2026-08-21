"""Tests for demo/weekly_email.py. dashboard/render/send_html_email are
monkeypatched throughout - no real SMTP connection or matplotlib chart
rendering is exercised here (those are covered by test_dashboard.py and
test_notifications.py respectively)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def weekly_email(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "dashboard", "notifications", "weekly_email"):
        if mod in sys.modules:
            del sys.modules[mod]
    import weekly_email as we
    importlib.reload(we)
    return we


def _seed_entry(storage_mod):
    storage_mod.HERMES_DIR.mkdir(parents=True, exist_ok=True)
    with open(storage_mod.MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "mood", "score": 7, "timestamp": "2026-01-01T09:00:00Z"}) + "\n")


class TestSendWeeklySummary:
    def test_builds_dashboard_data_and_sends_email(self, weekly_email, monkeypatch):
        calls = {}

        def fake_build_dashboard_data(days, compare_days):
            calls["build_args"] = (days, compare_days)
            return {"entry_count": 5, "dates": [], "per_metric": {}, "correlations": [],
                    "insights": [], "patterns": {}, "habits": [], "days": days,
                    "retrospective": {}, "compare_days": compare_days}

        monkeypatch.setattr(weekly_email, "build_dashboard_data", fake_build_dashboard_data)
        monkeypatch.setattr(weekly_email, "render_html", lambda data: "<html>fake report</html>")

        def fake_send_html_email(subject, html, plain):
            calls["subject"] = subject
            calls["html"] = html
            calls["plain"] = plain

        monkeypatch.setattr(weekly_email, "send_html_email", fake_send_html_email)

        weekly_email.send_weekly_summary(days=30, compare_days=7)

        assert calls["build_args"] == (30, 7)
        assert calls["html"] == "<html>fake report</html>"
        assert "Weekly Summary" in calls["subject"]
        assert "5 entries" in calls["plain"]

    def test_propagates_notification_error(self, weekly_email, monkeypatch):
        monkeypatch.setattr(weekly_email, "build_dashboard_data",
                            lambda days, compare_days: {"entry_count": 0})
        monkeypatch.setattr(weekly_email, "render_html", lambda data: "<html></html>")

        def failing_send(*a, **k):
            raise weekly_email.NotificationError("SMTP not configured")

        monkeypatch.setattr(weekly_email, "send_html_email", failing_send)

        with pytest.raises(weekly_email.NotificationError):
            weekly_email.send_weekly_summary()


class TestMainCli:
    def test_no_data_exits_cleanly(self, weekly_email, capsys):
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["weekly_email.py"]
            weekly_email.main()
        assert exc_info.value.code == 1
        assert "No data yet" in capsys.readouterr().out

    def test_send_failure_exits_with_message(self, weekly_email, monkeypatch, capsys):
        _seed_entry(weekly_email.storage)
        monkeypatch.setattr(weekly_email, "send_weekly_summary",
                            lambda *a, **k: (_ for _ in ()).throw(
                                weekly_email.NotificationError("SMTP not configured")))
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["weekly_email.py"]
            weekly_email.main()
        assert exc_info.value.code == 1
        assert "Failed to send" in capsys.readouterr().out

    def test_success_prints_confirmation(self, weekly_email, monkeypatch, capsys):
        _seed_entry(weekly_email.storage)
        monkeypatch.setattr(weekly_email, "send_weekly_summary", lambda *a, **k: None)
        sys.argv = ["weekly_email.py"]
        weekly_email.main()
        assert "emailed" in capsys.readouterr().out.lower()

    def test_profile_flag_used(self, weekly_email, monkeypatch):
        weekly_email.storage.set_active_profile("alex")
        weekly_email.storage.write_memory({"type": "mood", "score": 5})
        weekly_email.storage.set_active_profile(None)

        monkeypatch.setattr(weekly_email, "send_weekly_summary", lambda *a, **k: None)
        sys.argv = ["weekly_email.py", "--profile", "alex"]
        weekly_email.main()
        assert weekly_email.storage.ACTIVE_PROFILE == "alex"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
