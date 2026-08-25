"""
Hermes Life OS - Discord Bot
===============================
The Discord counterpart to telegram_bot.py: talk to Hermes from Discord
(DM or a server channel), including photo-based meal logging and voice
message transcription - same underlying pipeline (run_life_os), same
authorization model (only one person's messages are ever processed).

Setup:
    1. Create a Discord application + bot at https://discord.com/developers/applications
       ("New Application" -> "Bot" tab -> "Reset Token" -> copy it).
    2. Under the Bot tab, enable the "Message Content Intent" privileged
       intent (required to read message text/attachments).
    3. Invite the bot to a server you control (OAuth2 -> URL Generator ->
       scopes: bot; permissions: Send Messages, Read Message History,
       Attach Files), or just DM it directly once it's in a shared server.
    4. Find your own Discord user id (enable Developer Mode in Discord's
       settings, then right-click your name -> Copy User ID).
    5. set DISCORD_BOT_TOKEN=...
       set DISCORD_USER_ID=...
    6. pip install "hermes-life-os[discord]"   # or: pip install discord.py
    7. python demo/discord_bot.py

Only messages from DISCORD_USER_ID are ever processed - anyone else
(in a shared server channel, or if the bot is ever added elsewhere) is
silently ignored, so your personal health data stays private. This
works for both DMs and server channels the bot can see.

Photos are supported exactly like the Telegram bot: attach an image
and Hermes uses a vision-capable LLM to identify the meal and log it.
This needs a vision-capable model - see telegram_bot.py's docstring
for the Ollama (llava) setup note, which applies here too.

Voice messages are supported too: Discord's native voice-message
attachments (and any other audio attachment) are downloaded and
transcribed locally via voice_transcribe.py (faster-whisper), exactly
like Telegram voice notes.

Unlike telegram_bot.py's hand-rolled long-polling loop, this uses the
discord.py library's own websocket-based event client (the standard,
supported way to run a Discord bot) - so there's no custom polling or
backoff logic here; discord.py's Client.run() handles the connection
lifecycle itself.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_transcribe import transcribe_audio, TranscriptionError

DISCORD_MAX_MESSAGE_LENGTH = 2000

_IMAGE_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
_AUDIO_CONTENT_TYPE_PREFIX = "audio/"


class DiscordBotError(RuntimeError):
    pass


def is_authorized(user_id: Any, allowed_user_id: Any) -> bool:
    return str(user_id) == str(allowed_user_id)


def _split_for_discord(text: str, limit: int = DISCORD_MAX_MESSAGE_LENGTH) -> List[str]:
    """Discord rejects any single message over 2000 characters - split
    long replies the same way telegram_bot.py does, on line boundaries
    where possible so chunks don't cut a sentence in half mid-word."""
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


def classify_attachment(content_type: Optional[str]) -> str:
    """Buckets a Discord attachment's content_type into 'image', 'audio',
    or 'other' - so the caller knows whether to run vision meal-logging,
    voice transcription, or ignore it."""
    if not content_type:
        return "other"
    content_type = content_type.lower()
    if content_type in _IMAGE_CONTENT_TYPES or content_type.startswith("image/"):
        return "image"
    if content_type.startswith(_AUDIO_CONTENT_TYPE_PREFIX):
        return "audio"
    return "other"


def bytes_to_image_data_uri(raw: bytes, content_type: Optional[str]) -> str:
    """Encodes raw image bytes as a base64 data URI, ready to hand to
    run_life_os(image_data_uri=...)."""
    media_type = content_type or "image/jpeg"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def generate_reply(client, model: str, user_text: str, image_data_uri: str = "") -> str:
    """Runs one message through the same tool-calling pipeline as the
    Telegram bot (run_life_os), returning its reply_text field. Pass
    image_data_uri to attach a photo for meal logging."""
    from demo_life_os import run_life_os, seed_demo_memory

    seed_demo_memory()
    prompt = user_text or (
        "Here's a photo of my meal - please identify what I ate and log it."
    )
    scenario = {"title": "Discord", "prompt": prompt}
    result = run_life_os(scenario, client, model, max_turns=10,
                          user_message=prompt, image_data_uri=image_data_uri)
    return result.get("reply_text", "").strip() or (
        "I processed that, but didn't have a specific reply to send back - "
        "try asking again or rephrasing."
    )


async def transcribe_audio_bytes(raw: bytes, suffix: str = ".ogg") -> str:
    """Writes raw audio bytes to a temp file and transcribes them via
    voice_transcribe.py (faster-whisper), cleaning up afterward. Async
    only so callers in the discord.py event loop don't need a separate
    executor call for the (synchronous) tempfile bookkeeping around it -
    the actual transcription is still a blocking call underneath."""
    import tempfile

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


