"""Tests for demo/slack_bot.py. No real Slack connection: slack_bolt
itself is only imported inside build_app()/main() (guarded by
SlackBotError), so resolve_profile()/handle_message() and their helpers
are tested directly with plain event dicts - the same pattern
test_discord_bot.py uses for discord.py."""

from __future__ import annotations

import base64
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def slack_bot(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "users", "slack_bot"):
        if mod in sys.modules:
            del sys.modules[mod]
    import slack_bot as sb
    importlib.reload(sb)
    sb.storage.set_active_profile(None)
    return sb


class TestResolveProfile:
    def test_single_user_match(self, slack_bot):
        authorized, profile, username = slack_bot.resolve_profile("U0123", "U0123")
        assert authorized is True
        assert profile is None  # keep whatever profile is already active
        assert username is None

    def test_single_user_mismatch(self, slack_bot):
        authorized, profile, username = slack_bot.resolve_profile("U9999", "U0123")
        assert authorized is False

    def test_no_allowed_user_configured_falls_through_to_registry(self, slack_bot):
        authorized, _profile, _username = slack_bot.resolve_profile("U0123", None)
        assert authorized is False  # no link registered either

    def test_multi_user_link_match(self, slack_bot):
        slack_bot.users_mod.add_user("alex", profile="alex")
        slack_bot.users_mod.link_channel("alex", "slack", "U0123")
        authorized, profile, username = slack_bot.resolve_profile("U0123", None)
        assert authorized is True
        assert profile == "alex"
        assert username == "alex"

    def test_multi_user_no_link_unauthorized(self, slack_bot):
        slack_bot.users_mod.add_user("alex", profile="alex")
        authorized, _profile, _username = slack_bot.resolve_profile("U9999", None)
        assert authorized is False

    def test_single_user_takes_priority_over_registry(self, slack_bot):
        slack_bot.users_mod.add_user("alex", profile="alex")
        slack_bot.users_mod.link_channel("alex", "slack", "U0123")
        # SLACK_ALLOWED_USER_ID happens to also be U0123 - single-user
        # branch wins and returns profile=None (no switch), not "alex"
        authorized, profile, username = slack_bot.resolve_profile("U0123", "U0123")
        assert authorized is True
        assert profile is None
        assert username is None


class TestExtractImageFiles:
    def test_no_files_key(self, slack_bot):
        assert slack_bot.extract_image_files({}) == []

    def test_filters_to_images_only(self, slack_bot):
        event = {"files": [
            {"mimetype": "image/png", "url_private": "http://x/1"},
            {"mimetype": "application/pdf", "url_private": "http://x/2"},
            {"mimetype": "image/jpeg", "url_private": "http://x/3"},
        ]}
        result = slack_bot.extract_image_files(event)
        assert len(result) == 2
        assert all(f["mimetype"].startswith("image/") for f in result)

    def test_missing_mimetype_excluded(self, slack_bot):
        event = {"files": [{"url_private": "http://x/1"}]}
        assert slack_bot.extract_image_files(event) == []


class TestBytesToImageDataUri:
    def test_encodes_correctly(self, slack_bot):
        raw = b"fake-image-bytes"
        uri = slack_bot.bytes_to_image_data_uri(raw, "image/png")
        assert uri.startswith("data:image/png;base64,")
        encoded = uri.split(",", 1)[1]
        assert base64.b64decode(encoded) == raw

    def test_defaults_to_jpeg_when_mimetype_missing(self, slack_bot):
        uri = slack_bot.bytes_to_image_data_uri(b"x", None)
        assert uri.startswith("data:image/jpeg;base64,")


