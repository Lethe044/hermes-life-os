"""Tests for demo/telegram_bot.py. No real network access to Telegram -
get_updates/send_message/generate_reply are monkeypatched throughout."""

from __future__ import annotations

import importlib
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def telegram_bot(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "telegram_bot"):
        if mod in sys.modules:
            del sys.modules[mod]
    import telegram_bot as tb
    importlib.reload(tb)
    return tb


class TestExtractVoice:
    def test_extracts_chat_id_and_file_id(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "voice": {"file_id": "AB123", "duration": 5}}}
        assert telegram_bot.extract_voice(update) == ("555", "AB123")

    def test_none_when_no_voice_key(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "text": "hi"}}
        assert telegram_bot.extract_voice(update) is None

    def test_none_when_no_chat_id(self, telegram_bot):
        update = {"update_id": 1, "message": {"voice": {"file_id": "AB123"}}}
        assert telegram_bot.extract_voice(update) is None

    def test_none_when_voice_missing_file_id(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "voice": {"duration": 5}}}
        assert telegram_bot.extract_voice(update) is None

    def test_none_when_no_message_key(self, telegram_bot):
        assert telegram_bot.extract_voice({"update_id": 1}) is None


class TestGetFilePath:
    def test_returns_file_path_on_success(self, telegram_bot, monkeypatch):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                return json.dumps({"ok": True, "result": {"file_path": "voice/file_0.oga"}}).encode()

        monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", lambda url, timeout=15: FakeResponse())
        result = telegram_bot.get_file_path("token", "AB123")
        assert result == "voice/file_0.oga"

    def test_raises_on_not_ok_response(self, telegram_bot, monkeypatch):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                return json.dumps({"ok": False, "description": "file not found"}).encode()

        monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", lambda url, timeout=15: FakeResponse())
        with pytest.raises(telegram_bot.TelegramError):
            telegram_bot.get_file_path("token", "bad-id")

    def test_raises_telegram_error_on_network_failure(self, telegram_bot, monkeypatch):
        def raise_url_error(*a, **k):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", raise_url_error)
        with pytest.raises(telegram_bot.TelegramError):
            telegram_bot.get_file_path("token", "AB123")


class TestDownloadVoiceFile:
    def test_calls_get_file_path_then_downloads(self, telegram_bot, monkeypatch, tmp_path):
        monkeypatch.setattr(telegram_bot, "get_file_path", lambda token, file_id: "voice/file_0.oga")
        downloaded = {}
        monkeypatch.setattr(telegram_bot.urllib.request, "urlretrieve",
                            lambda url, dest: downloaded.update(url=url, dest=dest))

        dest = str(tmp_path / "out.ogg")
        telegram_bot.download_voice_file("token", "AB123", dest)
        assert downloaded["dest"] == dest
        assert "voice/file_0.oga" in downloaded["url"]

    def test_raises_telegram_error_on_download_failure(self, telegram_bot, monkeypatch, tmp_path):
        monkeypatch.setattr(telegram_bot, "get_file_path", lambda token, file_id: "voice/file_0.oga")

        def raise_url_error(*a, **k):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(telegram_bot.urllib.request, "urlretrieve", raise_url_error)
        with pytest.raises(telegram_bot.TelegramError):
            telegram_bot.download_voice_file("token", "AB123", str(tmp_path / "out.ogg"))


class TestTranscribeVoiceMessage:
    def test_downloads_transcribes_and_cleans_up(self, telegram_bot, monkeypatch):
        downloaded_paths = []

        def fake_download(token, file_id, dest_path):
            downloaded_paths.append(dest_path)
            Path(dest_path).write_bytes(b"fake audio")

        monkeypatch.setattr(telegram_bot, "download_voice_file", fake_download)
        monkeypatch.setattr(telegram_bot, "transcribe_audio", lambda path: "hello world")

        result = telegram_bot._transcribe_voice_message("token", "AB123")
        assert result == "hello world"
        assert not Path(downloaded_paths[0]).exists()  # temp file cleaned up

    def test_temp_file_cleaned_up_even_on_transcription_failure(self, telegram_bot, monkeypatch):
        downloaded_paths = []

        def fake_download(token, file_id, dest_path):
            downloaded_paths.append(dest_path)
            Path(dest_path).write_bytes(b"fake audio")

        def broken_transcribe(path):
            raise telegram_bot.TranscriptionError("model not installed")

        monkeypatch.setattr(telegram_bot, "download_voice_file", fake_download)
        monkeypatch.setattr(telegram_bot, "transcribe_audio", broken_transcribe)

        with pytest.raises(telegram_bot.TranscriptionError):
            telegram_bot._transcribe_voice_message("token", "AB123")
        assert not Path(downloaded_paths[0]).exists()

    def test_download_failure_propagates_and_cleans_up(self, telegram_bot, monkeypatch):
        def broken_download(token, file_id, dest_path):
            raise telegram_bot.TelegramError("download failed")

        monkeypatch.setattr(telegram_bot, "download_voice_file", broken_download)
        with pytest.raises(telegram_bot.TelegramError):
            telegram_bot._transcribe_voice_message("token", "AB123")


