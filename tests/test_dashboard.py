"""Tests for demo/dashboard.py - the HTML report generator."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "demo"))

import pytest


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point storage.py's HERMES_DIR at an isolated temp directory and
    reload every module that captured MEMORY_FILE/HERMES_DIR as a
    module-level constant at import time."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    import storage
    importlib.reload(storage)
    import analytics
    importlib.reload(analytics)
    import patterns
    importlib.reload(patterns)
    import dashboard
    importlib.reload(dashboard)

    return tmp_path, dashboard, storage


def _seed_entries(storage, n_days=14):
    base = datetime.now(timezone.utc) - timedelta(days=n_days)
    for i in range(n_days):
        ts = (base + timedelta(days=i)).strftime("%Y-%m-%dT09:00:00Z")
        for entry in (
            {"type": "mood", "score": 4 + (i % 5), "timestamp": ts},
            {"type": "sleep", "hours": 5.0 + (i % 4) * 0.5, "timestamp": ts},
            {"type": "stress", "score": 7 - (i % 4), "timestamp": ts},
        ):
            with open(storage.MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")


class TestBuildDashboardData:
    def test_no_data_yields_empty_series(self, fake_home):
        _, dashboard, storage = fake_home
        data = dashboard.build_dashboard_data(days=30)
        assert data["entry_count"] == 0
        assert data["dates"] == []
        assert data["insights"] == []

    def test_with_data_populates_series_and_dates(self, fake_home):
        _, dashboard, storage = fake_home
        storage.HERMES_DIR.mkdir(parents=True, exist_ok=True)
        _seed_entries(storage, n_days=14)

        data = dashboard.build_dashboard_data(days=30)
        assert data["entry_count"] == 42  # 14 days * 3 entry types
        assert len(data["dates"]) == 14
        assert len(data["per_metric"]["mood"]) == 14
        assert len(data["per_metric"]["sleep"]) == 14


class TestRenderHtml:
    def test_render_empty_data_shows_placeholder_copy(self, fake_home):
        _, dashboard, storage = fake_home
        data = dashboard.build_dashboard_data(days=30)
        html = dashboard.render_html(data)
        assert "Not enough logged data" in html
        assert "No strong correlations yet" in html
        assert "<html" in html and "</html>" in html

    def test_render_with_data_embeds_chart_image(self, fake_home):
        _, dashboard, storage = fake_home
        storage.HERMES_DIR.mkdir(parents=True, exist_ok=True)
        _seed_entries(storage, n_days=14)

        data = dashboard.build_dashboard_data(days=30)
        html = dashboard.render_html(data)
        assert "data:image/png;base64," in html
        assert "Not enough logged data" not in html

    def test_render_with_habits_lists_streaks(self, fake_home):
        _, dashboard, storage = fake_home
        storage.HERMES_DIR.mkdir(parents=True, exist_ok=True)
        storage.save_habits([{"name": "morning run", "streak": 5, "best_streak": 9}])

        data = dashboard.build_dashboard_data(days=30)
        html = dashboard.render_html(data)
        assert "morning run" in html
        assert "5 day streak" in html


class TestCliEndToEnd:
    def test_main_writes_html_file_without_data(self, fake_home, capsys):
        tmp_path, dashboard, storage = fake_home
        out_file = tmp_path / "out.html"

        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["dashboard.py", "--out", str(out_file), "--no-open"]
            dashboard.main()
        assert exc_info.value.code == 1
        assert not out_file.exists()

    def test_main_writes_html_file_with_data(self, fake_home):
        tmp_path, dashboard, storage = fake_home
        storage.HERMES_DIR.mkdir(parents=True, exist_ok=True)
        _seed_entries(storage, n_days=14)
        out_file = tmp_path / "out.html"

        sys.argv = ["dashboard.py", "--out", str(out_file), "--no-open"]
        dashboard.main()

        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "Hermes Life OS - Dashboard" in content
