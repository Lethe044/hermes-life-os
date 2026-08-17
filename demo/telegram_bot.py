"""
Hermes Life OS - Telegram Bot
================================
Talk to Hermes from your phone - no server, no webhook, just long
polling (this process needs to keep running, e.g. in a screen/tmux
session, `nohup`, or as a systemd/launchd service).

Setup:
    1. Message @BotFather on Telegram: /newbot -> get a bot token.
    2. Send your new bot any message once, then visit
       https://api.telegram.org/bot<TOKEN>/getUpdates in a browser to
       find your own numeric chat id in the response.
    3. set TELEGRAM_BOT_TOKEN=...
       set TELEGRAM_CHAT_ID=...
    4. python demo/telegram_bot.py

Only messages from TELEGRAM_CHAT_ID are ever processed - anyone else
who messages the bot (e.g. if your bot's username leaks) is silently
ignored, so your personal health data stays private.

Replies use run_life_os()'s reply_text field - the model's actual
natural-language answer (plus any briefing content it delivered),
extracted directly rather than parsing the rendered terminal output.
The terminal still shows its usual rich-formatted panels/tables (this
process's own console is unaffected); Telegram gets clean plain text
instead of box-drawing characters that would render as garbled
symbols in a chat app.

If TELEGRAM_BOT_TOKEN is copy-pasted incorrectly (or retyped by hand -
0 and O look identical in many fonts) Telegram returns 401 Unauthorized.
Repeated failed attempts can also trigger Telegram's own temporary
rate-limiting, which looks identical from here - the polling loop below
backs off exponentially (5s, 10s, 20s, ... capped at 5 minutes) on
consecutive failures instead of hammering the API, so a bad token or a
transient block doesn't make things worse.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class TelegramError(RuntimeError):
    pass


def _clean_for_telegram(text: str) -> str:
    """Strips ANSI escape codes, just in case any slip through - the
    reply_text extraction in generate_reply() shouldn't produce any,
    but this is a cheap safety net."""
    return _ANSI_ESCAPE_RE.sub("", text)


def _split_for_telegram(text: str, limit: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> List[str]:
    """Telegram rejects any single message over 4096 characters with a
    400 Bad Request - split long replies into multiple messages instead
    of losing them entirely. Splits on line boundaries where possible so
    chunks don't cut a sentence in half mid-word."""
    if len(text) <= limit:
        return [text] if text else []

    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit  # no good line break - hard-cut at the limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks


def get_updates(bot_token: str, offset: Optional[int] = None, timeout: int = 25) -> List[Dict[str, Any]]:
    """Long-polls Telegram for new messages since `offset`. Blocks for up
    to `timeout` seconds if there's nothing new yet (this is the normal,
    efficient way to poll - it is not a busy-loop)."""
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    url = f"{TELEGRAM_API}/bot{bot_token}/getUpdates?" + "&".join(f"{k}={v}" for k, v in params.items())

    try:
        with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise TelegramError(
                "Telegram rejected the bot token (401 Unauthorized) - double check "
                "TELEGRAM_BOT_TOKEN is copy-pasted exactly (never retyped by hand - "
                "0 and O look identical in many fonts). If you're sure it's correct "
                "and this just started happening, Telegram may be temporarily "
                "rate-limiting repeated failed attempts - this will back off "
                "automatically."
            ) from e
        raise TelegramError(f"getUpdates failed ({e.code}): {e}") from e
    except urllib.error.URLError as e:
        raise TelegramError(f"getUpdates failed: {e}") from e

    if not body.get("ok"):
        raise TelegramError(f"getUpdates returned an error: {body}")
    return body.get("result", [])


def send_message(bot_token: str, chat_id: str, text: str) -> None:
    """Sends a plain-text reply (no Markdown - see module docstring),
    automatically split across multiple Telegram messages if it's over
    Telegram's 4096-character limit."""
    text = _clean_for_telegram(text)
    for chunk in _split_for_telegram(text):
        url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": chunk}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            raise TelegramError(f"sendMessage failed ({e.code}): {detail}") from e
        except urllib.error.URLError as e:
            raise TelegramError(f"sendMessage failed: {e}") from e
        if not body.get("ok"):
            raise TelegramError(f"sendMessage returned an error: {body}")