class TestExtractMessage:
    def test_extracts_chat_id_and_text(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "text": "hello"}}
        assert telegram_bot.extract_message(update) == ("555", "hello")

    def test_none_when_no_message_key(self, telegram_bot):
        update = {"update_id": 1, "edited_message": {"chat": {"id": 555}, "text": "edited"}}
        assert telegram_bot.extract_message(update) is None

    def test_none_when_no_text(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "sticker": {}}}
        assert telegram_bot.extract_message(update) is None

    def test_none_when_no_chat_id(self, telegram_bot):
        update = {"update_id": 1, "message": {"text": "hi"}}
        assert telegram_bot.extract_message(update) is None


class TestIsAuthorized:
    def test_matching_chat_id(self, telegram_bot):
        assert telegram_bot.is_authorized("555", "555") is True

    def test_mismatched_chat_id(self, telegram_bot):
        assert telegram_bot.is_authorized("555", "999") is False

    def test_handles_int_vs_str_comparison(self, telegram_bot):
        assert telegram_bot.is_authorized(555, "555") is True


class TestCleanForTelegram:
    def test_strips_ansi_codes(self, telegram_bot):
        ansi_text = "\x1b[1mBold\x1b[0m normal \x1b[31mred\x1b[0m"
        assert telegram_bot._clean_for_telegram(ansi_text) == "Bold normal red"

    def test_plain_text_unchanged(self, telegram_bot):
        assert telegram_bot._clean_for_telegram("hello world") == "hello world"


class TestSplitForTelegram:
    def test_short_text_single_chunk(self, telegram_bot):
        assert telegram_bot._split_for_telegram("hello") == ["hello"]

    def test_empty_text_no_chunks(self, telegram_bot):
        assert telegram_bot._split_for_telegram("") == []

    def test_exactly_at_limit_single_chunk(self, telegram_bot):
        assert len(telegram_bot._split_for_telegram("a" * 4096)) == 1

    def test_over_limit_splits_into_multiple_chunks(self, telegram_bot):
        long_text = "line one\n" * 1000
        chunks = telegram_bot._split_for_telegram(long_text)
        assert len(chunks) >= 2
        assert all(len(c) <= 4096 for c in chunks)


class TestGenerateReply:
    def test_calls_run_life_os_and_returns_reply_text(self, telegram_bot, monkeypatch):
        import demo_life_os

        def fake_run_life_os(scenario, client, model, max_turns=10, user_message="", image_data_uri=""):
            return {"reply_text": "Hermes says hi"}

        monkeypatch.setattr(demo_life_os, "run_life_os", fake_run_life_os)
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        result = telegram_bot.generate_reply(client=None, model="x", user_text="hello")
        assert result == "Hermes says hi"

    def test_empty_reply_text_has_fallback(self, telegram_bot, monkeypatch):
        import demo_life_os
        monkeypatch.setattr(demo_life_os, "run_life_os", lambda *a, **k: {"reply_text": ""})
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        result = telegram_bot.generate_reply(client=None, model="x", user_text="hello")
        assert "didn't have a specific reply" in result

    def test_missing_reply_text_key_has_fallback(self, telegram_bot, monkeypatch):
        import demo_life_os
        monkeypatch.setattr(demo_life_os, "run_life_os", lambda *a, **k: {})
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        result = telegram_bot.generate_reply(client=None, model="x", user_text="hello")
        assert "didn't have a specific reply" in result


class TestExtractPhoto:
    def test_extracts_largest_photo_by_file_size(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "photo": [
            {"file_id": "small", "file_size": 1000},
            {"file_id": "large", "file_size": 50000},
            {"file_id": "medium", "file_size": 10000},
        ]}}
        assert telegram_bot.extract_photo(update) == ("555", "large")

    def test_handles_missing_file_size(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "photo": [
            {"file_id": "only"},
        ]}}
        assert telegram_bot.extract_photo(update) == ("555", "only")

    def test_none_when_no_photo_key(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "text": "hi"}}
        assert telegram_bot.extract_photo(update) is None

    def test_none_when_empty_photo_list(self, telegram_bot):
        update = {"update_id": 1, "message": {"chat": {"id": 555}, "photo": []}}
        assert telegram_bot.extract_photo(update) is None

    def test_none_when_no_chat_id(self, telegram_bot):
        update = {"update_id": 1, "message": {"photo": [{"file_id": "x", "file_size": 1}]}}
        assert telegram_bot.extract_photo(update) is None

    def test_none_when_no_message_key(self, telegram_bot):
        assert telegram_bot.extract_photo({"update_id": 1}) is None


