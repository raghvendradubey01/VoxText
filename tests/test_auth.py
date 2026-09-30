"""End-to-end tests for the authentication flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from main import app as fastapi_app

SIGNUP = {"email": "Alice@Example.com ", "password": "correct-horse-battery", "full_name": "  Alice  "}
INVALID_CREDENTIALS = "The email or password is incorrect."


def _cookie_header(response) -> str:
    return " ".join(response.headers.get_list("set-cookie")).lower()


def test_signup_creates_account_and_session(client) -> None:
    response = client.post("/api/auth/signup", json=SIGNUP)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "alice@example.com", "e-mail must be normalised"
    assert body["full_name"] == "Alice"
    assert body["id"] > 0
    assert "password" not in body and "password_hash" not in body

    cookie = _cookie_header(response)
    assert "voxtext_session" in cookie
    assert "httponly" in cookie, "session cookie must be unreadable by JavaScript"
    assert "samesite=lax" in cookie


def test_only_a_bcrypt_hash_reaches_the_database(client) -> None:
    client.post("/api/auth/signup", json=SIGNUP)

    with SessionLocal() as session:
        user = session.query(User).filter_by(email="alice@example.com").one()
        assert user.password_hash.startswith("$2b$")
        assert SIGNUP["password"] not in user.password_hash


def test_signup_rejects_duplicate_email(client) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    second = client.post(
        "/api/auth/signup",
        json={"email": "alice@example.com", "password": "another-password"},
    )

    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


def test_signup_race_falls_back_to_conflict(client, monkeypatch) -> None:
    """If a concurrent request wins the race, the unique index still protects us."""
    client.post("/api/auth/signup", json=SIGNUP)

    # Pretend the pre-check found no account, so the INSERT is really attempted.
    monkeypatch.setattr("sqlalchemy.orm.Session.scalar", lambda self, *a, **k: None)
    response = client.post(
        "/api/auth/signup",
        json={"email": "alice@example.com", "password": "another-password"},
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    with SessionLocal() as session:
        assert session.query(User).count() == 1


def test_signup_validates_input(client) -> None:
    cases = [
        ({"email": "not-an-email", "password": "long-enough-pw"}, "email"),
        ({"email": "user@example.com", "password": "short"}, "password"),
        ({"email": "user@example.com", "password": " " * 12}, "password"),
        (
            {"email": "user@example.com", "password": "p" * 80},
            "bytes",
        ),  # > 72 bytes: bcrypt would silently truncate
    ]
    for payload, expected_fragment in cases:
        response = client.post("/api/auth/signup", json=payload)
        assert response.status_code == 422, payload
        assert expected_fragment in response.text.lower(), response.text


def test_login_returns_the_profile_and_a_session_cookie(client) -> None:
    client.post("/api/auth/signup", json=SIGNUP)

    response = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": SIGNUP["password"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "alice@example.com"
    assert "httponly" in _cookie_header(response)

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["full_name"] == "Alice"
    assert me.json()["last_login_at"] is not None


def test_login_rejects_wrong_password(client) -> None:
    client.post("/api/auth/signup", json=SIGNUP)

    response = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password-here"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_CREDENTIALS


def test_unknown_email_and_wrong_password_are_indistinguishable(client) -> None:
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "whatever-1234"},
    )
    client.post("/api/auth/signup", json=SIGNUP)
    wrong = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "whatever-1234"},
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_repeated_failures_are_rate_limited(client) -> None:
    client.post("/api/auth/signup", json=SIGNUP)

    last = None
    for _ in range(3):  # LOGIN_MAX_ATTEMPTS=3 in the test environment
        last = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": "nope-nope-nope"},
        )
        assert last.status_code == 401

    blocked = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": SIGNUP["password"]},
    )

    assert blocked.status_code == 429
    assert "too many failed sign-in attempts" in blocked.json()["detail"].lower()
    assert int(blocked.headers["retry-after"]) >= 1


def test_successful_login_clears_the_failure_counter(client) -> None:
    from app.security.rate_limit import login_limiter

    client.post("/api/auth/signup", json=SIGNUP)
    client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "nope-nope-nope"},
    )
    assert login_limiter.remaining(
        f"login:testclient:alice@example.com"
    ) < login_limiter.max_attempts

    ok = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": SIGNUP["password"]},
    )
    assert ok.status_code == 200
    assert login_limiter.remaining("login:testclient:alice@example.com") == 3


def test_me_requires_a_session(client) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert "www-authenticate" in {k.lower() for k in response.headers.keys()}


def test_me_accepts_a_bearer_token(client) -> None:
    login = client.post(
        "/api/auth/signup",
        json={"email": "bearer@example.com", "password": "correct-horse-battery"},
    )
    token = login.cookies.get(get_settings().session_cookie_name)
    client.cookies.clear()

    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "bearer@example.com"


def test_me_rejects_a_forged_token(client) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    settings = get_settings()
    forged = jwt.encode(
        {
            "sub": "1",
            "type": "session",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "an-attacker-key-that-is-long-enough-to-look-real-0123456789",
        algorithm=settings.jwt_algorithm,
    )
    client.cookies.set(settings.session_cookie_name, forged)

    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_an_expired_token(client) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": "1",
            "type": "session",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.resolved_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    client.cookies.set(settings.session_cookie_name, expired)

    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_me_rejects_a_deactivated_account(auth_client) -> None:
    with SessionLocal() as session:
        session.query(User).update({"is_active": False})
        session.commit()

    response = auth_client.get("/api/auth/me")
    assert response.status_code == 401
    assert "active" in response.json()["detail"].lower()


def test_logout_ends_the_session(auth_client) -> None:
    assert auth_client.get("/api/auth/me").status_code == 200

    response = auth_client.post("/api/auth/logout")

    assert response.status_code == 204
    assert "voxtext_session=" in " ".join(response.headers.get_list("set-cookie"))
    assert auth_client.get("/api/auth/me").status_code == 401


def test_logout_revokes_the_token_so_a_captured_cookie_cannot_be_replayed(
    auth_client,
) -> None:
    """Dropping the cookie is not enough - the JWT itself must stop working.

    The check above only proves the *browser* forgets the token.  An attacker who
    copied it first must not keep a valid session until ``exp``.
    """
    settings = get_settings()
    captured = auth_client.cookies.get(settings.session_cookie_name)
    assert captured, "sign-up must issue a session cookie"

    assert auth_client.post("/api/auth/logout").status_code == 204

    # A separate client replays the captured token, bypassing any cookie jar.
    with TestClient(fastapi_app) as attacker:
        attacker.cookies.set(settings.session_cookie_name, captured)
        stolen = attacker.get("/api/auth/me")

    assert stolen.status_code == 401, "a logged-out token must be rejected"
    assert "ended" in stolen.json()["detail"].lower()


def test_state_changing_requests_from_other_origins_are_blocked(client) -> None:
    response = client.post(
        "/api/auth/signup",
        json=SIGNUP,
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403


def test_anonymous_dashboard_redirects_to_login(client) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code in (302, 303, 307)
    assert response.headers["location"] == "/login"


def test_dashboard_is_served_when_signed_in(auth_client) -> None:
    response = auth_client.get("/")

    assert response.status_code == 200
    assert "Transcription Result" in response.text


def test_sign_in_page_redirects_an_active_session(auth_client) -> None:
    response = auth_client.get("/login", follow_redirects=False)

    assert response.status_code in (302, 303, 307)
    assert response.headers["location"] == "/"


def test_sign_in_page_is_reachable(client) -> None:
    assert client.get("/login").status_code == 200


def test_health_is_public_and_reports_model_state(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["speech_model"] == get_settings().whisper_model


def test_static_assets_are_served(client) -> None:
    assert client.get("/static/style.css").status_code == 200


def test_security_headers_are_present(client) -> None:
    response = client.get("/api/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "microphone=(self)" in response.headers["permissions-policy"]

