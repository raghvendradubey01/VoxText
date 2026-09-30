"""Signed session tokens (JWT, HS256) using PyJWT.

Tokens are delivered in an ``HttpOnly`` cookie so that no credential is ever
readable from browser JavaScript.  ``Authorization: Bearer <token>`` is also
accepted for non-browser API clients.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from ..config import get_settings
from .errors import AuthError
from .revocation import session_revoker

SESSION_TOKEN_TYPE = "session"
_INVALID_SESSION = "Your session is invalid. Please sign in again."
_REVOKED_SESSION = "Your session has ended. Please sign in again."


@dataclass(frozen=True)
class SessionToken:
    """Claims of a validated session, plus the encoded JWT when issuing one."""

    user_id: int
    expires_at: datetime
    token_id: str
    token: str = ""


def _signing_key() -> str:
    return get_settings().resolved_secret_key


def create_session_token(user_id: int, expires_in_seconds: int | None = None) -> SessionToken:
    """Issue a new signed session token for ``user_id``."""
    settings = get_settings()
    lifetime = (
        settings.session_max_age_seconds
        if expires_in_seconds is None
        else expires_in_seconds
    )
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=lifetime)
    token_id = uuid.uuid4().hex

    payload = {
        # RFC 7519 requires a string subject claim.
        "sub": str(user_id),
        "type": SESSION_TOKEN_TYPE,
        "iat": issued_at,
        "exp": expires_at,
        "jti": token_id,
    }
    encoded = jwt.encode(payload, _signing_key(), algorithm=settings.jwt_algorithm)
    return SessionToken(
        user_id=user_id,
        expires_at=expires_at,
        token_id=token_id,
        token=encoded,
    )


def decode_session_token(token: str) -> SessionToken:
    """Validate a session token and return its claims.

    Raises :class:`AuthError` for missing, malformed, expired, tampered or
    deliberately revoked (signed-out) tokens.
    """
    settings = get_settings()
    if not token:
        raise AuthError()

    try:
        payload = jwt.decode(
            token,
            _signing_key(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Your session has expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(_INVALID_SESSION) from exc

    if payload.get("type") != SESSION_TOKEN_TYPE:
        raise AuthError(_INVALID_SESSION)

    token_id = str(payload.get("jti", ""))
    if session_revoker.is_revoked(token_id):
        # The signature is still valid; the user asked for this session to end.
        raise AuthError(_REVOKED_SESSION)

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError(_INVALID_SESSION) from exc

    expires_at = datetime.now(timezone.utc)
    if isinstance(payload.get("exp"), (int, float)):
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    return SessionToken(
        user_id=user_id,
        expires_at=expires_at,
        token_id=token_id,
        token=token,
    )