class TestDownloadPhotoAsDataUri:
    def test_returns_valid_base64_data_uri(self, telegram_bot, monkeypatch):
        monkeypatch.setattr(telegram_bot, "get_file_path", lambda token, file_id: "photos/file_0.jpg")

        def fake_download(token, file_id, dest_path):
            Path(dest_path).write_bytes(b"\xff\xd8\xff\xe0fakejpegdata")

        monkeypatch.setattr(telegram_bot, "download_telegram_file", fake_download)

        result = telegram_bot._download_photo_as_data_uri("token", "AB123")
        assert result.startswith("data:image/jpeg;base64,")

        import base64
        b64_part = result.split(",", 1)[1]
        assert base64.b64decode(b64_part) == b"\xff\xd8\xff\xe0fakejpegdata"

    def test_infers_media_type_from_extension(self, telegram_bot, monkeypatch):
        monkeypatch.setattr(telegram_bot, "get_file_path", lambda token, file_id: "photos/file_0.png")
        monkeypatch.setattr(telegram_bot, "download_telegram_file",
                            lambda token, file_id, dest_path: Path(dest_path).write_bytes(b"pngdata"))

        result = telegram_bot._download_photo_as_data_uri("token", "AB123")
        assert result.startswith("data:image/png;base64,")

    def test_temp_file_cleaned_up(self, telegram_bot, monkeypatch):
        monkeypatch.setattr(telegram_bot, "get_file_path", lambda token, file_id: "photos/file_0.jpg")
        captured_paths = []

        def fake_download(token, file_id, dest_path):
            captured_paths.append(dest_path)
            Path(dest_path).write_bytes(b"data")

        monkeypatch.setattr(telegram_bot, "download_telegram_file", fake_download)
        telegram_bot._download_photo_as_data_uri("token", "AB123")
        assert not Path(captured_paths[0]).exists()

    def test_temp_file_cleaned_up_even_on_download_failure(self, telegram_bot, monkeypatch):
        monkeypatch.setattr(telegram_bot, "get_file_path", lambda token, file_id: "photos/file_0.jpg")

        def broken_download(token, file_id, dest_path):
            raise telegram_bot.TelegramError("download failed")

        monkeypatch.setattr(telegram_bot, "download_telegram_file", broken_download)
        with pytest.raises(telegram_bot.TelegramError):
            telegram_bot._download_photo_as_data_uri("token", "AB123")


class TestGenerateReplyWithImage:
    def test_passes_image_data_uri_through_to_run_life_os(self, telegram_bot, monkeypatch):
        import demo_life_os
        captured = {}

        def fake_run_life_os(scenario, client, model, max_turns=10, user_message="", image_data_uri=""):
            captured["image_data_uri"] = image_data_uri
            return {"reply_text": "Logged: chicken salad"}

        monkeypatch.setattr(demo_life_os, "run_life_os", fake_run_life_os)
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        result = telegram_bot.generate_reply(client=None, model="x", user_text="",
                                              image_data_uri="data:image/jpeg;base64,abc")
        assert result == "Logged: chicken salad"
        assert captured["image_data_uri"] == "data:image/jpeg;base64,abc"

    def test_empty_caption_uses_default_prompt(self, telegram_bot, monkeypatch):
        import demo_life_os
        captured = {}

        def fake_run_life_os(scenario, client, model, max_turns=10, user_message="", image_data_uri=""):
            captured["prompt"] = user_message
            return {"reply_text": "ok"}

        monkeypatch.setattr(demo_life_os, "run_life_os", fake_run_life_os)
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        telegram_bot.generate_reply(client=None, model="x", user_text="", image_data_uri="data:...")
        assert "photo" in captured["prompt"].lower()

    def test_caption_used_as_prompt_when_present(self, telegram_bot, monkeypatch):
        import demo_life_os
        captured = {}

        def fake_run_life_os(scenario, client, model, max_turns=10, user_message="", image_data_uri=""):
            captured["prompt"] = user_message
            return {"reply_text": "ok"}

        monkeypatch.setattr(demo_life_os, "run_life_os", fake_run_life_os)
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        telegram_bot.generate_reply(client=None, model="x", user_text="that's a big burrito",
                                     image_data_uri="data:...")
        assert captured["prompt"] == "that's a big burrito"


