"""Tests for demo/local_api.py - the local REST API. Uses Flask's own
test client (in-process, no real HTTP server) so these run fast and
without a port."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

pytest.importorskip("flask")

API_KEY = "test-api-key-12345"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "tools", "local_api"):
        if mod in sys.modules:
            del sys.modules[mod]
    import local_api
    importlib.reload(local_api)
    local_api.storage.set_active_profile(None)
    app = local_api.build_app(API_KEY)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def auth_headers():
    return {"X-API-Key": API_KEY}


class TestHealthEndpoint:
    def test_health_requires_no_api_key(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_health_reports_active_profile(self, client):
        resp = client.get("/api/health")
        assert resp.get_json()["profile"] == "default"


class TestApiKeyAuth:
    def test_missing_key_rejected(self, client):
        resp = client.get("/api/tools")
        assert resp.status_code == 401

    def test_wrong_key_rejected(self, client):
        resp = client.get("/api/tools", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_correct_key_accepted(self, client):
        resp = client.get("/api/tools", headers=auth_headers())
        assert resp.status_code == 200

    def test_options_preflight_not_blocked_by_auth(self, client):
        resp = client.options("/api/tools")
        assert resp.status_code != 401


class TestCorsHeaders:
    def test_cors_header_present_on_response(self, client):
        resp = client.get("/api/health")
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"


class TestListTools:
    def test_returns_tool_schema_list(self, client):
        resp = client.get("/api/tools", headers=auth_headers())
        data = resp.get_json()
        assert isinstance(data, list)
        names = {t["name"] for t in data}
        assert "remember" in names
        assert "log_meal" in names

    def test_each_entry_has_description_and_parameters(self, client):
        resp = client.get("/api/tools", headers=auth_headers())
        data = resp.get_json()
        for tool in data:
            assert "description" in tool
            assert "parameters" in tool


class TestCallTool:
    def test_remember_via_api(self, client):
        resp = client.post("/api/tools/remember", headers=auth_headers(),
                           json={"type": "mood", "content": "feeling good today"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "Remembered" in data["result"]

    def test_log_meal_via_api_then_recall(self, client):
        resp = client.post("/api/tools/log_meal", headers=auth_headers(),
                           json={"meal_time": "lunch", "food": "chicken salad", "calories": 450})
        assert resp.status_code == 200

        resp2 = client.get("/api/memory/search?q=chicken", headers=auth_headers())
        results = resp2.get_json()
        assert any("chicken" in json.dumps(r) for r in results)

    def test_unknown_tool_returns_404(self, client):
        resp = client.post("/api/tools/not_a_real_tool", headers=auth_headers(), json={})
        assert resp.status_code == 404

    def test_missing_body_treated_as_empty_object(self, client):
        # get_profile takes no required params - an empty/missing body should be fine
        resp = client.post("/api/tools/get_profile", headers=auth_headers())
        assert resp.status_code == 200

    def test_non_object_body_rejected(self, client):
        resp = client.post("/api/tools/remember", headers=auth_headers(),
                           data=json.dumps(["not", "an", "object"]),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_json_result_is_also_parsed_into_data_field(self, client):
        resp = client.post("/api/tools/get_profile", headers=auth_headers(), json={})
        data = resp.get_json()
        assert "data" in data
        assert "profile" in data["data"]

    def test_plain_text_result_has_no_data_field(self, client):
        resp = client.post("/api/tools/remember", headers=auth_headers(),
                           json={"type": "note", "content": "just a note"})
        data = resp.get_json()
        assert "data" not in data

    def test_tool_exception_returns_500_not_a_crash(self, client, monkeypatch):
        import local_api

        def broken_dispatch(name, inp):
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(local_api, "dispatch_tool", broken_dispatch)
        resp = client.post("/api/tools/remember", headers=auth_headers(),
                           json={"type": "note", "content": "x"})
        assert resp.status_code == 500
        assert "simulated failure" in resp.get_json()["error"]


class TestMemoryRecent:
    def test_returns_recent_entries(self, client):
        client.post("/api/tools/remember", headers=auth_headers(),
                    json={"type": "mood", "content": "recent entry"})
        resp = client.get("/api/memory/recent", headers=auth_headers())
        assert resp.status_code == 200
        entries = resp.get_json()
        assert any(e.get("content") == "recent entry" for e in entries)

    def test_days_param_respected(self, client):
        resp = client.get("/api/memory/recent?days=30", headers=auth_headers())
        assert resp.status_code == 200


class TestMemorySearch:
    def test_missing_query_param_rejected(self, client):
        resp = client.get("/api/memory/search", headers=auth_headers())
        assert resp.status_code == 400

    def test_search_finds_matching_entry(self, client):
        client.post("/api/tools/remember", headers=auth_headers(),
                    json={"type": "note", "content": "unique-searchable-phrase-xyz"})
        resp = client.get("/api/memory/search?q=unique-searchable-phrase-xyz", headers=auth_headers())
        results = resp.get_json()
        assert len(results) >= 1

    def test_limit_param_respected(self, client):
        for i in range(5):
            client.post("/api/tools/remember", headers=auth_headers(),
                        json={"type": "note", "content": f"limit-test-entry-{i}"})
        resp = client.get("/api/memory/search?q=limit-test-entry&limit=2", headers=auth_headers())
        results = resp.get_json()
        assert len(results) <= 2


class TestBuildAppRequiresFlask:
    def test_raises_clear_error_when_flask_not_installed(self, client, monkeypatch):
        import local_api
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "flask":
                raise ImportError("No module named 'flask'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(local_api.LocalApiError, match="flask"):
            local_api.build_app("some-key")


class TestMainCli:
    def test_missing_api_key_exits_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("LIFE_OS_API_KEY", raising=False)
        for mod in ("storage", "local_api"):
            if mod in sys.modules:
                del sys.modules[mod]
        import local_api
        importlib.reload(local_api)
        monkeypatch.setattr(sys, "argv", ["local_api.py"])
        with pytest.raises(SystemExit) as exc_info:
            local_api.main()
        assert exc_info.value.code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
