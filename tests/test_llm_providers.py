"""
Tests for llm_providers.py - provider resolution and the Anthropic <-> OpenAI
message/tool format adapter. No real network calls: the Anthropic client is
mocked, and the openai/ollama/openrouter paths are exercised only up to
client construction (never an actual .create() call).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "demo"))

import pytest

import llm_providers as lp


# ---------------------------------------------------------------------------
# resolve_provider
# ---------------------------------------------------------------------------

class TestResolveProvider:
    def test_explicit_choice_wins(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        assert lp.resolve_provider("openai") == "openai"

    def test_explicit_unknown_raises(self):
        with pytest.raises(lp.ProviderError):
            lp.resolve_provider("not-a-provider")

    def test_env_var_override(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("LIFE_OS_PROVIDER", "openrouter")
        assert lp.resolve_provider(None) == "openrouter"

    def test_autodetect_prefers_anthropic_over_openai(self, monkeypatch):
        monkeypatch.delenv("LIFE_OS_PROVIDER", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("OPENAI_API_KEY", "y")
        assert lp.resolve_provider(None) == "anthropic"

    def test_autodetect_falls_back_to_ollama(self, monkeypatch):
        monkeypatch.delenv("LIFE_OS_PROVIDER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert lp.resolve_provider(None) == "ollama"


class TestGetClientErrors:
    def test_missing_openai_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(lp.ProviderError):
            lp.get_client("openai")

    def test_missing_anthropic_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(lp.ProviderError):
            lp.get_client("anthropic")

    def test_ollama_needs_no_key(self):
        client = lp.get_client("ollama")
        assert client.chat.completions is not None


# ---------------------------------------------------------------------------
# OpenAI-format tools -> Anthropic tool schema
# ---------------------------------------------------------------------------

class TestToolSchemaConversion:
    def test_converts_function_shape_to_input_schema(self):
        tools = [{
            "type": "function",
            "function": {
                "name": "log_meal",
                "description": "Log a meal",
                "parameters": {"type": "object", "properties": {"food": {"type": "string"}}},
            },
        }]
        out = lp._openai_tools_to_anthropic(tools)
        assert out == [{
            "name": "log_meal",
            "description": "Log a meal",
            "input_schema": {"type": "object", "properties": {"food": {"type": "string"}}},
        }]

    def test_empty_or_none_returns_empty_list(self):
        assert lp._openai_tools_to_anthropic(None) == []
        assert lp._openai_tools_to_anthropic([]) == []


# ---------------------------------------------------------------------------
# OpenAI-format message history -> Anthropic message history
# ---------------------------------------------------------------------------

class TestMessageConversion:
    def test_system_message_extracted_separately(self):
        messages = [
            {"role": "system", "content": "You are Hermes."},
            {"role": "user", "content": "hi"},
        ]
        system, out = lp._openai_messages_to_anthropic(messages)
        assert system == "You are Hermes."
        assert out == [{"role": "user", "content": "hi"}]

    def test_assistant_tool_call_becomes_tool_use_block(self):
        messages = [
            {"role": "user", "content": "log lunch"},
            {
                "role": "assistant", "content": "",
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "log_meal", "arguments": json.dumps({"food": "salad"})},
                }],
            },
        ]
        _, out = lp._openai_messages_to_anthropic(messages)
        assert out[1]["role"] == "assistant"
        block = out[1]["content"][0]
        assert block["type"] == "tool_use"
        assert block["id"] == "call_1"
        assert block["name"] == "log_meal"
        assert block["input"] == {"food": "salad"}

    def test_consecutive_tool_results_grouped_into_one_user_message(self):
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "x", "arguments": "{}"}},
                {"id": "b", "type": "function", "function": {"name": "y", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "a", "content": "result-a"},
            {"role": "tool", "tool_call_id": "b", "content": "result-b"},
        ]
        _, out = lp._openai_messages_to_anthropic(messages)
        # assistant message, then exactly one grouped user message with two tool_results
        assert len(out) == 2
        assert out[1]["role"] == "user"
        assert len(out[1]["content"]) == 2
        assert out[1]["content"][0] == {
            "type": "tool_result", "tool_use_id": "a", "content": "result-a"
        }
        assert out[1]["content"][1] == {
            "type": "tool_result", "tool_use_id": "b", "content": "result-b"
        }


# ---------------------------------------------------------------------------
# OpenAI vision content-array -> Anthropic image block (photo meal logging)
# ---------------------------------------------------------------------------

class TestUserContentConversion:
    def test_plain_string_passes_through(self):
        assert lp._openai_user_content_to_anthropic("hello") == "hello"

    def test_none_becomes_empty_string(self):
        assert lp._openai_user_content_to_anthropic(None) == ""

    def test_text_and_image_content_array_converted(self):
        content = [
            {"type": "text", "text": "What did I eat?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
        ]
        blocks = lp._openai_user_content_to_anthropic(content)
        assert blocks[0] == {"type": "text", "text": "What did I eat?"}
        assert blocks[1] == {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"},
        }

    def test_png_media_type_preserved(self):
        content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,XYZ"}}]
        blocks = lp._openai_user_content_to_anthropic(content)
        assert blocks[0]["source"]["media_type"] == "image/png"

    def test_non_data_uri_image_is_dropped_not_raised(self):
        """A remote http(s) image URL can't be embedded inline for
        Anthropic - drop it rather than sending a malformed block."""
        content = [
            {"type": "text", "text": "check this"},
            {"type": "image_url", "image_url": {"url": "https://example.com/pic.jpg"}},
        ]
        blocks = lp._openai_user_content_to_anthropic(content)
        assert blocks == [{"type": "text", "text": "check this"}]

    def test_full_pipeline_user_message_with_image(self):
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "log this meal"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
            ]},
        ]
        _, out = lp._openai_messages_to_anthropic(messages)
        assert out[0]["role"] == "user"
        assert out[0]["content"][0] == {"type": "text", "text": "log this meal"}
        assert out[0]["content"][1]["type"] == "image"
        assert out[0]["content"][1]["source"]["data"] == "QUJD"


# ---------------------------------------------------------------------------
# Anthropic response -> OpenAI-shaped message (the reverse direction)
# ---------------------------------------------------------------------------

class TestResponseConversion:
    def test_text_only_response(self):
        fake_resp = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Good morning!")],
            stop_reason="end_turn",
        )
        result = lp._anthropic_response_to_openai_message(fake_resp)
        msg = result.choices[0].message
        assert msg.content == "Good morning!"
        assert msg.tool_calls is None
        assert result.choices[0].finish_reason == "stop"

    def test_tool_use_response(self):
        fake_resp = SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="Let me check."),
                SimpleNamespace(type="tool_use", id="toolu_1", name="get_profile", input={}),
            ],
            stop_reason="tool_use",
        )
        result = lp._anthropic_response_to_openai_message(fake_resp)
        msg = result.choices[0].message
        assert msg.content == "Let me check."
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "toolu_1"
        assert msg.tool_calls[0].function.name == "get_profile"
        assert json.loads(msg.tool_calls[0].function.arguments) == {}
        assert result.choices[0].finish_reason == "tool_calls"


# ---------------------------------------------------------------------------
# Full round trip through the _AnthropicClient wrapper, with the underlying
# anthropic SDK mocked out entirely.
# ---------------------------------------------------------------------------

class TestAnthropicClientWrapper:
    def test_create_calls_underlying_sdk_and_returns_openai_shape(self):
        mock_sdk_client = MagicMock()
        mock_sdk_client.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Hi there")],
            stop_reason="end_turn",
        )

        wrapper = lp._AnthropicClient(mock_sdk_client)
        resp = wrapper.chat.completions.create(
            model="claude-sonnet-5",
            messages=[
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "hello"},
            ],
            tools=[{"type": "function", "function": {
                "name": "noop", "description": "", "parameters": {"type": "object", "properties": {}}
            }}],
            max_tokens=100,
        )

        assert resp.choices[0].message.content == "Hi there"
        _, kwargs = mock_sdk_client.messages.create.call_args
        assert kwargs["system"] == "Be helpful."
        assert kwargs["model"] == "claude-sonnet-5"
        assert kwargs["max_tokens"] == 100
        assert kwargs["tools"][0]["name"] == "noop"
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
