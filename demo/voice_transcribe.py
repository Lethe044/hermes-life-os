"""
Hermes Life OS - Voice Transcription
========================================
Transcribes audio (e.g. Telegram voice notes) to text using a local,
free Whisper model via faster-whisper - no cloud API, no per-minute
cost. Runs entirely on CPU (no GPU required, though one speeds things
up if available).

Install:
    pip install "hermes-life-os[voice]"   # or: pip install faster-whisper

Model size (WHISPER_MODEL env var, default "base"):
    tiny   - fastest, least accurate (~75 MB)
    base   - good balance for most voice notes (~150 MB)  <- default
    small  - more accurate, slower (~500 MB)
    medium / large - noticeably better but slow on CPU-only machines

The model is downloaded automatically on first use (from Hugging Face)
and cached locally - no manual download step. The first transcription
after starting the bot will be slower while the model loads; after
that it stays loaded in memory for the rest of the process.

A note on testing: this module's core logic (segment-joining, model
caching, error handling) is unit tested with a mocked model object -
faster-whisper itself isn't installed in the environment this was
built in, so real audio transcription hasn't been exercised end-to-end
here. Your first real voice note is the true end-to-end check.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

_model_cache: Dict[str, object] = {}


class TranscriptionError(RuntimeError):
    pass


def _get_model(model_size: Optional[str] = None):
    """Loads (or returns the already-loaded) Whisper model for
    `model_size`. Models are cached per size for the life of the
    process - loading is the slow part, so a long-running bot only
    pays that cost once per size actually used."""
    model_size = model_size or os.environ.get("WHISPER_MODEL", "base")
    if model_size in _model_cache:
        return _model_cache[model_size]

    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptionError(
            "Voice transcription needs the 'faster-whisper' package.\n"
            "  pip install faster-whisper\n"
            "  (or: pip install \"hermes-life-os[voice]\")"
        ) from e

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    except Exception as e:
        raise TranscriptionError(f"Failed to load Whisper model '{model_size}': {e}") from e

    _model_cache[model_size] = model
    return model


def transcribe_audio(file_path: str, model_size: Optional[str] = None) -> str:
    """
    Transcribes an audio file to text. Accepts any format ffmpeg can
    read (Telegram voice notes are .ogg/Opus; faster-whisper shells out
    to ffmpeg internally for decoding, so ffmpeg must be installed and
    on PATH - most systems have it, or `pip install ffmpeg-python` pulls
    a bundled build via imageio-ffmpeg as a fallback in some setups).

    Returns the transcribed text (empty string if no speech was
    detected - not an error). Raises TranscriptionError if the package
    isn't installed, the model fails to load, or transcription itself
    fails (e.g. corrupt/unreadable audio file).
    """
    model = _get_model(model_size)
    try:
        segments, _info = model.transcribe(file_path)
        return " ".join(segment.text.strip() for segment in segments).strip()
    except TranscriptionError:
        raise
    except Exception as e:
        raise TranscriptionError(f"Transcription failed: {e}") from e
