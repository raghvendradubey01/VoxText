"""Environment-driven configuration.

Every runtime-configurable value lives here and is read from the process
environment (optionally loaded from a local ``.env`` file).  No secret is ever
hard-coded and no secret is ever sent to the browser.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
APP_VERSION = "2.0.0"
# Git-ignored directory used only to persist an auto-generated development key.
INSTANCE_DIR = BASE_DIR / "instance"

# A development key is generated once and reused across restarts so that local
# sessions do not vanish on every ``--reload`` cycle.  It is never committed.
_DEV_KEY_FILE = INSTANCE_DIR / "dev_secret.key"
_DEV_KEY_BYTES = 48


def _load_or_create_dev_key() -> str:
    """Return a stable random key for local development only."""
    if _DEV_KEY_FILE.is_file():
        existing = _DEV_KEY_FILE.read_text(encoding="ascii").strip()
        if len(existing) >= 32:
            return existing
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(_DEV_KEY_BYTES)
    _DEV_KEY_FILE.write_text(generated, encoding="ascii")
    return generated


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "VoxText"
    debug: bool = True

    # --- Security ----------------------------------------------------------
    # Required in production (DEBUG=false).  Auto-generated for local dev.
    secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    session_max_age_seconds: int = Field(default=60 * 60 * 24 * 7, ge=60)
    session_cookie_name: str = "voxtext_session"
    # When None the cookie is marked Secure automatically for HTTPS requests.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    bcrypt_rounds: int = Field(default=12, ge=4, le=15)
    # Login brute-force protection (per IP + email).
    login_max_attempts: int = Field(default=10, ge=1)
    login_window_seconds: int = Field(default=900, ge=30)

    # --- Database ----------------------------------------------------------
    # SQLite for development; swap to postgresql+psycopg://... without code changes.
    database_url: str = "sqlite:///./voxtext.db"

    # --- Speech to text ----------------------------------------------------
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = Field(default=5, ge=1, le=20)
    whisper_warm_on_startup: bool = True
    upload_dir: Path = Path("uploads")
    max_upload_mb: int = Field(default=25, ge=1, le=200)
    allowed_audio_extensions: list[str] = [
        ".webm",
        ".wav",
        ".mp3",
        ".m4a",
        ".mp4",
        ".ogg",
        ".opus",
        ".flac",
        ".aac",
    ]

    # --- CORS --------------------------------------------------------------
    # Same-origin by default; list origins only if the frontend is separated.
    cors_origins: list[str] = []

    @field_validator("cookie_samesite")
    @classmethod
    def _validate_samesite(cls, value: str) -> str:
        allowed = {"lax", "strict", "none"}
        normalised = value.strip().lower()
        if normalised not in allowed:
            raise ValueError(f"cookie_samesite must be one of {sorted(allowed)}")
        return normalised

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if stripped == "":
            # An unset/blank SECRET_KEY (as shipped in .env.example) means
            # "not configured", not "invalid": fall back to the development
            # default instead of refusing to start.
            return None
        if stripped in {"change-me", "changeme", "secret", "your-secret-key"}:
            raise ValueError(
                "SECRET_KEY is set to a placeholder value. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if len(stripped.encode("utf-8")) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 bytes for HS256. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return stripped

    @property
    def resolved_secret_key(self) -> str:
        """Secret used to sign session tokens (fails fast outside DEBUG)."""
        if self.secret_key:
            return self.secret_key
        if not self.debug:
            raise RuntimeError(
                "SECRET_KEY must be set in the environment when DEBUG=false."
            )
        return _load_or_create_dev_key()

    @property
    def secret_is_auto_generated(self) -> bool:
        return self.secret_key is None

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def resolved_upload_dir(self) -> Path:
        """Absolute upload directory, resolved relative to the project root."""
        candidate = Path(self.upload_dir)
        return candidate if candidate.is_absolute() else BASE_DIR / candidate


@lru_cache
def get_settings() -> Settings:
    return Settings()
