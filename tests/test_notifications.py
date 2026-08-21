"""Tests for the pluggable notification channels (demo/notifications.py)."""
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

from notifications import send_notification, NotificationResult, NotificationError, send_html_email


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure no leftover env vars from the host machine leak into tests."""
    for key in [
        "HERMES_NOTIFY_CHANNEL", "HERMES_WEBHOOK_URL",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        "HERMES_SMTP_HOST", "HERMES_SMTP_PORT", "HERMES_SMTP_USER",
        "HERMES_SMTP_PASSWORD", "HERMES_SMTP_TO",
    ]:
        monkeypatch.delenv(key, raising=False)


class TestConsoleChannel:
    def test_default_channel_is_console(self, capsys):
        result = send_notification("Title", "Body")
        assert result.ok is True
        assert result.channel == "console"

    def test_console_prints_title_and_message(self, capsys):
        send_notification("My Title", "My Body", channel="console")
        captured = capsys.readouterr()
        assert "My Title" in captured.out
        assert "My Body" in captured.out

    def test_env_var_selects_channel(self, monkeypatch, capsys):
        monkeypatch.setenv("HERMES_NOTIFY_CHANNEL", "console")
        result = send_notification("T", "M")
        assert result.channel == "console"


class TestWebhookChannel:
    def test_fails_gracefully_without_url(self):
        result = send_notification("T", "M", channel="webhook")
        assert result.ok is False
        assert "HERMES_WEBHOOK_URL" in result.detail

    def test_never_raises(self):
        # Should not raise even though config is missing
        try:
            send_notification("T", "M", channel="webhook")
        except Exception as e:
            pytest.fail(f"send_notification raised unexpectedly: {e}")


class TestTelegramChannel:
    def test_fails_gracefully_without_credentials(self):
        result = send_notification("T", "M", channel="telegram")
        assert result.ok is False
        assert "TELEGRAM_BOT_TOKEN" in result.detail

    def test_fails_gracefully_with_partial_credentials(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        # chat id still missing
        result = send_notification("T", "M", channel="telegram")
        assert result.ok is False


class TestEmailChannel:
    def test_fails_gracefully_without_credentials(self):
        result = send_notification("T", "M", channel="email")
        assert result.ok is False
        assert "HERMES_SMTP_HOST" in result.detail

    def test_fails_gracefully_with_partial_credentials(self, monkeypatch):
        monkeypatch.setenv("HERMES_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("HERMES_SMTP_USER", "user@example.com")
        # password still missing
        result = send_notification("T", "M", channel="email")
        assert result.ok is False


class TestSendHtmlEmail:
    def test_raises_without_credentials(self):
        with pytest.raises(NotificationError, match="HERMES_SMTP_HOST"):
            send_html_email("Subject", "<p>body</p>")

    def test_raises_with_partial_credentials(self, monkeypatch):
        monkeypatch.setenv("HERMES_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("HERMES_SMTP_USER", "user@example.com")
        with pytest.raises(NotificationError):
            send_html_email("Subject", "<p>body</p>")

    def test_successful_send_with_mocked_smtp(self, monkeypatch):
        monkeypatch.setenv("HERMES_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("HERMES_SMTP_USER", "user@example.com")
        monkeypatch.setenv("HERMES_SMTP_PASSWORD", "secret")
        monkeypatch.setenv("HERMES_SMTP_TO", "recipient@example.com")

        sent = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=10):
                sent["host"] = host
                sent["port"] = port

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def starttls(self):
                sent["starttls"] = True

            def login(self, user, password):
                sent["login"] = (user, password)

            def sendmail(self, from_addr, to_addrs, msg_str):
                sent["from"] = from_addr
                sent["to"] = to_addrs
                sent["msg"] = msg_str

        import notifications
        monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)

        result = send_html_email("Weekly Summary", "<h1>Report</h1>", "Plain fallback")
        assert result.ok is True
        assert result.channel == "email"
        assert sent["to"] == ["recipient@example.com"]
        assert sent["login"] == ("user@example.com", "secret")
        assert "Weekly Summary" in sent["msg"]
        assert "multipart/alternative" in sent["msg"]
        assert "Content-Type: text/html" in sent["msg"]
        assert "Content-Type: text/plain" in sent["msg"]
        # bodies are base64-encoded by MIMEText for utf-8 - verify via decode
        import base64
        assert base64.b64encode("<h1>Report</h1>".encode()).decode() in sent["msg"]
        assert base64.b64encode("Plain fallback".encode()).decode() in sent["msg"]

    def test_smtp_failure_raises_notification_error(self, monkeypatch):
        monkeypatch.setenv("HERMES_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("HERMES_SMTP_USER", "user@example.com")
        monkeypatch.setenv("HERMES_SMTP_PASSWORD", "secret")

        class FailingSMTP:
            def __init__(self, host, port, timeout=10):
                pass

            def __enter__(self):
                raise OSError("connection refused")

            def __exit__(self, *a):
                return False

        import notifications
        monkeypatch.setattr(notifications.smtplib, "SMTP", FailingSMTP)

        with pytest.raises(NotificationError, match="email send failed"):
            send_html_email("Subject", "<p>body</p>")


class TestUnknownChannel:
    def test_unknown_channel_falls_back_gracefully(self):
        result = send_notification("T", "M", channel="carrier_pigeon")
        assert result.ok is False
        assert "unknown channel" in result.detail

    def test_unknown_channel_still_delivers_to_console(self, capsys):
        send_notification("Title", "Body", channel="carrier_pigeon")
        captured = capsys.readouterr()
        assert "Title" in captured.out
        assert "Body" in captured.out


class TestNotificationResult:
    def test_result_is_dataclass_with_expected_fields(self):
        result = NotificationResult(channel="console", ok=True, detail="")
        assert result.channel == "console"
        assert result.ok is True
        assert result.detail == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
