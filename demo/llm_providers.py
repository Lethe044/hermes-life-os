"""
Hermes Life OS - Multi-Provider LLM Client
=============================================
Lets Hermes Life OS run against any of four backends, with zero code
changes anywhere else in the project:

    - ollama      Free, fully local. No API key. Requires a running
                  `ollama serve` with a tool-calling-capable model pulled
                  (e.g. `ollama pull llama3.1`).
    - openai      OPENAI_API_KEY
    - anthropic   ANTHROPIC_API_KEY
    - openrouter  OPENROUTER_API_KEY (original default, incl. Hermes-3)

openai / openrouter / ollama all speak the OpenAI-compatible
`chat.completions` API, so they reuse the `openai` SDK directly with a
swapped base_url. Anthropic's Messages API has a different wire format
(separate `system` param, content-block based messages, `tool_use` /
`tool_result` blocks instead of OpenAI's `tool_calls` / role="tool"), so
`_AnthropicChatCompletions` below adapts it to look exactly like an
OpenAI response object (`resp.choices[0].message.content`,
`.tool_calls[i].id/.function.name/.function.arguments`,
`resp.choices[0].finish_reason`). The rest of the codebase (demo_life_os.py,
tools.py) never needs to know which provider is actually running.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

PROVIDERS = ("ollama", "openai", "anthropic", "openrouter")

DEFAULT_MODELS: Dict[str, str] = {
    "openrouter": "nousresearch/hermes-3-llama-3.1-405b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5",
    "ollama": "llama3.1",
}

_ENV_KEYS: Dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    # ollama needs no key - local server
}

_OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/v1"


class ProviderError(RuntimeError):
    """Raised when a provider can't be initialized (missing key, etc.)."""


def resolve_provider(explicit: Optional[str] = None) -> str:
    """
    Decide which provider to use.

    Priority: explicit --provider flag > LIFE_OS_PROVIDER env var >
    auto-detect the first available API key in this order:
    anthropic, openai, openrouter > fall back to ollama (assumed local,
    no key required - if it isn't running, the first request will fail
    with a clear connection error).
    """
    if explicit:
        explicit = explicit.lower()
        if explicit not in PROVIDERS:
            raise ProviderError(
                f"Unknown provider '{explicit}'. Choose from: {', '.join(PROVIDERS)}"
            )
        return explicit

    env_choice = os.environ.get("LIFE_OS_PROVIDER", "").lower()
    if env_choice:
        if env_choice not in PROVIDERS:
            raise ProviderError(
                f"Unknown LIFE_OS_PROVIDER '{env_choice}'. Choose from: {', '.join(PROVIDERS)}"
            )
        return env_choice

    for provider in ("anthropic", "openai", "openrouter"):
        if os.environ.get(_ENV_KEYS[provider]):
            return provider

    return "ollama"


def default_model_for(provider: str) -> str:
    return DEFAULT_MODELS[provider]


def get_client(provider: str):
    """
    Return an object exposing `.chat.completions.create(model=, messages=,
    tools=, tool_choice=, max_tokens=)` that returns an OpenAI-shaped
    response, regardless of which provider is behind it.
    """
    if provider in ("openai", "openrouter", "ollama"):
        from openai import OpenAI

        if provider == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY")
            if not key:
                raise ProviderError(
                    "Set OPENROUTER_API_KEY first.\n"
                    "  Windows: set OPENROUTER_API_KEY=sk-or-...\n"
                    "  macOS/Linux: export OPENROUTER_API_KEY=sk-or-..."
                )
            return OpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://github.com/Lethe044/hermes-life-os",
                    "X-Title": "Hermes Life OS",
                },
            )

        if provider == "openai":
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ProviderError(
                    "Set OPENAI_API_KEY first.\n"
                    "  Windows: set OPENAI_API_KEY=sk-...\n"
                    "  macOS/Linux: export OPENAI_API_KEY=sk-..."
                )
            return OpenAI(api_key=key)

        # ollama - no key required, local OpenAI-compatible endpoint
        return OpenAI(api_key="ollama", base_url=_OLLAMA_BASE_URL)

    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError(
                "Set ANTHROPIC_API_KEY first.\n"
                "  Windows: set ANTHROPIC_API_KEY=sk-ant-...\n"
                "  macOS/Linux: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError(
                "The 'anthropic' package is required for --provider anthropic.\n"
                "  pip install anthropic"
            ) from e
        return _AnthropicClient(anthropic.Anthropic(api_key=key))

    raise ProviderError(f"Unknown provider '{provider}'. Choose from: {', '.join(PROVIDERS)}")