class TestSendMessage:
    def test_splits_long_message_into_multiple_requests(self, telegram_bot, monkeypatch):
        sent_payloads = []

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"ok": True, "result": {}}).encode()

        def fake_urlopen(req, timeout=10):
            sent_payloads.append(json.loads(req.data.decode()))
            return FakeResponse()

        monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", fake_urlopen)
        telegram_bot.send_message("token", "555", "x" * 9000)
        assert len(sent_payloads) == 3
        assert all(len(p["text"]) <= 4096 for p in sent_payloads)


class TestRunBotLoop:
    def test_ignores_unauthorized_chat_id(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 999}, "text": "hi"}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: sent.append(a))
        monkeypatch.setattr(telegram_bot, "generate_reply", lambda *a, **k: "should not be sent")

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert sent == []

    def test_processes_authorized_message_and_replies(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 555}, "text": "log my mood as 8"}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: sent.append((chat_id, text)))
        monkeypatch.setattr(telegram_bot, "generate_reply", lambda client, model, text: f"Logged: {text}")

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert sent == [("555", "Logged: log my mood as 8")]

    def test_advances_offset_past_processed_updates(self, telegram_bot, monkeypatch):
        seen_offsets = []

        def fake_get_updates(bot_token, offset=None, timeout=25):
            seen_offsets.append(offset)
            if offset is None:
                return [{"update_id": 42, "message": {"chat": {"id": 555}, "text": "hi"}}]
            return []

        monkeypatch.setattr(telegram_bot, "get_updates", fake_get_updates)
        monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: None)
        monkeypatch.setattr(telegram_bot, "generate_reply", lambda *a, **k: "ok")

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=2)
        assert seen_offsets == [None, 43]

    def test_generate_reply_exception_sends_error_message_not_crash(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 555}, "text": "hi"}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: sent.append(text))

        def broken_reply(*a, **k):
            raise RuntimeError("LLM exploded")

        monkeypatch.setattr(telegram_bot, "generate_reply", broken_reply)

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert len(sent) == 1
        assert "LLM exploded" in sent[0]

    def test_voice_message_transcribed_and_replied_with_heard_prefix(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 555}, "voice": {"file_id": "AB123"}}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        monkeypatch.setattr(telegram_bot, "_transcribe_voice_message", lambda token, file_id: "how am I doing")
        monkeypatch.setattr(telegram_bot, "generate_reply", lambda client, model, text: f"Reply to: {text}")
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: sent.append((chat_id, text)))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert len(sent) == 1
        chat_id, reply = sent[0]
        assert chat_id == "555"
        assert "how am I doing" in reply  # the heard transcript
        assert "Reply to: how am I doing" in reply  # the actual answer

    def test_voice_message_from_unauthorized_chat_ignored(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 999}, "voice": {"file_id": "AB123"}}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: sent.append(a))
        monkeypatch.setattr(telegram_bot, "_transcribe_voice_message",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert sent == []

    def test_voice_transcription_failure_sends_clear_error(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 555}, "voice": {"file_id": "AB123"}}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)

        def broken_transcribe(token, file_id):
            raise telegram_bot.TranscriptionError("faster-whisper not installed")

        monkeypatch.setattr(telegram_bot, "_transcribe_voice_message", broken_transcribe)
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: sent.append(text))
        monkeypatch.setattr(telegram_bot, "generate_reply",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert len(sent) == 1
        assert "faster-whisper not installed" in sent[0]

    def test_empty_transcription_sends_no_speech_detected_message(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 555}, "voice": {"file_id": "AB123"}}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        monkeypatch.setattr(telegram_bot, "_transcribe_voice_message", lambda token, file_id: "")
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: sent.append(text))
        monkeypatch.setattr(telegram_bot, "generate_reply",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert len(sent) == 1
        assert "couldn't make out any speech" in sent[0].lower()

    def test_text_message_reply_has_no_heard_prefix(self, telegram_bot, monkeypatch):
        """Sanity check that the voice-only 'Heard:' prefix never leaks
        into normal text-message replies."""
        updates = [{"update_id": 1, "message": {"chat": {"id": 555}, "text": "hi"}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        monkeypatch.setattr(telegram_bot, "generate_reply", lambda *a, **k: "plain reply")
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: sent.append(text))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert sent == ["plain reply"]

    def test_photo_message_downloaded_and_replied_with_camera_prefix(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 555},
                    "photo": [{"file_id": "AB123", "file_size": 5000}]}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        monkeypatch.setattr(telegram_bot, "_download_photo_as_data_uri",
                            lambda token, file_id: "data:image/jpeg;base64,fake")
        captured = {}

        def fake_generate_reply(client, model, text, image_data_uri=""):
            captured["text"] = text
            captured["image_data_uri"] = image_data_uri
            return "Logged: grilled chicken and rice"

        monkeypatch.setattr(telegram_bot, "generate_reply", fake_generate_reply)
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: sent.append((chat_id, text)))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert len(sent) == 1
        chat_id, reply = sent[0]
        assert chat_id == "555"
        assert "Logged: grilled chicken and rice" in reply
        assert captured["image_data_uri"] == "data:image/jpeg;base64,fake"

    def test_photo_with_caption_passes_caption_as_text(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 555}, "caption": "my lunch",
                    "photo": [{"file_id": "AB123", "file_size": 5000}]}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        monkeypatch.setattr(telegram_bot, "_download_photo_as_data_uri",
                            lambda token, file_id: "data:image/jpeg;base64,fake")
        captured = {}

        def fake_generate_reply(client, model, text, image_data_uri=""):
            captured["text"] = text
            return "ok"

        monkeypatch.setattr(telegram_bot, "generate_reply", fake_generate_reply)
        monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: None)

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert captured["text"] == "my lunch"

    def test_photo_from_unauthorized_chat_ignored(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 999},
                    "photo": [{"file_id": "AB123", "file_size": 5000}]}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: sent.append(a))
        monkeypatch.setattr(telegram_bot, "_download_photo_as_data_uri",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert sent == []

    def test_photo_download_failure_sends_clear_error(self, telegram_bot, monkeypatch):
        updates = [{"update_id": 1, "message": {"chat": {"id": 555},
                    "photo": [{"file_id": "AB123", "file_size": 5000}]}}]
        monkeypatch.setattr(telegram_bot, "get_updates", lambda *a, **k: updates)

        def broken_download(token, file_id):
            raise telegram_bot.TelegramError("network down")

        monkeypatch.setattr(telegram_bot, "_download_photo_as_data_uri", broken_download)
        sent = []
        monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat_id, text: sent.append(text))
        monkeypatch.setattr(telegram_bot, "generate_reply",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)
        assert len(sent) == 1
        assert "network down" in sent[0]

    def test_get_updates_error_does_not_crash_the_loop(self, telegram_bot, monkeypatch):
        def broken_get_updates(*a, **k):
            raise telegram_bot.TelegramError("network down")

        monkeypatch.setattr(telegram_bot, "get_updates", broken_get_updates)
        monkeypatch.setattr(telegram_bot.time, "sleep", lambda s: None)

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=1)


