"""Tests for demo/discord_bot.py. No real Discord connection: discord.py
itself is never imported by these tests (build_client/main are the only
functions that touch it, and they're exercised only up to the
ImportError-guard / argument-validation level). handle_message() and its
helpers are pure/async-pure and tested directly with fake message and
attachment objects."""

from __future__ import annotations

import asyncio
import base64
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def discord_bot(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "discord_bot"):
        if mod in sys.modules:
            del sys.modules[mod]
    import discord_bot as db
    importlib.reload(db)
    return db


def run(coro):
    return asyncio.run(coro)


class FakeAttachment:
    def __init__(self, content_type, data=b"", filename="file.bin", read_error=None):
        self.content_type = content_type
        self.filename = filename
        self._data = data
        self._read_error = read_error

    async def read(self):
        if self._read_error:
            raise self._read_error
        return self._data


class FakeAuthor:
    def __init__(self, id, bot=False):
        self.id = id
        self.bot = bot


class FakeMessage:
    def __init__(self, author_id, content="", attachments=None, is_bot=False):
        self.author = FakeAuthor(author_id, bot=is_bot)
        self.content = content
        self.attachments = attachments or []


class TestIsAuthorized:
    def test_matching_id(self, discord_bot):
        assert discord_bot.is_authorized("555", "555") is True

    def test_mismatched_id(self, discord_bot):
        assert discord_bot.is_authorized("555", "999") is False

    def test_handles_int_vs_str(self, discord_bot):
        assert discord_bot.is_authorized(555, "555") is True


class TestSplitForDiscord:
    def test_short_text_single_chunk(self, discord_bot):
        assert discord_bot._split_for_discord("hello") == ["hello"]

    def test_empty_text_no_chunks(self, discord_bot):
        assert discord_bot._split_for_discord("") == []

    def test_exactly_at_limit_single_chunk(self, discord_bot):
        assert len(discord_bot._split_for_discord("a" * 2000)) == 1

    def test_over_limit_splits_into_multiple_chunks(self, discord_bot):
        long_text = "line one\n" * 500
        chunks = discord_bot._split_for_discord(long_text)
        assert len(chunks) >= 2
        assert all(len(c) <= 2000 for c in chunks)


class TestClassifyAttachment:
    def test_jpeg_is_image(self, discord_bot):
        assert discord_bot.classify_attachment("image/jpeg") == "image"

    def test_png_is_image(self, discord_bot):
        assert discord_bot.classify_attachment("image/png") == "image"

    def test_ogg_audio_is_audio(self, discord_bot):
        assert discord_bot.classify_attachment("audio/ogg") == "audio"

    def test_pdf_is_other(self, discord_bot):
        assert discord_bot.classify_attachment("application/pdf") == "other"

    def test_none_is_other(self, discord_bot):
        assert discord_bot.classify_attachment(None) == "other"


class TestBytesToImageDataUri:
    def test_encodes_correctly(self, discord_bot):
        result = discord_bot.bytes_to_image_data_uri(b"fakejpegdata", "image/jpeg")
        assert result.startswith("data:image/jpeg;base64,")
        b64_part = result.split(",", 1)[1]
        assert base64.b64decode(b64_part) == b"fakejpegdata"

    def test_defaults_to_jpeg_media_type(self, discord_bot):
        result = discord_bot.bytes_to_image_data_uri(b"data", None)
        assert result.startswith("data:image/jpeg;base64,")


class TestGenerateReply:
    def test_calls_run_life_os_and_returns_reply_text(self, discord_bot, monkeypatch):
        import demo_life_os
        monkeypatch.setattr(demo_life_os, "run_life_os",
                            lambda *a, **k: {"reply_text": "Hermes says hi"})
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        result = discord_bot.generate_reply(client=None, model="x", user_text="hello")
        assert result == "Hermes says hi"

    def test_empty_reply_has_fallback(self, discord_bot, monkeypatch):
        import demo_life_os
        monkeypatch.setattr(demo_life_os, "run_life_os", lambda *a, **k: {"reply_text": ""})
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        result = discord_bot.generate_reply(client=None, model="x", user_text="hello")
        assert "didn't have a specific reply" in result

    def test_passes_image_data_uri_through(self, discord_bot, monkeypatch):
        import demo_life_os
        captured = {}

        def fake_run_life_os(scenario, client, model, max_turns=10, user_message="", image_data_uri=""):
            captured["uri"] = image_data_uri
            return {"reply_text": "Logged: pasta"}

        monkeypatch.setattr(demo_life_os, "run_life_os", fake_run_life_os)
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        discord_bot.generate_reply(client=None, model="x", user_text="",
                                   image_data_uri="data:image/jpeg;base64,abc")
        assert captured["uri"] == "data:image/jpeg;base64,abc"


