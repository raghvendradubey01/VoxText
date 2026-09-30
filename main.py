"""VoxText application entry point.

Wires configuration, database, security middleware, API routers and the static
frontend together.  Run locally with:

    python -m uvicorn main:app --reload

Layout:

* ``app/config.py``     - environment-driven settings
* ``app/db.py``         - engine, sessions, declarative base
* ``app/models.py``     - ORM models
* ``app/security/``     - password hashing, session tokens, request guards
* ``app/services/``     - uploads + speech recognition
* ``app/routers/``      - HTTP endpoints
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_VERSION, BASE_DIR, get_settings
from app.db import init_db
from app.routers import auth, health
from app.routers import speech as speech_router
from app.security.deps import has_valid_session
from app.services import speech
from app.services.errors import SpeechEngineError, UploadError

settings = get_settings()
PUBLIC_DIR = BASE_DIR / "public"

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("voxtext")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Create tables, prepare the upload dir and pre-load the Whisper model."""
    init_db()
    settings.resolved_upload_dir.mkdir(parents=True, exist_ok=True)

    if settings.whisper_warm_on_startup:
        # Loading hundreds of MB of weights must not block start-up, so it runs
        # in the background and /api/health reports readiness.
        threading.Thread(
            target=speech.warm_model, name="speech-model-warmup", daemon=True
        ).start()
    else:
        logger.info("Speech model warm-up disabled; it loads on first use")

    logger.info(
        "%s v%s ready (debug=%s, uploads=%s)",
        settings.app_name,
        APP_VERSION,
        settings.debug,
        settings.resolved_upload_dir,
    )
    yield


app = FastAPI(
    title=settings.app_name,
    version=APP_VERSION,
    description="Privacy-first speech-to-text SaaS with account-based access.",
    lifespan=lifespan,
    # Interactive docs are useful locally, not something to advertise publicly.
    docs_url="/api/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.debug else None,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Baseline hardening headers on every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    # Only this origin may use the microphone; camera/geolocation are off.
    response.headers.setdefault(
        "Permissions-Policy", "microphone=(self), camera=(), geolocation=()"
    )
    if request.url.scheme.lower() == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.exception_handler(UploadError)
async def _upload_error_handler(request: Request, exc: UploadError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(SpeechEngineError)
async def _speech_error_handler(
    request: Request, exc: SpeechEngineError
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # The traceback goes to the server log only; clients get a generic message.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500, content={"detail": "An unexpected error occurred."}
    )


app.include_router(auth.router)
app.include_router(speech_router.router)
app.include_router(health.router)


def _page(name: str) -> FileResponse:
    return FileResponse(PUBLIC_DIR / name)


@app.get("/", include_in_schema=False)
async def dashboard(request: Request) -> FileResponse:
    """The transcriber is an authenticated page."""
    if not has_valid_session(request):
        return RedirectResponse(url="/login", status_code=302)
    return _page("index.html")


@app.get("/login", include_in_schema=False)
async def login_page(request: Request) -> FileResponse:
    if has_valid_session(request):
        return RedirectResponse(url="/", status_code=302)
    return _page("login.html")


@app.get("/signup", include_in_schema=False)
async def signup_page(request: Request) -> FileResponse:
    if has_valid_session(request):
        return RedirectResponse(url="/", status_code=302)
    return _page("signup.html")


# Static assets live under one explicit prefix so API and page routes always win
# and the site root cannot be used to probe the filesystem.
app.mount("/static", StaticFiles(directory=PUBLIC_DIR), name="static")

