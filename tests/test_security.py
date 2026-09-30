"""Unit tests for password hashing and session tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.security.errors import AuthError
from app.security.passwords import hash_password, verify_password
from app.security.tokens import create_session_token, decode_session_token

FORGERY_KEY = "a-completely-different-signing-key-0123456789abcdef"


def _claim_set(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "42",
        "type": "session",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return claims


def test_hash_is_verifiable_and_salted() -> None:
    digest = hash_password("correct-horse-battery")
    other = hash_password("correct-horse-battery")

    assert digest.startswith("$2b$")
    assert digest != other, "bcrypt must use a fresh salt each time"
    assert verify_password("correct-horse-battery", digest)
    assert not verify_password("correct-horse-batterY", digest)


def test_malformed_digest_is_rejected() -> None:
    assert not verify_password("anything", "not-a-bcrypt-digest")
    assert not verify_password("anything", "")


def test_token_round_trip() -> None:
    issued = create_session_token(42)
    claims = decode_session_token(issued.token)

    assert claims.user_id == 42
    assert claims.token_id == issued.token_id
    assert claims.expires_at > datetime.now(timezone.utc)


def test_missing_token_is_rejected() -> None:
    with pytest.raises(AuthError):
        decode_session_token("")


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(AuthError):
        decode_session_token("not.a.jwt")


def test_token_signed_with_another_key_is_rejected() -> None:
    settings = get_settings()
    forged = jwt.encode(
        _claim_set(), FORGERY_KEY, algorithm=settings.jwt_algorithm
    )
    with pytest.raises(AuthError):
        decode_session_token(forged)


def test_expired_token_is_rejected() -> None:
    settings = get_settings()
    expired = jwt.encode(
        _claim_set(exp=datetime.now(timezone.utc) - timedelta(minutes=1)),
        settings.resolved_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AuthError, match="expired"):
        decode_session_token(expired)


def test_token_of_wrong_type_is_rejected() -> None:
    """A token signed by *this* app but for another purpose is still invalid."""
    settings = get_settings()
    wrong_type = jwt.encode(
        _claim_set(type="password-reset"),
        settings.resolved_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AuthError):
        decode_session_token(wrong_type)


def test_algorithm_confusion_is_rejected() -> None:
    """Only the configured algorithm is accepted."""
    settings = get_settings()
    hs384 = jwt.encode(
        _claim_set(), settings.resolved_secret_key, algorithm="HS384"
    )
    with pytest.raises(AuthError):
        decode_session_token(hs384)
