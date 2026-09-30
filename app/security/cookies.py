"""Helpers for the HttpOnly session cookie."""

from __future__ import annotations

from fastapi import Request, Response

from ..config import get_settings


def _is_secure(request: Request) -> bool:
    settings = get_settings()
    return bool(settings.cookie_secure) or request.url.scheme.lower() == "https"


def set_session_cookie(
    response: Response, request: Request, token: str, max_age_seconds: int
) -> None:
    """Attach the signed session token as an HttpOnly cookie.

    ``HttpOnly`` keeps the value out of ``document.cookie``/JS reach, and
    ``SameSite=Lax`` stops it riding on cross-site state-changing requests.
    """
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age_seconds,
        path="/",
        secure=_is_secure(request),
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=_is_secure(request),
        httponly=True,
        samesite=settings.cookie_samesite,
    )
