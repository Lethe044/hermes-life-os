"""
Hermes Life OS - Slack Bot
=============================
Talk to Hermes from Slack via direct message. Uses Socket Mode (a
persistent websocket connection) - like telegram_bot.py, this needs no
public server or webhook URL, just a long-running process.

Setup:
    1. Create a Slack app at https://api.slack.com/apps ("From scratch").
    2. Under "Socket Mode", enable it and generate an app-level token
       with the connections:write scope (starts with xapp-).
    3. Under "OAuth & Permissions", add these Bot Token Scopes:
       chat:write, im:history, im:read, im:write, files:read
       then "Install to Workspace" and copy the Bot User OAuth Token
       (starts with xoxb-).
    4. Under "Event Subscriptions", subscribe to the message.im bot
       event (Socket Mode carries these over the websocket - no Request
       URL needed).
    5. Find your own Slack user ID: click your profile picture ->
       "View profile" -> "More" (...) -> "Copy member ID".
    6. set SLACK_BOT_TOKEN=xoxb-...
       set SLACK_APP_TOKEN=xapp-...
       set SLACK_ALLOWED_USER_ID=U0123ABC        # single-user mode
    7. pip install "hermes-life-os[slack]"        # or: pip install slack_bolt
    8. python demo/slack_bot.py

Multi-user mode - a household or small team sharing one bot, each
person automatically routed to their own profile (see
docs/MULTI_USER.md) - skip SLACK_ALLOWED_USER_ID and instead register
and link each person once:

    python demo/users.py add alex --profile alex
    python demo/users.py link alex slack U0123ABC
    python demo/users.py add sam --profile sam
    python demo/users.py link sam slack U0456DEF

A DM from a Slack user ID covered by neither SLACK_ALLOWED_USER_ID nor
a users.json link is silently ignored (never confirmed or denied to an
unknown sender) - your data stays private, and a typo in a link can't
accidentally expose the wrong profile to the wrong person.

Photos are supported like the other bots: share an image of a meal in
the DM and Hermes uses a vision-capable LLM to identify and log it -
this needs a vision-capable model, see telegram_bot.py's docstring for
the Ollama (llava) setup note, which applies here too.

Unlike telegram_bot.py's hand-rolled long-polling loop, this uses
slack_bolt (Slack's own, officially supported framework) and its
Socket Mode handler for the connection lifecycle - there's no custom
polling or backoff logic here.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
import users as users_mod


class SlackBotError(RuntimeError):
    pass


def resolve_profile(
    slack_user_id: str, allowed_user_id: Optional[str]
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Decides whether a Slack user is allowed to talk to this bot and,
    if so, which profile their messages should operate on.

    Returns (authorized, profile_or_none, username_or_none):
      - Single-user match (SLACK_ALLOWED_USER_ID): (True, None, None) -
        None means "don't switch profiles, use whichever profile this
        process already has active" (--profile / LIFE_OS_PROFILE).
      - Multi-user match (a users.json link): (True, their_profile,
        their_username).
      - No match: (False, None, None) - caller should silently ignore.
    """
    if allowed_user_id and str(slack_user_id) == str(allowed_user_id):
        return True, None, None
    record = users_mod.find_by_channel("slack", slack_user_id)
    if record is not None:
        return True, record["profile"], record["username"]
    return False, None, None


def generate_reply(client, model: str, user_text: str, image_data_uri: str = "") -> str:
    """Runs one message through the same tool-calling pipeline as the
    other bots (run_life_os), returning its reply_text field."""
    from demo_life_os import run_life_os, seed_demo_memory

    seed_demo_memory()
    prompt = user_text or (
        "Here's a photo of my meal - please identify what I ate and log it."
    )
    scenario = {"title": "Slack", "prompt": prompt}
    result = run_life_os(scenario, client, model, max_turns=10,
                          user_message=prompt, image_data_uri=image_data_uri)
    return result.get("reply_text", "").strip() or (
        "I processed that, but didn't have a specific reply to send back - "
        "try asking again or rephrasing."
    )


def download_slack_file(bot_token: str, file_url: str) -> bytes:
    """Downloads a Slack file (the `url_private` field from a message's
    `files` list). Slack file URLs require the bot token as a Bearer
    auth header, unlike a plain public URL - a bare GET returns a login
    wall instead of the file."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(file_url, headers={"Authorization": f"Bearer {bot_token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError) as e:
        raise SlackBotError(f"Failed to download Slack file: {e}") from e


def bytes_to_image_data_uri(raw: bytes, mimetype: Optional[str]) -> str:
    """Encodes raw image bytes as a base64 data URI, ready to hand to
    run_life_os(image_data_uri=...)."""
    media_type = mimetype or "image/jpeg"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def extract_image_files(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pulls image file entries (mimetype starting with image/) out of
    a Slack message event's `files` list, if any."""
    files = event.get("files") or []
    return [f for f in files if str(f.get("mimetype", "")).startswith("image/")]


