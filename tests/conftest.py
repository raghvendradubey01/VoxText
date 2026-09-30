"""Shared pytest configuration.

Environment variables are set **before** the application is imported, because
settings are read once and cached: this points the tests at a throw-away SQLite
file (never the developer's database), cheap bcrypt rounds, a small upload cap
and disables the Whisper warm-up so the suite stays fast and offline.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "SECRET_KEY",
    "unit-test-secret-key-not-for-anything-real-0123456789abcdef",
)
os.environ["DEBUG"] = "false"
os.environ["WHISPER_WARM_ON_STARTUP"] = "false"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["MAX_UPLOAD_MB"] = "1"
os.environ["LOGIN_MAX_ATTEMPTS"] = "3"
os.environ["LOGIN_WINDOW_SECONDS"] = "60"

_TEST_DIR = Path(tempfile.mkdtemp(prefix="voxtext-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_DIR / 'test.db').as_posix()}"

import pytest  # noqa: E402  (must follow the environment setup above)
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.security.rate_limit import login_limiter  # noqa: E402
from app.security.revocation import session_revoker  # noqa: E402
from main import app as fastapi_app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state():
    """Start every test with an empty users table and no carried-over state."""
    init_db()
    login_limiter.reset_all()
    session_revoker.reset_all()
    yield
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    login_limiter.reset_all()
    session_revoker.reset_all()


@pytest.fixture
def client() -> TestClient:
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    """A client with an active session for a freshly created account."""
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-battery",
            "full_name": "Alice",
        },
    )
    assert response.status_code == 201, response.text
    return client
