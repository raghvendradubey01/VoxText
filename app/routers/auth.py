"""Account endpoints: sign up, sign in, sign out, current session.

Sessions are stateless signed tokens carried in an HttpOnly cookie.  Because the
tokens are self-contained, signing out also records the token's id in an
in-memory revocation list so a captured cookie cannot be replayed.  Failed
sign-ins are rate limited per client address + email, and unknown accounts cost
the same CPU as known ones so response timing does not leak who has registered.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User, utcnow
from ..schemas import LoginRequest, SignupRequest, UserOut
from ..security.cookies import clear_session_cookie, set_session_cookie
from ..security.deps import extract_session_token, get_current_user, require_same_origin
from ..security.errors import AuthError
from ..security.passwords import (
    hash_password,
    verify_dummy_password,
    verify_password,
)
from ..security.rate_limit import client_identity, login_limiter
from ..security.revocation import session_revoker
from ..security.tokens import create_session_token, decode_session_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for both "no such account" and "wrong password".
INVALID_CREDENTIALS = "The email or password is incorrect."
DUPLICATE_EMAIL = "An account with this email already exists."


def _start_session(request: Request, response: Response, user: User) -> UserOut:
    session = create_session_token(user.id)
    set_session_cookie(
        response,
        request,
        session.token,
        get_settings().session_max_age_seconds,
    )
    return UserOut.model_validate(user)


@router.post(
    "/signup",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
    summary="Create an account and start a session",
)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserOut:
    email = User.normalize_email(payload.email)

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_EMAIL)

    user = User(
        email=email,
        full_name=payload.full_name,
        # Only the bcrypt digest is persisted - never the plaintext password.
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race against a concurrent sign-up for the same address.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_EMAIL
        ) from None
    db.refresh(user)

    logger.info("Created account id=%s", user.id)
    return _start_session(request, response, user)


@router.post(
    "/login",
    response_model=UserOut,
    dependencies=[Depends(require_same_origin)],
    summary="Sign in and start a session",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserOut:
    email = User.normalize_email(payload.email)
    limiter_key = client_identity(request, "login", email)
    login_limiter.check(
        limiter_key,
        "Too many failed sign-in attempts. Please try again in a few minutes.",
    )

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_dummy_password(payload.password)  # keep the timing flat
        login_limiter.record_failure(limiter_key)
        raise AuthError(INVALID_CREDENTIALS)

    if not verify_password(payload.password, user.password_hash):
        login_limiter.record_failure(limiter_key)
        raise AuthError(INVALID_CREDENTIALS)

    login_limiter.reset(limiter_key)

    if not user.is_active:
        logger.warning("Sign-in attempt for inactive account id=%s", user.id)
        raise AuthError("This account is no longer active.", status_code=403)

    user.last_login_at = utcnow()
    db.commit()

    logger.info("Signed in user id=%s", user.id)
    return _start_session(request, response, user)


@router.post(
    "/logout",
    dependencies=[Depends(require_same_origin)],
    summary="End the current session",
)
def logout(request: Request) -> Response:
    """End the current session: drop the cookie *and* revoke its token."""
    raw = extract_session_token(request)
    if raw:
        try:
            claims = decode_session_token(raw)
        except AuthError:
            # Already invalid (expired, forged, never issued) - nothing to revoke.
            claims = None
        if claims is not None:
            session_revoker.revoke(claims.token_id, claims.expires_at)
            logger.info("Revoked session jti=%s user_id=%s", claims.token_id, claims.user_id)

    # 204 carries no body; the cookie removal travels in the response headers.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, request)
    return response


@router.get(
    "/me",
    response_model=UserOut,
    summary="Return the signed-in user",
)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