# ---------------------------------------------------------------------------
# Anthropic adapter - makes the Messages API look like OpenAI's
# chat.completions API so the rest of the codebase is untouched.
# ---------------------------------------------------------------------------

def _openai_tools_to_anthropic(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not tools:
        return []
    out = []
    for t in tools:
        fn = t["function"]
        out.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


def _openai_user_content_to_anthropic(content: Any) -> Any:
    """
    Convert an OpenAI-style user message `content` field to Anthropic's
    content-block format.

    OpenAI/Ollama/OpenRouter accept a plain string, or (for vision) a
    list of content parts:
        [{"type": "text", "text": "..."},
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,XXXX"}}]

    Anthropic's Messages API wants the same idea but shaped differently:
        [{"type": "text", "text": "..."},
         {"type": "image", "source": {"type": "base64",
                                       "media_type": "image/jpeg",
                                       "data": "XXXX"}}]

    Plain strings pass through unchanged (Anthropic accepts a bare
    string for `content` too).
    """
    if isinstance(content, str) or content is None:
        return content or ""

    blocks: List[Dict[str, Any]] = []
    for part in content:
        part_type = part.get("type")
        if part_type == "text":
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif part_type == "image_url":
            url = part.get("image_url", {}).get("url", "")
            # Expected shape: "data:<media_type>;base64,<data>"
            if url.startswith("data:") and ";base64," in url:
                header, data = url.split(";base64,", 1)
                media_type = header[len("data:"):] or "image/jpeg"
            else:
                # Not a data URI we can embed inline - drop rather than
                # send Anthropic something it will reject outright.
                continue
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            })
        # Unknown part types are skipped rather than raising, so a
        # provider-specific content part never breaks the Anthropic path.
    return blocks


def _openai_messages_to_anthropic(messages: List[Dict[str, Any]]):
    """
    Split an OpenAI-format message list into (system_text, anthropic_messages).
    Consecutive role="tool" messages are grouped into a single Anthropic
    user message containing multiple tool_result blocks, since Anthropic
    has no standalone "tool" role.
    """
    system_parts: List[str] = []
    out: List[Dict[str, Any]] = []
    pending_tool_results: List[Dict[str, Any]] = []

    def flush_tool_results():
        if pending_tool_results:
            out.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

    for m in messages:
        role = m["role"]

        if role == "system":
            if m.get("content"):
                system_parts.append(m["content"])
            continue

        if role == "tool":
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": m["tool_call_id"],
                "content": str(m.get("content", "")),
            })
            continue

        # any non-tool message ends a run of tool results
        flush_tool_results()

        if role == "user":
            out.append({"role": "user", "content": _openai_user_content_to_anthropic(m.get("content"))})

        elif role == "assistant":
            blocks: List[Dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls", []) or []:
                try:
                    tool_input = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    tool_input = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": tool_input,
                })
            if not blocks:
                blocks = [{"type": "text", "text": ""}]
            out.append({"role": "assistant", "content": blocks})

    flush_tool_results()
    return "\n\n".join(system_parts), out


def _anthropic_response_to_openai_message(resp) -> SimpleNamespace:
    text_parts: List[str] = []
    tool_calls: List[SimpleNamespace] = []

    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(SimpleNamespace(
                id=block.id,
                function=SimpleNamespace(
                    name=block.name,
                    arguments=json.dumps(block.input),
                ),
            ))

    finish_reason = "tool_calls" if tool_calls else (
        "stop" if resp.stop_reason == "end_turn" else resp.stop_reason
    )

    message = SimpleNamespace(
        content="".join(text_parts),
        tool_calls=tool_calls or None,
    )
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


class _AnthropicCompletions:
    def __init__(self, client):
        self._client = client

    def create(self, model: str, messages: List[Dict[str, Any]],
               tools: Optional[List[Dict[str, Any]]] = None,
               tool_choice: str = "auto", max_tokens: int = 1500, **_ignored):
        system_text, anthropic_messages = _openai_messages_to_anthropic(messages)
        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
        }
        if system_text:
            kwargs["system"] = system_text
        anthropic_tools = _openai_tools_to_anthropic(tools)
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        resp = self._client.messages.create(**kwargs)
        return _anthropic_response_to_openai_message(resp)


class _AnthropicChat:
    def __init__(self, client):
        self.completions = _AnthropicCompletions(client)


class _AnthropicClient:
    """Wraps anthropic.Anthropic so `.chat.completions.create(...)` works
    exactly like the OpenAI SDK, returning OpenAI-shaped responses."""

    def __init__(self, client):
        self.chat = _AnthropicChat(client)
