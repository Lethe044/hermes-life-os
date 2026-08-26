"""
Hermes Life OS - Local REST API
===================================
A lightweight, localhost-only HTTP API exposing the same tools the LLM
agent uses - meant for third-party integrations that don't want to
(or can't) go through an LLM at all: Apple Shortcuts, Android Tasker,
a browser extension, a home-screen widget, an Alfred/Raycast workflow,
curl in a cron job, etc.

Setup (single-user - unchanged from before):
    pip install "hermes-life-os[api]"   # or: pip install flask
    set LIFE_OS_API_KEY=some-long-random-string
    hermes-life-os-api

    # from another terminal / your Shortcut / your extension:
    curl -H "X-API-Key: some-long-random-string" \\
         http://127.0.0.1:8765/api/tools

Setup (multi-user - a whole household/team sharing one server, each
person with their own profile and their own key):
    python demo/users.py add alex --profile alex
    python demo/users.py add sam --profile sam
    hermes-life-os-api          # LIFE_OS_API_KEY is optional in this mode

    curl -H "X-API-Key: <alex's key>" http://127.0.0.1:8765/api/health
    # -> {"status": "ok", "profile": "alex", "user": "alex"}
    curl -H "X-API-Key: <sam's key>"  http://127.0.0.1:8765/api/health
    # -> {"status": "ok", "profile": "sam",  "user": "sam"}

Every request is authenticated independently and automatically operates
on *that key's* profile - callers never pass a profile name themselves,
which is what keeps one person from accidentally (or deliberately)
reading another's data with the wrong key. See docs/MULTI_USER.md.

At least one of LIFE_OS_API_KEY or a users.json registry (via
`python demo/users.py add ...`) is required - the server refuses to
start with neither configured. Both can be active at once: the single
shared key (if set) always maps to --profile / LIFE_OS_PROFILE, same as
before; any request bearing a registered user's personal key maps to
that user's own profile instead. A request key that matches neither is
rejected with 401, same as always.

Security model - please read before exposing this beyond your own
machine:
    - Binds to 127.0.0.1 (localhost) by default. Only change --host if
      you understand the risk: this API has no rate limiting, no HTTPS
      of its own, and grants full read/write access to personal health
      data for every configured user.
    - Every request must send a valid key as the `X-API-Key` header -
      there is no unauthenticated fallback (except GET /api/health,
      which reports liveness only and no data).
    - Per-user keys are stored as salted PBKDF2 hashes in users.json,
      never in plaintext - see demo/users.py. The plaintext key is only
      ever shown once, at creation/rotation time.
    - If you want access from your phone (e.g. a Shortcut over your
      home Wi-Fi), put this behind a reverse proxy with HTTPS and its
      own auth (e.g. Tailscale, Caddy, or your router's VPN) rather
      than binding --host 0.0.0.0 directly - this server does not do
      TLS itself.

Endpoints:
    GET  /api/health              - {"status": "ok", "profile": "...", "user": "..."}
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

Every endpoint operates on the profile resolved from the request's
X-API-Key (either the single shared key's --profile, or a registered
user's own profile) - callers never specify a profile directly.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
import users as users_mod
from tools import dispatch_tool, TOOLS


class LocalApiError(RuntimeError):
    pass


def _require_flask():
    try:
        from flask import Flask, g, jsonify, request
        return Flask, g, jsonify, request
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


def build_app(api_key: Optional[str] = None, default_profile: Optional[str] = None):
    """Constructs and returns the Flask app. Split out from main() so
    tests can build an app instance directly (via Flask's test client)
    without going through argument parsing or client.run().

    `api_key`, if given, is the single shared key (legacy/single-user
    mode) - requests bearing it always resolve to `default_profile`
    (whatever --profile/LIFE_OS_PROFILE the server was started with).
    Independently of that, any request bearing a key registered via
    `python demo/users.py add ...` resolves to *that user's own*
    profile - both mechanisms can be active at once. At least one of
    "api_key is set" or "a user is registered" must be true for any
    request beyond /api/health to ever succeed; main() enforces that at
    startup, but build_app() itself has no opinion (useful for tests
    that only want to exercise the users.json path)."""
    Flask, g, jsonify, request = _require_flask()

    app = Flask(__name__)

    @app.after_request
    def _add_cors_headers(response):
        # Permissive CORS so a browser extension or a locally-served
        # web dashboard can call this without a proxy. Safe *because*
        # every request still needs a valid API key - CORS alone grants
        # no access, it only controls which origins a browser will let
        # fetch() calls run from.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "X-API-Key, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.before_request
    def _authenticate():
        if request.method == "OPTIONS":
            return  # CORS preflight - browsers don't attach custom headers to these

        provided = request.headers.get("X-API-Key", "")
        g.life_os_user = None
        # Tracked separately from resolved_profile because a valid shared
        # key legitimately resolves to a `default_profile` of None (which
        # means "use whatever --profile Hermes started with") - collapsing
        # "authenticated with no explicit profile" and "not authenticated"
        # into a single None would incorrectly reject that valid request.
        authenticated = False
        resolved_profile = default_profile

        if provided and api_key and provided == api_key:
            authenticated = True
        elif provided:
            user_record = users_mod.verify_api_key(provided)
            if user_record is not None:
                authenticated = True
                resolved_profile = user_record["profile"]
                g.life_os_user = user_record["username"]

        if request.path == "/api/health":
            # Liveness check only - no personal data exposed either way,
            # so this never 401s. Reports whichever profile a valid key
            # resolves to, or the server's configured default otherwise.
            storage.set_active_profile(resolved_profile if authenticated else default_profile)
            return

        if not authenticated:
            return jsonify({"error": "Missing or invalid X-API-Key header."}), 401
        storage.set_active_profile(resolved_profile)

    @app.route("/api/health", methods=["GET"])
    def health():
        payload = {"status": "ok", "profile": storage.ACTIVE_PROFILE}
        if g.get("life_os_user"):
            payload["user"] = g.life_os_user
        return jsonify(payload)

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

    import storage
    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))
    default_profile = storage.ACTIVE_PROFILE

    registered_users = users_mod.list_users()
    if not api_key and not registered_users:
        print("Neither LIFE_OS_API_KEY nor any registered user (see `python demo/users.py add`) "
              "is set. Refusing to start an unauthenticated API server.\n"
              "Single-user: set LIFE_OS_API_KEY=" + os.urandom(16).hex() + "\n"
              "Multi-user:  python demo/users.py add <name>")
        sys.exit(1)

    try:
        app = build_app(api_key, default_profile=default_profile)
    except LocalApiError as e:
        print(e)
        sys.exit(1)

    print(f"Hermes Life OS local API - default profile: {default_profile}")
    if registered_users:
        names = ", ".join(u["username"] for u in registered_users)
        print(f"Registered users (each with their own profile via their own key): {names}")
    print(f"Listening on http://{args.host}:{args.port} (Ctrl+C to stop)")
    if args.host not in ("127.0.0.1", "localhost"):
        print("WARNING: binding beyond localhost - make sure you understand the security "
              "notes in this file's docstring first.")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