class TestHandleAttachment:
    def test_image_attachment_returns_data_uri(self, discord_bot):
        att = FakeAttachment("image/jpeg", data=b"jpegbytes")
        kind, text, uri = run(discord_bot.handle_attachment(att))
        assert kind == "image"
        assert text == ""
        assert uri.startswith("data:image/jpeg;base64,")

    def test_audio_attachment_transcribed(self, discord_bot, monkeypatch):
        monkeypatch.setattr(discord_bot, "transcribe_audio_bytes",
                            lambda raw, suffix=".ogg": _async_return("logged a workout"))
        att = FakeAttachment("audio/ogg", data=b"audiobytes", filename="voice.ogg")
        kind, text, uri = run(discord_bot.handle_attachment(att))
        assert kind == "audio"
        assert text == "logged a workout"
        assert uri == ""

    def test_audio_transcription_failure_returns_error(self, discord_bot, monkeypatch):
        async def broken(raw, suffix=".ogg"):
            raise discord_bot.TranscriptionError("model not installed")

        monkeypatch.setattr(discord_bot, "transcribe_audio_bytes", broken)
        att = FakeAttachment("audio/ogg", data=b"audiobytes")
        kind, text, uri = run(discord_bot.handle_attachment(att))
        assert kind == "error"
        assert "model not installed" in text

    def test_other_content_type_ignored(self, discord_bot):
        att = FakeAttachment("application/pdf", data=b"pdfbytes")
        kind, text, uri = run(discord_bot.handle_attachment(att))
        assert kind == "other"

    def test_download_failure_returns_error(self, discord_bot):
        att = FakeAttachment("image/jpeg", read_error=RuntimeError("connection reset"))
        kind, text, uri = run(discord_bot.handle_attachment(att))
        assert kind == "error"
        assert "connection reset" in text


async def _async_return(value):
    return value


class TestHandleMessage:
    def test_ignores_bot_authors(self, discord_bot):
        msg = FakeMessage(author_id=555, content="hi", is_bot=True)
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        assert result is None

    def test_ignores_unauthorized_user(self, discord_bot):
        msg = FakeMessage(author_id=999, content="hi")
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        assert result is None

    def test_ignores_empty_message_no_attachments(self, discord_bot):
        msg = FakeMessage(author_id=555, content="")
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        assert result is None

    def test_plain_text_message_gets_reply(self, discord_bot, monkeypatch):
        monkeypatch.setattr(discord_bot, "generate_reply",
                            lambda client, model, text, image_data_uri="": f"Reply to: {text}")
        msg = FakeMessage(author_id=555, content="how am I doing")
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        assert result == ("Reply to: how am I doing", False)

    def test_image_attachment_triggers_vision_reply_with_camera_prefix(self, discord_bot, monkeypatch):
        captured = {}

        def fake_generate_reply(client, model, text, image_data_uri=""):
            captured["uri"] = image_data_uri
            return "Logged: chicken salad"

        monkeypatch.setattr(discord_bot, "generate_reply", fake_generate_reply)
        att = FakeAttachment("image/jpeg", data=b"jpegbytes")
        msg = FakeMessage(author_id=555, content="", attachments=[att])
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        reply, is_voice = result
        assert "Logged: chicken salad" in reply
        assert reply.startswith("\U0001F4F7")
        assert is_voice is False
        assert captured["uri"].startswith("data:image/jpeg;base64,")

    def test_audio_attachment_triggers_heard_prefix(self, discord_bot, monkeypatch):
        async def fake_transcribe(raw, suffix=".ogg"):
            return "log my mood as 8"

        monkeypatch.setattr(discord_bot, "transcribe_audio_bytes", fake_transcribe)
        monkeypatch.setattr(discord_bot, "generate_reply",
                            lambda client, model, text, image_data_uri="": f"Logged: {text}")
        att = FakeAttachment("audio/ogg", data=b"audiobytes")
        msg = FakeMessage(author_id=555, content="", attachments=[att])
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        reply, is_voice = result
        assert is_voice is True
        assert "log my mood as 8" in reply
        assert "Logged: log my mood as 8" in reply

    def test_empty_transcription_short_circuits_with_no_speech_message(self, discord_bot, monkeypatch):
        async def fake_transcribe(raw, suffix=".ogg"):
            return ""

        monkeypatch.setattr(discord_bot, "transcribe_audio_bytes", fake_transcribe)
        monkeypatch.setattr(discord_bot, "generate_reply",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))
        att = FakeAttachment("audio/ogg", data=b"audiobytes")
        msg = FakeMessage(author_id=555, content="", attachments=[att])
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        reply, is_voice = result
        assert "couldn't make out any speech" in reply.lower()

    def test_attachment_download_failure_short_circuits_with_error(self, discord_bot, monkeypatch):
        monkeypatch.setattr(discord_bot, "generate_reply",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))
        att = FakeAttachment("image/jpeg", read_error=RuntimeError("connection reset"))
        msg = FakeMessage(author_id=555, content="", attachments=[att])
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        reply, is_voice = result
        assert "connection reset" in reply

    def test_generate_reply_exception_does_not_crash(self, discord_bot, monkeypatch):
        def broken(*a, **k):
            raise RuntimeError("LLM exploded")

        monkeypatch.setattr(discord_bot, "generate_reply", broken)
        msg = FakeMessage(author_id=555, content="hi")
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        reply, is_voice = result
        assert "LLM exploded" in reply

    def test_other_attachment_type_silently_skipped(self, discord_bot, monkeypatch):
        monkeypatch.setattr(discord_bot, "generate_reply",
                            lambda client, model, text, image_data_uri="": f"Reply to: {text}")
        att = FakeAttachment("application/pdf", data=b"pdfbytes")
        msg = FakeMessage(author_id=555, content="check this out", attachments=[att])
        result = run(discord_bot.handle_message(msg, llm_client=None, model="x", allowed_user_id="555"))
        reply, is_voice = result
        assert reply == "Reply to: check this out"


class TestBuildClientRequiresDiscordPy:
    def test_raises_clear_error_when_discord_not_installed(self, discord_bot, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "discord":
                raise ImportError("No module named 'discord'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(discord_bot.DiscordBotError, match="discord.py"):
            discord_bot.build_client("555", llm_client=None, model="x")


class TestMainCli:
    def test_missing_credentials_exits_cleanly(self, discord_bot, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DISCORD_USER_ID", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["discord_bot.py"]
            discord_bot.main()
        assert exc_info.value.code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