def extract_message(update: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Pulls (chat_id, text) out of one Telegram update dict, or None if
    it isn't a plain text message (photos, stickers, edits, etc. are
    intentionally ignored - text-only for now)."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text")
    if chat_id is None or not text:
        return None
    return str(chat_id), text


def is_authorized(chat_id: str, allowed_chat_id: str) -> bool:
    return str(chat_id) == str(allowed_chat_id)


def generate_reply(client, model: str, user_text: str) -> str:
    """Runs one message through the same tool-calling pipeline as
    --mode chat (run_life_os), returning its reply_text field - the
    model's actual natural-language answer, plus any briefing content
    it delivered along the way. The terminal this process runs in still
    shows the normal rich-formatted output (panels, tables, tool-call
    trace) exactly as --mode chat does; only the *returned* text (what
    gets sent to Telegram) is plain and reply-focused."""
    from demo_life_os import run_life_os, seed_demo_memory

    seed_demo_memory()
    scenario = {"title": "Telegram", "prompt": user_text}
    result = run_life_os(scenario, client, model, max_turns=10, user_message=user_text)
    return result.get("reply_text", "").strip() or (
        "I processed that, but didn't have a specific reply to send back - "
        "try asking again or rephrasing."
    )


def run_bot(bot_token: str, allowed_chat_id: str, client, model: str,
            max_iterations: Optional[int] = None) -> None:
    """The polling loop. `max_iterations` exists purely for tests - normal
    use leaves it None and runs forever until interrupted."""
    offset: Optional[int] = None
    iterations = 0
    consecutive_failures = 0
    MAX_BACKOFF_SECONDS = 300  # 5 minutes

    print(f"Hermes Life OS Telegram bot started. Listening for chat_id {allowed_chat_id}...")
    while max_iterations is None or iterations < max_iterations:
        try:
            updates = get_updates(bot_token, offset=offset, timeout=25)
            consecutive_failures = 0
        except TelegramError as e:
            consecutive_failures += 1
            # exponential backoff (5s, 10s, 20s, ... capped at 5 min) - repeatedly
            # hammering Telegram with a bad/rate-limited token only makes any
            # block worse, so back off harder the longer this keeps failing
            wait_seconds = min(5 * (2 ** (consecutive_failures - 1)), MAX_BACKOFF_SECONDS)
            print(f"[telegram_bot] {e} - retrying in {wait_seconds}s "
                  f"({consecutive_failures} consecutive failures).")
            time.sleep(wait_seconds)
            iterations += 1
            continue

        for update in updates:
            offset = update["update_id"] + 1
            parsed = extract_message(update)
            if parsed is None:
                continue
            chat_id, text = parsed
            if not is_authorized(chat_id, allowed_chat_id):
                continue  # silently ignore anyone who isn't you

            try:
                reply = generate_reply(client, model, text)
            except Exception as e:
                reply = f"Something went wrong processing that: {e}"

            try:
                send_message(bot_token, chat_id, reply)
            except TelegramError as e:
                print(f"[telegram_bot] Failed to send reply: {e}")

        iterations += 1


def main():
    parser = argparse.ArgumentParser(description="Run the Hermes Life OS Telegram bot")
    parser.add_argument("--provider", default=None,
                        help="LLM backend: ollama, openai, anthropic, openrouter. "
                             "Default: auto-detect from env vars.")
    parser.add_argument("--model", default=None, help="Overrides the provider's default model.")
    parser.add_argument("--profile", default=None,
                        help="Named profile to use. Default: 'default'. Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not allowed_chat_id:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first (see this file's docstring for setup steps).")
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

    print(f"Provider: {provider}  Model: {model}  Profile: {storage.ACTIVE_PROFILE}")
    try:
        run_bot(bot_token, allowed_chat_id, client, model)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
