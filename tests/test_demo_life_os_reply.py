"""Tests for demo/demo_life_os.py's reply_text extraction (run_life_os)
and the raw-tool-call-JSON filter (_looks_like_raw_tool_call). Uses a
fake LLM client throughout - no real API/network calls."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def demo_life_os(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "life_score", "achievements", "recommendations", "leaderboard", "tools", "demo_life_os"):
        if mod in sys.modules:
            del sys.modules[mod]
    import demo_life_os as dlo
    importlib.reload(dlo)
    return dlo


def _text_response(content, finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def _tool_call_response(name, arguments, call_id="call_1"):
    tc = SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))
    message = SimpleNamespace(content=None, tool_calls=[tc])
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")])


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, tools, tool_choice, max_tokens):
        return self._responses.pop(0)


class TestLooksLikeRawToolCall:
    def test_detects_name_and_parameters(self, demo_life_os):
        assert demo_life_os._looks_like_raw_tool_call(
            '{"name":"recall","parameters":{"query":"how am i"}}'
        ) is True

    def test_detects_name_and_arguments(self, demo_life_os):
        assert demo_life_os._looks_like_raw_tool_call(
            '{"name": "log_meal", "arguments": {"food": "salad"}}'
        ) is True

    def test_normal_prose_not_flagged(self, demo_life_os):
        assert demo_life_os._looks_like_raw_tool_call("I'm doing great, thanks for asking!") is False

    def test_empty_string_not_flagged(self, demo_life_os):
        assert demo_life_os._looks_like_raw_tool_call("") is False

    def test_json_without_name_key_not_flagged(self, demo_life_os):
        assert demo_life_os._looks_like_raw_tool_call('{"just": "some json"}') is False

    def test_prose_containing_json_not_flagged(self, demo_life_os):
        text = 'Here is an example: {"name":"test"}'
        assert demo_life_os._looks_like_raw_tool_call(text) is False

    def test_invalid_json_not_flagged(self, demo_life_os):
        assert demo_life_os._looks_like_raw_tool_call("{not valid json") is False


class TestRunLifeOsReplyText:
    def test_captures_natural_language_reply(self, demo_life_os):
        client = FakeClient([_text_response("I'm doing well, thanks!")])
        result = demo_life_os.run_life_os(
            {"title": "Test", "prompt": "hi"}, client, "fake-model",
            max_turns=5, user_message="hi",
        )
        assert result["reply_text"] == "I'm doing well, thanks!"

    def test_captures_send_briefing_content(self, demo_life_os):
        client = FakeClient([
            _tool_call_response("send_briefing", {"type": "morning", "content": "Good morning! Sleep was 7h."}),
            _text_response("Let me know if you need anything else!"),
        ])
        result = demo_life_os.run_life_os(
            {"title": "Test", "prompt": "morning briefing"}, client, "fake-model",
            max_turns=5, user_message="morning briefing",
        )
        assert "Good morning! Sleep was 7h." in result["reply_text"]
        assert "Let me know if you need anything else!" in result["reply_text"]

    def test_raw_tool_call_json_excluded_from_reply_text(self, demo_life_os):
        client = FakeClient([_text_response('{"name":"recall","parameters":{"query":"hi"}}')])
        result = demo_life_os.run_life_os(
            {"title": "Test", "prompt": "hi"}, client, "fake-model",
            max_turns=5, user_message="hi",
        )
        assert result["reply_text"] == ""
        assert '"name"' not in result["reply_text"]

    def test_reply_text_key_always_present(self, demo_life_os):
        client = FakeClient([_text_response("ok")])
        result = demo_life_os.run_life_os(
            {"title": "Test", "prompt": "hi"}, client, "fake-model",
            max_turns=5, user_message="hi",
        )
        assert "reply_text" in result


class TestRunLifeOsImageInput:
    def test_image_data_uri_builds_vision_content_array(self, demo_life_os):
        captured = {}

        class CapturingClient:
            def __init__(self):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            def _create(self, model, messages, tools, tool_choice, max_tokens):
                captured["messages"] = messages
                return _text_response("Logged: chicken salad")

        result = demo_life_os.run_life_os(
            {"title": "Test", "prompt": ""}, CapturingClient(), "fake-model",
            max_turns=5, user_message="what did I eat?",
            image_data_uri="data:image/jpeg;base64,QUJD",
        )
        user_msg = captured["messages"][1]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], list)
        text_part = next(p for p in user_msg["content"] if p["type"] == "text")
        image_part = next(p for p in user_msg["content"] if p["type"] == "image_url")
        assert text_part["text"] == "what did I eat?"
        assert image_part["image_url"]["url"] == "data:image/jpeg;base64,QUJD"
        assert result["reply_text"] == "Logged: chicken salad"

    def test_empty_prompt_with_image_uses_default_text(self, demo_life_os):
        captured = {}

        class CapturingClient:
            def __init__(self):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            def _create(self, model, messages, tools, tool_choice, max_tokens):
                captured["messages"] = messages
                return _text_response("ok")

        demo_life_os.run_life_os(
            {"title": "Test", "prompt": ""}, CapturingClient(), "fake-model",
            max_turns=5, user_message="",
            image_data_uri="data:image/jpeg;base64,QUJD",
        )
        user_msg = captured["messages"][1]
        text_part = next(p for p in user_msg["content"] if p["type"] == "text")
        assert text_part["text"]  # non-empty default prompt

    def test_no_image_keeps_plain_string_content(self, demo_life_os):
        client = FakeClient([_text_response("ok")])
        # Reuses the pre-existing plain-string path (no image_data_uri arg) -
        # this is a regression guard, not new behavior.
        result = demo_life_os.run_life_os(
            {"title": "Test", "prompt": "hi"}, client, "fake-model",
            max_turns=5, user_message="hi",
        )
        assert result["reply_text"] == "ok"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
