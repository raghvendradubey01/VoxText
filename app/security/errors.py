"""Shared security exceptions mapped to HTTP responses."""

from __future__ import annotations

from fastapi import HTTPException


class AuthError(HTTPException):
    """Raised when a request is unauthenticated or the session is unusable."""

    def __init__(self, detail: str = "Authentication required.", status_code: int = 401):
        super().__init__(
            status_code=status_code,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class RateLimitError(HTTPException):
    """Raised when too many failed attempts were made in a time window."""

    def __init__(self, detail: str, retry_after_seconds: int) -> None:
        super().__init__(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(max(1, int(retry_after_seconds)))},
        )


class OriginError(HTTPException):
    """Raised when a state-changing request comes from an unexpected origin."""

    def __init__(self, detail: str = "Cross-origin request blocked.") -> None:
        super().__init__(status_code=403, detail=detail)
