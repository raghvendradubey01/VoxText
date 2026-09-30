"""Request guards: session extraction, current user lookup, origin checks."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from .errors import AuthError, OriginError
from .tokens import SessionToken, decode_session_token

_BEARER_PATTERN = re.compile(r"^bearer\s+(?P<token>.+)$", re.IGNORECASE)
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def extract_session_token(request: Request) -> str | None:
    """Read the session from the HttpOnly cookie, then from a bearer header."""
    settings = get_settings()
    cookie_value = request.cookies.get(settings.session_cookie_name)
    if cookie_value:
        return cookie_value.strip() or None

    header = request.headers.get("authorization")
    if header:
        match = _BEARER_PATTERN.match(header.strip())
        if match:
            return match.group("token").strip() or None
    return None


def resolve_session_token(request: Request) -> SessionToken | None:
    """Return valid session claims, or ``None`` when no usable session exists."""
    raw = extract_session_token(request)
    if not raw:
        return None
    try:
        return decode_session_token(raw)
    except AuthError:
        return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Dependency that requires a valid session and returns the matching user."""
    raw = extract_session_token(request)
    if not raw:
        raise AuthError("You must be signed in to use this feature.")

    claims = decode_session_token(raw)
    user = db.get(User, claims.user_id)
    if user is None:
        raise AuthError("Your session refers to an account that no longer exists.")
    if not user.is_active:
        raise AuthError("This account is no longer active.")
    return user


def has_valid_session(request: Request) -> bool:
    """Cheap cookie-only check used to redirect dashboard visitors."""
    return resolve_session_token(request) is not None


def require_same_origin(request: Request) -> None:
    """Defence-in-depth against CSRF for cookie-authenticated writes.

    ``SameSite=Lax`` already blocks cross-site POSTs; this additionally rejects
    requests that *do* carry a mismatched ``Origin``/``Referer``.  Requests with
    no ``Origin`` (curl, native clients, same-origin GETs) are allowed.
    """
    if request.method not in _UNSAFE_METHODS:
        return

    origin_header = request.headers.get("origin") or request.headers.get("referer")
    if not origin_header:
        return

    source = urlsplit(origin_header)
    source_netloc = (source.netloc or source.path).lower()
    if not source_netloc:
        return
    if source_netloc != request.url.netloc.lower():
        raise OriginError()