class TestHandleMessage:
    def _fake_client_and_model(self):
        return object(), "fake-model"

    def test_ignores_bot_messages(self, slack_bot):
        event = {"bot_id": "B123", "user": "U0123", "text": "hi"}
        client, model = self._fake_client_and_model()
        result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        assert result is None

    def test_ignores_bot_message_subtype(self, slack_bot):
        event = {"subtype": "bot_message", "user": "U0123", "text": "hi"}
        client, model = self._fake_client_and_model()
        result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        assert result is None

    def test_ignores_event_with_no_user(self, slack_bot):
        event = {"text": "hi"}
        client, model = self._fake_client_and_model()
        result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        assert result is None

    def test_ignores_unauthorized_sender(self, slack_bot):
        event = {"user": "U9999", "text": "hi"}
        client, model = self._fake_client_and_model()
        result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        assert result is None

    def test_ignores_empty_message(self, slack_bot):
        event = {"user": "U0123", "text": "   "}
        client, model = self._fake_client_and_model()
        result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        assert result is None

    def test_authorized_text_message_generates_reply(self, slack_bot):
        event = {"user": "U0123", "text": "how did I sleep?"}
        client, model = self._fake_client_and_model()
        with patch.object(slack_bot, "generate_reply", return_value="You slept great!") as mock_gen:
            result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        assert result == "You slept great!"
        mock_gen.assert_called_once()

    def test_exception_in_generate_reply_is_caught(self, slack_bot):
        event = {"user": "U0123", "text": "hello"}
        client, model = self._fake_client_and_model()
        with patch.object(slack_bot, "generate_reply", side_effect=RuntimeError("boom")):
            result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        assert "Something went wrong" in result
        assert "boom" in result

    def test_multi_user_switches_active_profile(self, slack_bot):
        slack_bot.users_mod.add_user("alex", profile="alex-profile")
        slack_bot.users_mod.link_channel("alex", "slack", "U0555")
        event = {"user": "U0555", "text": "log my mood as great"}
        client, model = self._fake_client_and_model()
        with patch.object(slack_bot, "generate_reply", return_value="Logged!"):
            slack_bot.handle_message(event, client, model, "xoxb-token", None)
        assert slack_bot.storage.ACTIVE_PROFILE == "alex-profile"

    def test_image_download_success_prefixes_camera_emoji(self, slack_bot):
        event = {
            "user": "U0123",
            "text": "",
            "files": [{"mimetype": "image/png", "url_private": "http://slack.example/file.png"}],
        }
        client, model = self._fake_client_and_model()
        with patch.object(slack_bot, "download_slack_file", return_value=b"imgbytes") as mock_dl, \
             patch.object(slack_bot, "generate_reply", return_value="Logged your meal.") as mock_gen:
            result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        mock_dl.assert_called_once_with("xoxb-token", "http://slack.example/file.png")
        assert result.startswith("\U0001F4F7")
        assert "Logged your meal." in result
        # image_data_uri should have been passed through to generate_reply
        _args, kwargs = mock_gen.call_args
        assert kwargs["image_data_uri"].startswith("data:image/png;base64,")

    def test_image_download_failure_returns_error_message(self, slack_bot):
        event = {
            "user": "U0123",
            "text": "",
            "files": [{"mimetype": "image/jpeg", "url_private": "http://slack.example/file.jpg"}],
        }
        client, model = self._fake_client_and_model()
        with patch.object(slack_bot, "download_slack_file",
                          side_effect=slack_bot.SlackBotError("network error")):
            result = slack_bot.handle_message(event, client, model, "xoxb-token", "U0123")
        assert "Couldn't process that image" in result
        assert "network error" in result


class TestBuildAppRequiresSlackBolt:
    def test_raises_clear_error_when_slack_bolt_not_installed(self, slack_bot, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "slack_bolt":
                raise ImportError("No module named 'slack_bolt'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(slack_bot.SlackBotError, match="slack_bolt"):
            slack_bot.build_app("xoxb-fake", object(), "fake-model", "U0123")


class TestBuildAppWithSlackBolt:
    """These exercise the real slack_bolt App wiring (event registration
    only - no real websocket connection is ever opened)."""

    def test_build_app_returns_app_instance(self, slack_bot):
        pytest.importorskip("slack_bolt")
        app = slack_bot.build_app("xoxb-fake-token-for-testing", object(), "fake-model", "U0123",
                                   verify_token=False)
        assert app is not None


class TestMainCli:
    def test_missing_tokens_exits_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
        for mod in ("storage", "users", "slack_bot"):
            if mod in sys.modules:
                del sys.modules[mod]
        import slack_bot as sb
        importlib.reload(sb)
        monkeypatch.setattr(sys, "argv", ["slack_bot.py"])
        with pytest.raises(SystemExit) as exc_info:
            sb.main()
        assert exc_info.value.code == 1

    def test_missing_allowed_user_and_no_links_exits_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-fake")
        monkeypatch.delenv("SLACK_ALLOWED_USER_ID", raising=False)
        for mod in ("storage", "users", "slack_bot"):
            if mod in sys.modules:
                del sys.modules[mod]
        import slack_bot as sb
        importlib.reload(sb)
        monkeypatch.setattr(sys, "argv", ["slack_bot.py"])
        with pytest.raises(SystemExit) as exc_info:
            sb.main()
        assert exc_info.value.code == 1
