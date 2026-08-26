"""Tests for demo/web_dashboard.py - the live web dashboard. Uses
Flask's own test client (in-process, no real HTTP server)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

pytest.importorskip("flask")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "patterns", "dashboard", "web_dashboard"):
        if mod in sys.modules:
            del sys.modules[mod]
    import web_dashboard as wd
    importlib.reload(wd)
    wd.storage.set_active_profile(None)
    app = wd.build_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def storage_module(client):
    """The 'storage' module web_dashboard reloaded, already pointed at
    the same temp HOME as `client`."""
    import storage
    return storage


class TestIndexPage:
    def test_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/html")

    def test_html_includes_chartjs_and_root_div(self, client):
        resp = client.get("/")
        body = resp.get_data(as_text=True)
        assert "Chart.js" in body or "chart.umd" in body
        assert "chartWrap" in body

    def test_no_auth_required_for_index(self, client):
        # Unlike local_api.py, the web dashboard doesn't require an API
        # key - it's read-only and localhost-only by default.
        resp = client.get("/")
        assert resp.status_code == 200


class TestDashboardDataEndpoint:
    def test_empty_profile_returns_zero_entries(self, client):
        resp = client.get("/api/dashboard-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["entry_count"] == 0
        assert data["dates"] == []

    def test_includes_profile_name(self, client):
        resp = client.get("/api/dashboard-data")
        data = resp.get_json()
        assert data["profile"] == "default"

    def test_default_days_is_30(self, client):
        resp = client.get("/api/dashboard-data")
        data = resp.get_json()
        assert data["days"] == 30

    def test_custom_days_param_respected(self, client):
        resp = client.get("/api/dashboard-data?days=14")
        data = resp.get_json()
        assert data["days"] == 14

    def test_days_param_clamped_to_reasonable_range(self, client):
        resp = client.get("/api/dashboard-data?days=99999")
        data = resp.get_json()
        assert data["days"] <= 365

        resp2 = client.get("/api/dashboard-data?days=0")
        data2 = resp2.get_json()
        assert data2["days"] >= 1

    def test_with_logged_data_returns_populated_series(self, client, storage_module):
        storage_module.write_memory({"type": "mood", "score": 7})
        storage_module.write_memory({"type": "mood", "score": 8})

        resp = client.get("/api/dashboard-data")
        data = resp.get_json()
        assert data["entry_count"] == 2
        assert len(data["dates"]) >= 1
        assert "mood" in data["per_metric"]

    def test_includes_all_expected_top_level_keys(self, client):
        resp = client.get("/api/dashboard-data")
        data = resp.get_json()
        for key in ("dates", "per_metric", "correlations", "insights",
                    "patterns", "habits", "entry_count", "days",
                    "retrospective", "compare_days", "profile"):
            assert key in data

    def test_habits_included(self, client, storage_module):
        storage_module.save_habits([{"name": "Meditate", "streak": 3, "best_streak": 5}])
        resp = client.get("/api/dashboard-data")
        data = resp.get_json()
        assert data["habits"][0]["name"] == "Meditate"

    def test_response_is_valid_json_content_type(self, client):
        resp = client.get("/api/dashboard-data")
        assert resp.content_type.startswith("application/json")


class TestBuildAppRequiresFlask:
    def test_raises_clear_error_when_flask_not_installed(self, monkeypatch):
        import builtins
        import web_dashboard as wd
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "flask":
                raise ImportError("No module named 'flask'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(wd.WebDashboardError, match="flask"):
            wd.build_app()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
