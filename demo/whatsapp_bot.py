"""
Hermes Life OS - WhatsApp Bot
=================================
Talk to Hermes over WhatsApp, using Twilio's WhatsApp API as the
transport (webhook-based - Twilio calls your server when a message
arrives, unlike the Telegram bot's polling loop or the Discord bot's
websocket client). Same feature set as both: plain text, photo-based
meal logging (vision), and voice-note transcription.

Setup (Twilio WhatsApp Sandbox - free, good for personal use):
    1. Sign up at https://www.twilio.com/console, note your Account SID
       and Auth Token from the console dashboard.
    2. Console -> Messaging -> Try it out -> Send a WhatsApp message ->
       follow the sandbox join instructions (send the given join code
       from your own WhatsApp to Twilio's sandbox number).
    3. set TWILIO_ACCOUNT_SID=...
       set TWILIO_AUTH_TOKEN=...
       set WHATSAPP_ALLOWED_NUMBER=whatsapp:+1XXXXXXXXXX   # your own number, E.164, with the "whatsapp:" prefix
    4. pip install "hermes-life-os[whatsapp]"   # or: pip install flask twilio
    5. hermes-life-os-whatsapp              # starts a local webhook server (default port 8766)
    6. Expose it publicly so Twilio can reach it - e.g. `ngrok http 8766`
       - and set that ngrok URL + "/whatsapp/webhook" (e.g.
       https://abcd1234.ngrok.io/whatsapp/webhook) as the sandbox's
       "WHEN A MESSAGE COMES IN" webhook in the Twilio console.
    7. Message the sandbox number from your phone.

For a production number (your own approved WhatsApp Business number
rather than the shared sandbox), setup on this bot's side is identical
- only the Twilio console configuration differs.

Security: every incoming request's Twilio signature is verified
(X-Twilio-Signature header, validated against TWILIO_AUTH_TOKEN) before
anything is processed - this is what stops someone else from POSTing
fake messages straight to your webhook URL. On top of that, only
messages from WHATSAPP_ALLOWED_NUMBER are ever processed - anyone else
who messages your sandbox/number (signature-valid or not) is silently
ignored.

Photos: attach an image and Hermes uses a vision-capable LLM to
identify the meal and log it - see telegram_bot.py's docstring for the
Ollama (llava) note, which applies here too.

Voice notes: WhatsApp voice messages are downloaded (via Twilio's
authenticated media URL) and transcribed locally via
voice_transcribe.py (faster-whisper), exactly like the Telegram/
Discord bots.

Replies are sent back as TwiML in the same HTTP response Twilio's
webhook call receives, so a reply must be ready within Twilio's ~15s
webhook timeout - the same practical constraint every Hermes reply
already tries to stay under.
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile
import xml.sax.saxutils as saxutils
from pathlib import Path
from typing import Any, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_transcribe import transcribe_audio, TranscriptionError

WHATSAPP_MAX_MESSAGE_LENGTH = 1550  # Twilio's WhatsApp limit is 1600 - leave headroom


class WhatsAppBotError(RuntimeError):
    pass


def is_authorized(from_number: str, allowed_number: str) -> bool:
    return (from_number or "").strip() == (allowed_number or "").strip()


def _split_for_whatsapp(text: str, limit: int = WHATSAPP_MAX_MESSAGE_LENGTH) -> List[str]:
    """Splits a long reply into several WhatsApp-sized messages, same
    line-boundary-aware approach as the Telegram/Discord bots use."""
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
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks


def classify_media(content_type: Optional[str]) -> str:
    if not content_type:
        return "other"
    content_type = content_type.lower()
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/"):
        return "audio"
    return "other"


def bytes_to_image_data_uri(raw: bytes, content_type: Optional[str]) -> str:
    media_type = content_type or "image/jpeg"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def download_media(media_url: str, account_sid: str, auth_token: str) -> bytes:
    """Twilio media URLs require HTTP Basic Auth with your account
    credentials - plain urllib rather than adding a 'requests'
    dependency, same low-dependency style as telegram_bot.py."""
    import urllib.request
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode("ascii")).decode("ascii")
    req = urllib.request.Request(media_url, headers={"Authorization": f"Basic {credentials}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def generate_reply(client, model: str, user_text: str, image_data_uri: str = "") -> str:
    """Runs one message through the same tool-calling pipeline as the
    Telegram/Discord bots (run_life_os), returning its reply_text field."""
    from demo_life_os import run_life_os, seed_demo_memory

    seed_demo_memory()
    prompt = user_text or (
        "Here's a photo of my meal - please identify what I ate and log it."
    )
    scenario = {"title": "WhatsApp", "prompt": prompt}
    result = run_life_os(scenario, client, model, max_turns=10,
                          user_message=prompt, image_data_uri=image_data_uri)
    return result.get("reply_text", "").strip() or (
        "I processed that, but didn't have a specific reply to send back - "
        "try asking again or rephrasing."
    )


def _transcribe_audio_bytes(raw: bytes, content_type: Optional[str]) -> str:
    suffix = ".ogg"
    if content_type and "/" in content_type:
        guess = content_type.split("/")[-1].split(";")[0].strip()
        if guess:
            suffix = "." + guess
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(raw)
    try:
        return transcribe_audio(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def handle_incoming(from_number: str, body: str, media_items: List[Tuple[Optional[str], bytes]],
                    llm_client, model: str, allowed_number: str) -> Optional[str]:
    """
    Core message-handling logic, factored out from the Flask webhook
    route so it's unit-testable without a real HTTP request. media_items
    is a list of (content_type, raw_bytes) for each attachment Twilio
    sent (WhatsApp messages carry at most one in practice, but this
    accepts a list for generality).

    Returns the reply text to send back, or None if the message should
    be silently ignored (unauthorized, or genuinely empty).
    """
    if not is_authorized(from_number, allowed_number):
        return None

    text = (body or "").strip()
    is_voice = False
    image_data_uri = ""

    for content_type, raw in media_items:
        kind = classify_media(content_type)
        if kind == "image":
            image_data_uri = bytes_to_image_data_uri(raw, content_type)
        elif kind == "audio":
            try:
                transcript = _transcribe_audio_bytes(raw, content_type)
            except TranscriptionError as e:
                return f"Couldn't process that voice note: {e}"
            if not transcript:
                return "I couldn't make out any speech in that voice note."
            text = transcript
            is_voice = True
        # "other" media types are silently skipped

    if not text and not image_data_uri:
        return None

    try:
        reply = generate_reply(llm_client, model, text, image_data_uri=image_data_uri)
    except Exception as e:  # noqa: BLE001 - never let a bad turn crash the webhook
        reply = f"Something went wrong processing that: {e}"

    if is_voice:
        reply = f'\U0001F3A4 Heard: "{text}"\n\n{reply}'
    elif image_data_uri:
        reply = f"\U0001F4F7 {reply}"

    return reply


def _validate_signature(auth_token: str, url: str, params: dict, signature: str) -> bool:
    """Wraps twilio's RequestValidator in a module-level function so
    tests can monkeypatch this one call instead of reaching into the
    twilio SDK's internals."""
    from twilio.request_validator import RequestValidator
    return RequestValidator(auth_token).validate(url, params, signature)


