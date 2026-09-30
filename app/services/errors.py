"""Domain errors raised by service helpers, mapped to HTTP responses centrally."""

from __future__ import annotations


class UploadError(Exception):
    """Invalid or unsafe uploaded file."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class SpeechEngineError(Exception):
    """The speech recognition engine could not be used."""

    def __init__(self, detail: str, status_code: int = 503) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
