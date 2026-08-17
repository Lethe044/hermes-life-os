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

        def fake_run_life_os(scenario, client, model, max_turns=10, user_message=""):
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