def _twiml_response(messages: List[str]):
    from flask import Response
    body = "".join(f"<Message>{saxutils.escape(m)}</Message>" for m in messages)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'
    return Response(xml, mimetype="text/xml")


def _require_deps():
    try:
        from flask import Flask, request, Response
    except ImportError as e:
        raise WhatsAppBotError(
            "The 'flask' package is required for the WhatsApp bot.\n"
            "  pip install \"hermes-life-os[whatsapp]\"   # or: pip install flask twilio"
        ) from e
    try:
        import twilio  # noqa: F401 - just checking it's importable
    except ImportError as e:
        raise WhatsAppBotError(
            "The 'twilio' package is required for the WhatsApp bot (used to verify "
            "incoming webhook requests are genuinely from Twilio).\n"
            "  pip install \"hermes-life-os[whatsapp]\"   # or: pip install flask twilio"
        ) from e
    return Flask, request, Response


def build_app(account_sid: str, auth_token: str, allowed_number: str, llm_client, model: str):
    """Constructs and returns the Flask app. Split out from main() so
    tests can build an app instance directly (via Flask's test client)
    without going through argument parsing or app.run()."""
    Flask, request, Response = _require_deps()

    app = Flask(__name__)

    @app.route("/whatsapp/webhook", methods=["POST"])
    def webhook():
        signature = request.headers.get("X-Twilio-Signature", "")
        if not _validate_signature(auth_token, request.url, request.form.to_dict(), signature):
            return Response(status=403)

        from_number = request.form.get("From", "")
        body = request.form.get("Body", "")
        num_media = int(request.form.get("NumMedia", "0") or "0")

        media_items: List[Tuple[Optional[str], bytes]] = []
        for i in range(num_media):
            media_url = request.form.get(f"MediaUrl{i}")
            content_type = request.form.get(f"MediaContentType{i}")
            if not media_url:
                continue
            try:
                raw = download_media(media_url, account_sid, auth_token)
            except Exception as e:  # noqa: BLE001 - surface any download failure to the user
                return _twiml_response([f"Couldn't download that attachment: {e}"])
            media_items.append((content_type, raw))

        reply = handle_incoming(from_number, body, media_items, llm_client, model, allowed_number)
        if reply is None:
            return _twiml_response([])
        return _twiml_response(_split_for_whatsapp(reply))

    return app


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Hermes Life OS WhatsApp bot webhook server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address. Default: 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8766, help="Port to listen on. Default: 8766.")
    parser.add_argument("--provider", default=None,
                        help="LLM backend: ollama, openai, anthropic, openrouter. Default: auto-detect.")
    parser.add_argument("--model", default=None, help="Overrides the provider's default model.")
    parser.add_argument("--profile", default=None,
                        help="Named profile to use. Default: 'default'. Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args()

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    allowed_number = os.environ.get("WHATSAPP_ALLOWED_NUMBER")
    if not account_sid or not auth_token or not allowed_number:
        print("Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and WHATSAPP_ALLOWED_NUMBER first "
              "(see this file's docstring for setup steps).")
        sys.exit(1)

    import storage
    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    from llm_providers import ProviderError, resolve_provider, default_model_for, get_client
    try:
        provider = resolve_provider(args.provider)
        llm_client = get_client(provider)
    except ProviderError as e:
        print(e)
        sys.exit(1)
    model = args.model or default_model_for(provider)

    try:
        app = build_app(account_sid, auth_token, allowed_number, llm_client, model)
    except WhatsAppBotError as e:
        print(e)
        sys.exit(1)

    print(f"Provider: {provider}  Model: {model}  Profile: {storage.ACTIVE_PROFILE}")
    print(f"Listening on http://{args.host}:{args.port}/whatsapp/webhook (Ctrl+C to stop)")
    print("Expose this publicly (e.g. `ngrok http " + str(args.port) + "`) and set the "
          "resulting URL + /whatsapp/webhook as your Twilio sandbox's webhook.")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