class TestExponentialBackoff:
    def test_backoff_increases_on_consecutive_failures(self, telegram_bot, monkeypatch):
        monkeypatch.setattr(telegram_bot, "get_updates",
                            lambda *a, **k: (_ for _ in ()).throw(telegram_bot.TelegramError("x")))
        waits = []
        monkeypatch.setattr(telegram_bot.time, "sleep", lambda s: waits.append(s))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=5)
        assert waits == [5, 10, 20, 40, 80]

    def test_backoff_capped_at_five_minutes(self, telegram_bot, monkeypatch):
        monkeypatch.setattr(telegram_bot, "get_updates",
                            lambda *a, **k: (_ for _ in ()).throw(telegram_bot.TelegramError("x")))
        waits = []
        monkeypatch.setattr(telegram_bot.time, "sleep", lambda s: waits.append(s))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=10)
        assert waits[-1] == 300

    def test_backoff_resets_after_success(self, telegram_bot, monkeypatch):
        state = {"fail_count": 0}

        def flaky(bot_token, offset=None, timeout=25):
            state["fail_count"] += 1
            if state["fail_count"] <= 2:
                raise telegram_bot.TelegramError("x")
            return []

        monkeypatch.setattr(telegram_bot, "get_updates", flaky)
        waits = []
        monkeypatch.setattr(telegram_bot.time, "sleep", lambda s: waits.append(s))

        telegram_bot.run_bot("token", "555", client=None, model="x", max_iterations=5)
        assert waits == [5, 10]


class TestGetUpdatesErrorHandling:
    def test_401_raises_clear_token_error(self, telegram_bot, monkeypatch):
        def raise_401(*a, **k):
            raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

        monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", raise_401)
        with pytest.raises(telegram_bot.TelegramError, match="token"):
            telegram_bot.get_updates("bad-token")


class TestMainCli:
    def test_missing_credentials_exits_cleanly(self, telegram_bot, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["telegram_bot.py"]
            telegram_bot.main()
        assert exc_info.value.code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
