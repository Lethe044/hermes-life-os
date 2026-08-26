"""Tests for demo/whatsapp_bot.py. No real Twilio/network calls: the
signature-validation call (_validate_signature) is monkeypatched in
every Flask-route test, and handle_incoming()/its helpers are pure
functions tested directly."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

pytest.importorskip("flask")
pytest.importorskip("twilio")


@pytest.fixture()
def whatsapp_bot(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "whatsapp_bot"):
        if mod in sys.modules:
            del sys.modules[mod]
    import whatsapp_bot as wb
    importlib.reload(wb)
    return wb


class TestIsAuthorized:
    def test_matching_number(self, whatsapp_bot):
        assert whatsapp_bot.is_authorized("whatsapp:+15551234567", "whatsapp:+15551234567") is True

    def test_mismatched_number(self, whatsapp_bot):
        assert whatsapp_bot.is_authorized("whatsapp:+15551234567", "whatsapp:+19999999999") is False

    def test_whitespace_trimmed(self, whatsapp_bot):
        assert whatsapp_bot.is_authorized(" whatsapp:+15551234567 ", "whatsapp:+15551234567") is True


class TestSplitForWhatsapp:
    def test_short_text_single_chunk(self, whatsapp_bot):
        assert whatsapp_bot._split_for_whatsapp("hi") == ["hi"]

    def test_empty_text_no_chunks(self, whatsapp_bot):
        assert whatsapp_bot._split_for_whatsapp("") == []

    def test_long_text_splits(self, whatsapp_bot):
        long_text = "line\n" * 500
        chunks = whatsapp_bot._split_for_whatsapp(long_text)
        assert len(chunks) >= 2
        assert all(len(c) <= whatsapp_bot.WHATSAPP_MAX_MESSAGE_LENGTH for c in chunks)


class TestClassifyMedia:
    def test_image_jpeg(self, whatsapp_bot):
        assert whatsapp_bot.classify_media("image/jpeg") == "image"

    def test_audio_ogg(self, whatsapp_bot):
        assert whatsapp_bot.classify_media("audio/ogg") == "audio"

    def test_pdf_is_other(self, whatsapp_bot):
        assert whatsapp_bot.classify_media("application/pdf") == "other"

    def test_none_is_other(self, whatsapp_bot):
        assert whatsapp_bot.classify_media(None) == "other"


class TestBytesToImageDataUri:
    def test_encodes_correctly(self, whatsapp_bot):
        import base64
        result = whatsapp_bot.bytes_to_image_data_uri(b"jpegdata", "image/jpeg")
        assert result.startswith("data:image/jpeg;base64,")
        assert base64.b64decode(result.split(",", 1)[1]) == b"jpegdata"


class TestDownloadMedia:
    def test_sends_basic_auth_header(self, whatsapp_bot, monkeypatch):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return b"mediabytes"

        def fake_urlopen(req, timeout=30):
            captured["auth_header"] = req.get_header("Authorization")
            return FakeResponse()

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        result = whatsapp_bot.download_media("https://api.twilio.com/media/123", "SID", "TOKEN")
        assert result == b"mediabytes"
        assert captured["auth_header"].startswith("Basic ")


class TestGenerateReply:
    def test_calls_run_life_os_and_returns_reply_text(self, whatsapp_bot, monkeypatch):
        import demo_life_os
        monkeypatch.setattr(demo_life_os, "run_life_os", lambda *a, **k: {"reply_text": "hi there"})
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        result = whatsapp_bot.generate_reply(client=None, model="x", user_text="hello")
        assert result == "hi there"

    def test_empty_reply_has_fallback(self, whatsapp_bot, monkeypatch):
        import demo_life_os
        monkeypatch.setattr(demo_life_os, "run_life_os", lambda *a, **k: {"reply_text": ""})
        monkeypatch.setattr(demo_life_os, "seed_demo_memory", lambda: None)

        result = whatsapp_bot.generate_reply(client=None, model="x", user_text="hello")
        assert "didn't have a specific reply" in result


class TestHandleIncoming:
    def test_unauthorized_number_ignored(self, whatsapp_bot):
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+19999999999", "hi", [], llm_client=None, model="x",
            allowed_number="whatsapp:+15551234567",
        )
        assert result is None

    def test_empty_message_no_media_ignored(self, whatsapp_bot):
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+15551234567", "", [], llm_client=None, model="x",
            allowed_number="whatsapp:+15551234567",
        )
        assert result is None

    def test_plain_text_gets_reply(self, whatsapp_bot, monkeypatch):
        monkeypatch.setattr(whatsapp_bot, "generate_reply",
                            lambda client, model, text, image_data_uri="": f"Reply: {text}")
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+15551234567", "how am I doing", [], llm_client=None, model="x",
            allowed_number="whatsapp:+15551234567",
        )
        assert result == "Reply: how am I doing"

    def test_image_media_triggers_vision_reply_with_camera_prefix(self, whatsapp_bot, monkeypatch):
        captured = {}

        def fake_generate_reply(client, model, text, image_data_uri=""):
            captured["uri"] = image_data_uri
            return "Logged: tacos"

        monkeypatch.setattr(whatsapp_bot, "generate_reply", fake_generate_reply)
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+15551234567", "", [("image/jpeg", b"jpegbytes")],
            llm_client=None, model="x", allowed_number="whatsapp:+15551234567",
        )
        assert result.startswith("\U0001F4F7")
        assert "Logged: tacos" in result
        assert captured["uri"].startswith("data:image/jpeg;base64,")

    def test_audio_media_triggers_heard_prefix(self, whatsapp_bot, monkeypatch):
        monkeypatch.setattr(whatsapp_bot, "_transcribe_audio_bytes",
                            lambda raw, content_type: "log my mood as 8")
        monkeypatch.setattr(whatsapp_bot, "generate_reply",
                            lambda client, model, text, image_data_uri="": f"Logged: {text}")
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+15551234567", "", [("audio/ogg", b"audiobytes")],
            llm_client=None, model="x", allowed_number="whatsapp:+15551234567",
        )
        assert "log my mood as 8" in result
        assert "Logged: log my mood as 8" in result

    def test_empty_transcription_short_circuits(self, whatsapp_bot, monkeypatch):
        monkeypatch.setattr(whatsapp_bot, "_transcribe_audio_bytes", lambda raw, content_type: "")
        monkeypatch.setattr(whatsapp_bot, "generate_reply",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+15551234567", "", [("audio/ogg", b"audiobytes")],
            llm_client=None, model="x", allowed_number="whatsapp:+15551234567",
        )
        assert "couldn't make out any speech" in result.lower()

    def test_transcription_failure_returns_error(self, whatsapp_bot, monkeypatch):
        def broken(raw, content_type):
            raise whatsapp_bot.TranscriptionError("model not installed")

        monkeypatch.setattr(whatsapp_bot, "_transcribe_audio_bytes", broken)
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+15551234567", "", [("audio/ogg", b"audiobytes")],
            llm_client=None, model="x", allowed_number="whatsapp:+15551234567",
        )
        assert "model not installed" in result

    def test_generate_reply_exception_does_not_crash(self, whatsapp_bot, monkeypatch):
        def broken(*a, **k):
            raise RuntimeError("LLM exploded")

        monkeypatch.setattr(whatsapp_bot, "generate_reply", broken)
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+15551234567", "hi", [], llm_client=None, model="x",
            allowed_number="whatsapp:+15551234567",
        )
        assert "LLM exploded" in result

    def test_other_media_type_silently_skipped(self, whatsapp_bot, monkeypatch):
        monkeypatch.setattr(whatsapp_bot, "generate_reply",
                            lambda client, model, text, image_data_uri="": f"Reply: {text}")
        result = whatsapp_bot.handle_incoming(
            "whatsapp:+15551234567", "check this", [("application/pdf", b"pdfbytes")],
            llm_client=None, model="x", allowed_number="whatsapp:+15551234567",
        )
        assert result == "Reply: check this"


class TestWebhookRoute:
    def _build_app(self, whatsapp_bot, monkeypatch, reply_text="Reply: hi"):
        monkeypatch.setattr(whatsapp_bot, "_validate_signature", lambda *a, **k: True)
        monkeypatch.setattr(whatsapp_bot, "generate_reply",
                            lambda client, model, text, image_data_uri="": reply_text)
        app = whatsapp_bot.build_app("SID", "TOKEN", "whatsapp:+15551234567", llm_client=None, model="x")
        app.config["TESTING"] = True
        return app

    def test_valid_signature_authorized_number_gets_twiml_reply(self, whatsapp_bot, monkeypatch):
        app = self._build_app(whatsapp_bot, monkeypatch, reply_text="Reply: hi")
        with app.test_client() as c:
            resp = c.post("/whatsapp/webhook", data={
                "From": "whatsapp:+15551234567", "Body": "hi", "NumMedia": "0",
            })
        assert resp.status_code == 200
        assert b"<Message>Reply: hi</Message>" in resp.data
        assert resp.content_type.startswith("text/xml")

    def test_invalid_signature_rejected(self, whatsapp_bot, monkeypatch):
        monkeypatch.setattr(whatsapp_bot, "_validate_signature", lambda *a, **k: False)
        app = whatsapp_bot.build_app("SID", "TOKEN", "whatsapp:+15551234567", llm_client=None, model="x")
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.post("/whatsapp/webhook", data={
                "From": "whatsapp:+15551234567", "Body": "hi", "NumMedia": "0",
            })
        assert resp.status_code == 403

    def test_unauthorized_number_gets_empty_twiml(self, whatsapp_bot, monkeypatch):
        app = self._build_app(whatsapp_bot, monkeypatch)
        with app.test_client() as c:
            resp = c.post("/whatsapp/webhook", data={
                "From": "whatsapp:+19999999999", "Body": "hi", "NumMedia": "0",
            })
        assert resp.status_code == 200
        assert b"<Message>" not in resp.data

    def test_media_downloaded_and_passed_through(self, whatsapp_bot, monkeypatch):
        monkeypatch.setattr(whatsapp_bot, "_validate_signature", lambda *a, **k: True)
        monkeypatch.setattr(whatsapp_bot, "download_media", lambda url, sid, token: b"jpegbytes")
        captured = {}

        def fake_generate_reply(client, model, text, image_data_uri=""):
            captured["uri"] = image_data_uri
            return "Logged: pizza"

        monkeypatch.setattr(whatsapp_bot, "generate_reply", fake_generate_reply)
        app = whatsapp_bot.build_app("SID", "TOKEN", "whatsapp:+15551234567", llm_client=None, model="x")
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.post("/whatsapp/webhook", data={
                "From": "whatsapp:+15551234567", "Body": "", "NumMedia": "1",
                "MediaUrl0": "https://api.twilio.com/media/abc", "MediaContentType0": "image/jpeg",
            })
        assert resp.status_code == 200
        assert b"Logged: pizza" in resp.data
        assert captured["uri"].startswith("data:image/jpeg;base64,")

    def test_media_download_failure_returns_error_twiml(self, whatsapp_bot, monkeypatch):
        monkeypatch.setattr(whatsapp_bot, "_validate_signature", lambda *a, **k: True)

        def broken_download(url, sid, token):
            raise RuntimeError("network down")

        monkeypatch.setattr(whatsapp_bot, "download_media", broken_download)
        app = whatsapp_bot.build_app("SID", "TOKEN", "whatsapp:+15551234567", llm_client=None, model="x")
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.post("/whatsapp/webhook", data={
                "From": "whatsapp:+15551234567", "Body": "", "NumMedia": "1",
                "MediaUrl0": "https://api.twilio.com/media/abc", "MediaContentType0": "image/jpeg",
            })
        assert resp.status_code == 200
        assert b"network down" in resp.data


class TestBuildAppRequiresDeps:
    def test_raises_clear_error_when_flask_not_installed(self, whatsapp_bot, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "flask":
                raise ImportError("No module named 'flask'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(whatsapp_bot.WhatsAppBotError, match="flask"):
            whatsapp_bot.build_app("SID", "TOKEN", "whatsapp:+1", llm_client=None, model="x")

    def test_raises_clear_error_when_twilio_not_installed(self, whatsapp_bot, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "twilio":
                raise ImportError("No module named 'twilio'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(whatsapp_bot.WhatsAppBotError, match="twilio"):
            whatsapp_bot.build_app("SID", "TOKEN", "whatsapp:+1", llm_client=None, model="x")


class TestMainCli:
    def test_missing_credentials_exits_cleanly(self, whatsapp_bot, monkeypatch):
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("WHATSAPP_ALLOWED_NUMBER", raising=False)
        monkeypatch.setattr(sys, "argv", ["whatsapp_bot.py"])
        with pytest.raises(SystemExit) as exc_info:
            whatsapp_bot.main()
        assert exc_info.value.code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
