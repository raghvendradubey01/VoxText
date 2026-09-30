"""Access-control and validation tests for the speech endpoint.

The Whisper model is intentionally *not* loaded here: every assertion below is
reached before transcription would start, so the suite stays fast and offline.
The transcription call itself is faked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import speech
from app.services.uploads import _safe_basename

AUDIO = {"audio": ("clip.webm", b"fake-webm-bytes", "audio/webm")}


def test_transcribe_requires_authentication(client) -> None:
    response = client.post("/api/transcribe", files=AUDIO, data={"task": "transcribe"})

    assert response.status_code == 401
    assert "signed in" in response.json()["detail"].lower()


def test_transcribe_accepts_an_authenticated_request(auth_client, monkeypatch) -> None:
    seen: dict = {}

    def fake_transcribe(path: Path, task: str = "transcribe"):
        seen["path"] = Path(path)
        seen["task"] = task
        assert seen["path"].is_file(), "the upload must be stored before transcribing"
        return speech.TranscriptionResult(
            text="hello from whisper",
            language="en",
            language_probability=0.97,
            duration=2.5,
            task=task,
        )

    monkeypatch.setattr(speech, "transcribe", fake_transcribe)

    response = auth_client.post("/api/transcribe", files=AUDIO, data={"task": "transcribe"})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "text": "hello from whisper",
        "language": "en",
        "language_probability": 0.97,
        "duration": 2.5,
        "task": "transcribe",
    }
    assert seen["task"] == "transcribe"
    assert not seen["path"].exists(), "the temporary upload must be deleted"


def test_translate_task_is_accepted(auth_client, monkeypatch) -> None:
    monkeypatch.setattr(
        speech,
        "transcribe",
        lambda path, task="transcribe": speech.TranscriptionResult(
            text="translated", language="en", language_probability=1.0,
            duration=1.0, task=task,
        ),
    )

    response = auth_client.post("/api/transcribe", files=AUDIO, data={"task": "translate"})

    assert response.status_code == 200
    assert response.json()["task"] == "translate"


def test_unknown_task_is_rejected(auth_client) -> None:
    response = auth_client.post(
        "/api/transcribe", files=AUDIO, data={"task": "summarise"}
    )

    assert response.status_code == 400
    assert "task" in response.json()["detail"]


@pytest.mark.parametrize("name", ["notes.txt", "payload.exe", "page.html", "script.sh"])
def test_unsupported_extensions_are_rejected(auth_client, name: str) -> None:
    response = auth_client.post(
        "/api/transcribe",
        files={"audio": (name, b"whatever", "application/octet-stream")},
        data={"task": "transcribe"},
    )

    assert response.status_code == 415
    assert "unsupported audio format" in response.json()["detail"].lower()


def test_empty_upload_is_rejected(auth_client) -> None:
    response = auth_client.post(
        "/api/transcribe",
        files={"audio": ("clip.webm", b"", "audio/webm")},
        data={"task": "transcribe"},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_oversized_upload_is_rejected(auth_client) -> None:
    # MAX_UPLOAD_MB=1 in the test environment.
    oversized = b"x" * (1024 * 1024 + 2048)

    response = auth_client.post(
        "/api/transcribe",
        files={"audio": ("big.webm", oversized, "audio/webm")},
        data={"task": "transcribe"},
    )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_upload_is_deleted_when_transcription_fails(auth_client, monkeypatch) -> None:
    captured: list[Path] = []

    def explode(path: Path, task: str = "transcribe"):
        captured.append(Path(path))
        raise RuntimeError("model exploded")

    monkeypatch.setattr(speech, "transcribe", explode)

    response = auth_client.post("/api/transcribe", files=AUDIO, data={"task": "transcribe"})

    assert response.status_code == 500
    # The raw failure must not leak to the client.
    assert response.json()["detail"] == (
        "Transcription failed. Check that the recording contains valid audio."
    )
    assert captured and not captured[0].exists()


def test_client_supplied_paths_are_never_used_for_storage() -> None:
    assert _safe_basename("..\\..\\..\\Windows\\System32\\config.webm") == "config.webm"
    assert _safe_basename("/etc/passwd") == "passwd"
    assert _safe_basename(" C:/Users/me/Desktop/recording.WAV ") == "recording.WAV"


@pytest.mark.parametrize("name", ["", "   ", "..", "/"])
def test_meaningless_file_names_are_rejected(name: str) -> None:
    from app.services.errors import UploadError

    with pytest.raises(UploadError):
        _safe_basename(name)
