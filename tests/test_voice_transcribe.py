"""Tests for demo/voice_transcribe.py. The 'package not installed'
error path is forced deterministically via sys.modules (setting
'faster_whisper' to None makes Python raise ImportError for it) rather
than relying on the package actually being absent from the test
environment - CI installs the [all] extra, which includes
faster-whisper, so relying on ambient absence is not reliable there.
The actual transcription/segment-joining logic is tested against a
mocked model object, independent of whether the real package or a
network connection is available."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def voice_transcribe():
    if "voice_transcribe" in sys.modules:
        del sys.modules["voice_transcribe"]
    import voice_transcribe as vt
    importlib.reload(vt)
    vt._model_cache.clear()
    return vt


class TestGetModelNotInstalled:
    def test_raises_clear_error_when_package_missing(self, voice_transcribe, monkeypatch):
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
        with pytest.raises(voice_transcribe.TranscriptionError, match="faster-whisper"):
            voice_transcribe._get_model("base")

    def test_transcribe_audio_raises_same_error(self, voice_transcribe, monkeypatch):
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
        with pytest.raises(voice_transcribe.TranscriptionError, match="faster-whisper"):
            voice_transcribe.transcribe_audio("/tmp/fake.ogg")


class TestModelSizeResolution:
    def test_uses_env_var_when_no_explicit_size(self, voice_transcribe, monkeypatch):
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
        monkeypatch.setenv("WHISPER_MODEL", "small")
        with pytest.raises(voice_transcribe.TranscriptionError):
            voice_transcribe._get_model(None)

    def test_defaults_to_base_without_env_var(self, voice_transcribe, monkeypatch):
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
        monkeypatch.delenv("WHISPER_MODEL", raising=False)
        with pytest.raises(voice_transcribe.TranscriptionError):
            voice_transcribe._get_model(None)


class TestTranscribeAudioWithMockedModel:
    def test_joins_segments_into_single_text(self, voice_transcribe):
        fake_model = SimpleNamespace(
            transcribe=lambda path: (
                [SimpleNamespace(text=" Hello "), SimpleNamespace(text=" world ")],
                SimpleNamespace(language="en"),
            )
        )
        voice_transcribe._model_cache["base"] = fake_model
        result = voice_transcribe.transcribe_audio("/tmp/fake.ogg", model_size="base")
        assert result == "Hello world"

    def test_empty_segments_returns_empty_string(self, voice_transcribe):
        fake_model = SimpleNamespace(transcribe=lambda path: ([], SimpleNamespace(language="en")))
        voice_transcribe._model_cache["base"] = fake_model
        result = voice_transcribe.transcribe_audio("/tmp/fake.ogg", model_size="base")
        assert result == ""

    def test_model_reused_from_cache_not_reloaded(self, voice_transcribe):
        call_count = {"n": 0}

        class FakeModel:
            def transcribe(self, path):
                call_count["n"] += 1
                return [SimpleNamespace(text="hi")], SimpleNamespace(language="en")

        voice_transcribe._model_cache["base"] = FakeModel()
        voice_transcribe.transcribe_audio("/tmp/a.ogg", model_size="base")
        voice_transcribe.transcribe_audio("/tmp/b.ogg", model_size="base")
        assert call_count["n"] == 2  # transcribe called twice, but same cached model instance
        assert len(voice_transcribe._model_cache) == 1  # only one model ever cached

    def test_transcription_exception_wrapped_as_transcription_error(self, voice_transcribe):
        def broken_transcribe(path):
            raise RuntimeError("corrupt audio")

        fake_model = SimpleNamespace(transcribe=broken_transcribe)
        voice_transcribe._model_cache["base"] = fake_model
        with pytest.raises(voice_transcribe.TranscriptionError, match="corrupt audio"):
            voice_transcribe.transcribe_audio("/tmp/fake.ogg", model_size="base")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