async def handle_attachment(attachment) -> Tuple[str, str, str]:
    """
    Given a discord.Attachment (or any object exposing async .read()
    plus .content_type/.filename), downloads it and returns
    (kind, text_or_error, image_data_uri) where kind is one of:
      - "image": image_data_uri is populated, text_or_error is "".
      - "audio": text_or_error holds the transcription (or "" if no
        speech was detected).
      - "error": text_or_error holds a human-readable error message.
      - "other": unsupported attachment type, ignored by the caller.
    """
    content_type = getattr(attachment, "content_type", None)
    kind = classify_attachment(content_type)

    if kind == "other":
        return "other", "", ""

    try:
        raw = await attachment.read()
    except Exception as e:  # noqa: BLE001 - surface any download failure to the user
        return "error", f"Couldn't download that attachment: {e}", ""

    if kind == "image":
        return "image", "", bytes_to_image_data_uri(raw, content_type)

    # audio
    suffix = Path(getattr(attachment, "filename", "") or "voice.ogg").suffix or ".ogg"
    try:
        text = await transcribe_audio_bytes(raw, suffix=suffix)
    except TranscriptionError as e:
        return "error", f"Couldn't process that voice message: {e}", ""
    return "audio", text, ""


async def handle_message(message, llm_client, model: str, allowed_user_id: Any) -> Optional[Tuple[str, bool]]:
    """
    Core message-handling logic, factored out from the discord.py event
    loop so it's unit-testable with a fake `message` object (no real
    Discord connection needed). `message` needs: .author.id, .author.bot,
    .content, .attachments (list of objects with .content_type/.filename/
    async .read()).

    Returns (reply_text, is_voice) to send back, or None if the message
    should be silently ignored (unauthorized, from the bot itself, or
    genuinely empty).
    """
    if getattr(message.author, "bot", False):
        return None
    if not is_authorized(message.author.id, allowed_user_id):
        return None

    text = (message.content or "").strip()
    is_voice = False
    image_data_uri = ""

    for attachment in getattr(message, "attachments", []) or []:
        result_kind, payload, uri = await handle_attachment(attachment)
        if result_kind == "error":
            return payload, False
        if result_kind == "image":
            image_data_uri = uri
        elif result_kind == "audio":
            if not payload:
                return "I couldn't make out any speech in that voice message.", False
            text = payload
            is_voice = True
        # "other" attachments are silently skipped

    if not text and not image_data_uri:
        return None  # nothing to respond to

    try:
        reply = generate_reply(llm_client, model, text, image_data_uri=image_data_uri)
    except Exception as e:  # noqa: BLE001 - never let a bad turn crash the bot process
        reply = f"Something went wrong processing that: {e}"

    if is_voice:
        reply = f'\U0001F3A4 Heard: "{text}"\n\n{reply}'
    elif image_data_uri:
        reply = f"\U0001F4F7 {reply}"

    return reply, is_voice


def build_client(allowed_user_id: str, llm_client, model: str):
    """Constructs the actual discord.py Client, wiring handle_message()
    into its on_message event. Imports discord.py lazily so this whole
    module (and its testable helpers above) can be imported/tested
    without discord.py installed - it's an optional extra, same as
    faster-whisper is for voice notes."""
    try:
        import discord
    except ImportError as e:
        raise DiscordBotError(
            "The 'discord.py' package is required for the Discord bot.\n"
            "  pip install \"hermes-life-os[discord]\"   # or: pip install discord.py"
        ) from e

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Hermes Life OS Discord bot logged in as {client.user}. "
              f"Listening for user id {allowed_user_id}...")

    @client.event
    async def on_message(message):
        result = await handle_message(message, llm_client, model, allowed_user_id)
        if result is None:
            return
        reply, _is_voice = result
        for chunk in _split_for_discord(reply):
            await message.channel.send(chunk)

    return client


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Hermes Life OS Discord bot")
    parser.add_argument("--provider", default=None,
                        help="LLM backend: ollama, openai, anthropic, openrouter. "
                             "Default: auto-detect from env vars.")
    parser.add_argument("--model", default=None, help="Overrides the provider's default model.")
    parser.add_argument("--profile", default=None,
                        help="Named profile to use. Default: 'default'. Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args()

    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    allowed_user_id = os.environ.get("DISCORD_USER_ID")
    if not bot_token or not allowed_user_id:
        print("Set DISCORD_BOT_TOKEN and DISCORD_USER_ID first (see this file's docstring for setup steps).")
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
        client = build_client(allowed_user_id, llm_client, model)
    except DiscordBotError as e:
        print(e)
        sys.exit(1)

    print(f"Provider: {provider}  Model: {model}  Profile: {storage.ACTIVE_PROFILE}")
    client.run(bot_token)


if __name__ == "__main__":
    main()
