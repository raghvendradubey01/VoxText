"""Faster-Whisper speech recognition service.

The model is heavy (hundreds of MB) so it is loaded lazily and guarded by a
lock: concurrent requests must not each trigger their own download.
Transcription is CPU/IO bound, so routers call it through a threadpool.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from .errors import SpeechEngineError

logger = logging.getLogger(__name__)

TASKS = ("transcribe", "translate")


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None
    language_probability: float
    duration: float
    task: str


_model: Any = None
_model_lock = threading.Lock()
_load_error: str | None = None


def _build_model() -> Any:
    """Import and instantiate the model (import is deferred to keep startup fast)."""
    from faster_whisper import WhisperModel  # heavy: only when actually needed

    settings = get_settings()
    logger.info(
        "Loading Faster-Whisper model '%s' (device=%s, compute_type=%s)",
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
    )
    return WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def get_model() -> Any:
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                _model = _build_model()
            except Exception as exc:  # pragma: no cover - depends on native libs
                logger.exception("Could not load the speech recognition model")
                raise SpeechEngineError(
                    "The speech recognition model is unavailable on this server. "
                    "Please contact the administrator."
                ) from exc
        return _model


def warm_model() -> bool:
    """Pre-load the model in a background thread so the first request is fast."""
    global _load_error
    try:
        get_model()
        _load_error = None
        logger.info("Speech model ready (%s)", get_settings().whisper_model)
        return True
    except SpeechEngineError as exc:
        _load_error = exc.detail
        return False


def model_is_ready() -> bool:
    return _model is not None


def model_load_error() -> str | None:
    return _load_error


def transcribe(audio_path: Path, task: str = "transcribe") -> TranscriptionResult:
    """Transcribe a stored audio file. Blocking - run this in a threadpool."""
    if task not in TASKS:
        raise ValueError(f"task must be one of {TASKS}")

    model = get_model()
    settings = get_settings()
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=settings.whisper_beam_size,
        task=task,
    )

    # Segments are a lazy generator: consuming them here is what does the work.
    text = " ".join(segment.text for segment in segments).strip()
    return TranscriptionResult(
        text=text,
        language=getattr(info, "language", None),
        language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
        duration=float(getattr(info, "duration", 0.0) or 0.0),
        task=task,
    )
