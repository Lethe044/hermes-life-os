"""
Hermes Life OS - Local REST API
===================================
A lightweight, localhost-only HTTP API exposing the same tools the LLM
agent uses - meant for third-party integrations that don't want to
(or can't) go through an LLM at all: Apple Shortcuts, Android Tasker,
a browser extension, a home-screen widget, an Alfred/Raycast workflow,
curl in a cron job, etc.

Setup:
    pip install "hermes-life-os[api]"   # or: pip install flask
    set LIFE_OS_API_KEY=some-long-random-string
    hermes-life-os-api

    # from another terminal / your Shortcut / your extension:
    curl -H "X-API-Key: some-long-random-string" \\
         http://127.0.0.1:8765/api/tools

Security model - please read before exposing this beyond your own
machine:
    - Binds to 127.0.0.1 (localhost) by default. Only change --host if
      you understand the risk: this API has no rate limiting, no HTTPS
      of its own, and grants full read/write access to your personal
      health data.
    - LIFE_OS_API_KEY is REQUIRED - the server refuses to start without
      it (unlike encryption at rest, this isn't optional, because an
      HTTP server has a materially larger exposure surface than a local
      file). Every request must send it as the `X-API-Key` header.
    - If you want access from your phone (e.g. a Shortcut over your
      home Wi-Fi), put this behind a reverse proxy with HTTPS and its
      own auth (e.g. Tailscale, Caddy, or your router's VPN) rather
      than binding --host 0.0.0.0 directly - this server does not do
      TLS itself.

Endpoints:
    GET  /api/health              - {"status": "ok", "profile": "..."}
    GET  /api/tools                - the same tool schema list the LLM sees
                                      (name, description, parameters) - lets
                                      a Shortcut/extension discover what's
                                      callable without reading source.
    POST /api/tools/<name>         - call any tool directly. Body: JSON
                                      matching that tool's parameters (see
                                      GET /api/tools). Returns the tool's
                                      result, parsed as JSON when possible.
    GET  /api/memory/recent?days=7 - recent memory entries (JSON)
    GET  /api/memory/search?q=...  - keyword search over memory (JSON)

Every endpoint operates on the active profile (LIFE_OS_PROFILE env var,
same as every other Hermes command) - this API doesn't add profile
switching of its own.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
from tools import dispatch_tool, TOOLS


class LocalApiError(RuntimeError):
    pass


def _require_flask():
    try:
        from flask import Flask, jsonify, request
        return Flask, jsonify, request
    except ImportError as e:
        raise LocalApiError(
            "The 'flask' package is required for the local API.\n"
            "  pip install \"hermes-life-os[api]\"   # or: pip install flask"
        ) from e


def _try_parse_json(text: str) -> Any:
    """Tool results are always a string (that's the LLM tool-call
    contract), but many tools actually return a JSON payload as text
    (e.g. get_profile, weekly_health_report). Surface the parsed form
    too when it's valid JSON, so API clients don't have to re-parse
    strings themselves - falls back to the raw string otherwise."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def build_app(api_key: str):
    """Constructs and returns the Flask app. Split out from main() so
    tests can build an app instance directly (via Flask's test client)
    without going through argument parsing or client.run()."""
    Flask, jsonify, request = _require_flask()

    app = Flask(__name__)

    @app.after_request
    def _add_cors_headers(response):
        # Permissive CORS so a browser extension or a locally-served
        # web dashboard can call this without a proxy. Safe *because*
        # every request still needs the API key - CORS alone grants no
        # access, it only controls which origins a browser will let
        # fetch() calls run from.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "X-API-Key, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.before_request
    def _check_api_key():
        if request.method == "OPTIONS":
            return  # CORS preflight - browsers don't attach custom headers to these
        if request.path == "/api/health":
            return  # unauthenticated liveness check only - no data exposed
        provided = request.headers.get("X-API-Key", "")
        if provided != api_key:
            return jsonify({"error": "Missing or invalid X-API-Key header."}), 401

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "profile": storage.ACTIVE_PROFILE})

    @app.route("/api/tools", methods=["GET"])
    def list_tools():
        return jsonify([t["function"] for t in TOOLS])

    @app.route("/api/tools/<name>", methods=["POST"])
    def call_tool(name):
        valid_names = {t["function"]["name"] for t in TOOLS}
        if name not in valid_names:
            return jsonify({"error": f"Unknown tool: {name}"}), 404

        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be a JSON object."}), 400

        try:
            result = dispatch_tool(name, body)
        except Exception as e:  # noqa: BLE001 - never leak a raw 500 with a stack trace
            return jsonify({"error": f"Tool call failed: {e}"}), 500

        payload = {"result": result}
        parsed = _try_parse_json(result)
        if parsed is not None:
            payload["data"] = parsed
        return jsonify(payload)

    @app.route("/api/memory/recent", methods=["GET"])
    def memory_recent():
        days = request.args.get("days", default=7, type=int)
        entries = storage.get_recent_memory(days=days)
        return jsonify(entries)

    @app.route("/api/memory/search", methods=["GET"])
    def memory_search():
        query = request.args.get("q", default="", type=str)
        if not query:
            return jsonify({"error": "Missing required query param 'q'."}), 400
        limit = request.args.get("limit", default=10, type=int)
        results = storage.search_memory(query, limit=limit)
        return jsonify(results)

    return app


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Hermes Life OS local REST API.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address. Default: 127.0.0.1 (localhost only - see this "
                             "file's docstring before changing this).")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on. Default: 8765.")
    parser.add_argument("--profile", default=None,
                        help="Named profile to serve. Default: 'default'. Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args()

    api_key = os.environ.get("LIFE_OS_API_KEY")
    if not api_key:
        print("LIFE_OS_API_KEY is not set. Refusing to start an unauthenticated API server.\n"
              "Set it to a long random string first, e.g.:\n"
              "  set LIFE_OS_API_KEY=" + os.urandom(16).hex())
        sys.exit(1)

    import storage
    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    try:
        app = build_app(api_key)
    except LocalApiError as e:
        print(e)
        sys.exit(1)

    print(f"Hermes Life OS local API - profile: {storage.ACTIVE_PROFILE}")
    print(f"Listening on http://{args.host}:{args.port} (Ctrl+C to stop)")
    if args.host not in ("127.0.0.1", "localhost"):
        print("WARNING: binding beyond localhost - make sure you understand the security "
              "notes in this file's docstring first.")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
