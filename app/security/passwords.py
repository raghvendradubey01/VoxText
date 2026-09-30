"""Password hashing with bcrypt.

``passlib`` is deliberately **not** used: it is unmaintained and its bcrypt
backend detection breaks against bcrypt >= 4.1.  Calling ``bcrypt`` directly is
smaller, faster and has no transitive dependencies.
"""

from __future__ import annotations

import secrets
from functools import lru_cache

import bcrypt

from ..config import get_settings


def _encode(password: str) -> bytes:
    return password.encode("utf-8")


def hash_password(password: str) -> str:
    """Return a salted bcrypt digest for ``password``."""
    salt = bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)
    return bcrypt.hashpw(_encode(password), salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time comparison of a candidate password against a digest."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_encode(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # Malformed / truncated digest stored or passed in: treat as invalid.
        return False


@lru_cache
def _dummy_hash() -> str:
    """Digest used to equalise response time for unknown email addresses."""
    return hash_password(secrets.token_urlsafe(32))


def verify_dummy_password(password: str) -> bool:
    """Burn the same CPU as a real check so accounts cannot be enumerated by timing."""
    return verify_password(password, _dummy_hash())


def is_bcrypt_digest(value: str) -> bool:
    return value.startswith(("$2b$", "$2a$", "$2y$"))