def handle_message(
    event: Dict[str, Any],
    llm_client,
    model: str,
    bot_token: str,
    allowed_user_id: Optional[str],
) -> Optional[str]:
    """Core message-handling logic, factored out from the slack_bolt
    event listener so it's unit-testable with a plain event dict - no
    real Slack connection needed. Returns the reply text to send, or
    None if the event should be silently ignored (a bot's own message,
    an unauthorized sender, or a genuinely empty message).

    Side effect: switches the active storage profile when the sender
    resolves to a linked multi-user profile. This is process-global
    state, exactly like local_api.py's per-request profile switch -
    safe here because Socket Mode delivers events to this handler one
    at a time, never concurrently.
    """
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return None  # never process the bot's own messages

    slack_user_id = event.get("user")
    if not slack_user_id:
        return None

    authorized, profile, _username = resolve_profile(slack_user_id, allowed_user_id)
    if not authorized:
        return None  # silently ignore - never confirm/deny to an unknown sender

    if profile is not None:
        storage.set_active_profile(profile)

    text = (event.get("text") or "").strip()
    image_data_uri = ""
    for f in extract_image_files(event):
        url = f.get("url_private")
        if not url:
            continue
        try:
            raw = download_slack_file(bot_token, url)
        except SlackBotError as e:
            return f"Couldn't process that image: {e}"
        image_data_uri = bytes_to_image_data_uri(raw, f.get("mimetype"))
        break  # only the first image, same convention as the other bots

    if not text and not image_data_uri:
        return None  # nothing to respond to

    try:
        reply = generate_reply(llm_client, model, text, image_data_uri=image_data_uri)
    except Exception as e:  # noqa: BLE001 - never let a bad turn crash the bot process
        reply = f"Something went wrong processing that: {e}"

    if image_data_uri:
        reply = f"\U0001F4F7 {reply}"
    return reply


def build_app(bot_token: str, llm_client, model: str, allowed_user_id: Optional[str],
              verify_token: bool = True):
    """Constructs the slack_bolt App, wiring handle_message() into its
    message event listener. Imports slack_bolt lazily so this whole
    module (and its testable helpers above) can be imported/tested
    without slack_bolt installed - it's an optional extra, same as
    discord.py is for the Discord bot.

    `verify_token` controls slack_bolt's own eager auth.test call at
    construction time (nice fail-fast UX in main() - a bad token is
    reported immediately with a clear error instead of only surfacing
    once a message arrives). Tests pass verify_token=False so building
    an App doesn't require real network access or a real token."""
    try:
        from slack_bolt import App
    except ImportError as e:
        raise SlackBotError(
            "The 'slack_bolt' package is required for the Slack bot.\n"
            "  pip install \"hermes-life-os[slack]\"   # or: pip install slack_bolt"
        ) from e

    try:
        app = App(token=bot_token, token_verification_enabled=verify_token)
    except Exception as e:  # noqa: BLE001 - slack_bolt raises its own BoltError subclass
        raise SlackBotError(f"Could not start the Slack app - check SLACK_BOT_TOKEN: {e}") from e

    @app.event("message")
    def _on_message(event, say):
        if event.get("channel_type") != "im":
            return  # DMs only - ignore channel/group messages and mentions
        reply = handle_message(event, llm_client, model, bot_token, allowed_user_id)
        if reply:
            say(reply)

    return app


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Hermes Life OS Slack bot")
    parser.add_argument("--provider", default=None,
                        help="LLM backend: ollama, openai, anthropic, openrouter. "
                             "Default: auto-detect from env vars.")
    parser.add_argument("--model", default=None, help="Overrides the provider's default model.")
    parser.add_argument("--profile", default=None,
                        help="Default/single-user profile. Default: 'default'. Ignored for "
                             "messages from a linked multi-user account, which use their own "
                             "profile instead. Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args()

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    allowed_user_id = os.environ.get("SLACK_ALLOWED_USER_ID")

    if not bot_token or not app_token:
        print("Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN first (see this file's docstring for setup steps).")
        sys.exit(1)

    registered_slack_users = [
        u for u in users_mod.list_users() if u.get("channels", {}).get("slack")
    ]
    if not allowed_user_id and not registered_slack_users:
        print("Set SLACK_ALLOWED_USER_ID for single-user mode, or link at least one user via\n"
              "  python demo/users.py link <name> slack <slack-user-id>\n"
              "for multi-user mode.")
        sys.exit(1)

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    from llm_providers import ProviderError, resolve_provider, default_model_for, get_client
    try:
        provider = resolve_provider(args.provider)
        client = get_client(provider)
    except ProviderError as e:
        print(e)
        sys.exit(1)
    model = args.model or default_model_for(provider)

    try:
        slack_app = build_app(bot_token, client, model, allowed_user_id)
    except SlackBotError as e:
        print(e)
        sys.exit(1)

    try:
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError as e:
        print(f"The 'slack_bolt' package is required for the Slack bot: {e}")
        sys.exit(1)

    print(f"Provider: {provider}  Model: {model}  Profile: {storage.ACTIVE_PROFILE}")
    if registered_slack_users:
        names = ", ".join(u["username"] for u in registered_slack_users)
        print(f"Multi-user mode - linked Slack users: {names}")
    print("Hermes Life OS Slack bot started (Socket Mode). Listening for DMs...")
    try:
        SocketModeHandler(slack_app, app_token).start()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
