"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MAX_PASSWORD_BYTES = 72  # bcrypt ignores bytes beyond this limit.


class SignupRequest(BaseModel):
    email: EmailStr = Field(description="Account email address.")
    password: str = Field(min_length=8, max_length=200)
    full_name: str | None = Field(default=None, max_length=120)

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("full_name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("password")
    @classmethod
    def _check_password_length(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not be blank.")
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded."
            )
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class UserOut(BaseModel):
    """Public user representation - never contains credentials or hashes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None
    created_at: datetime
    last_login_at: datetime | None


class StatusResponse(BaseModel):
    detail: str


class TranscriptionOut(BaseModel):
    """Shape kept identical to the original API so the existing UI keeps working."""

    text: str
    language: str | None
    language_probability: float
    duration: float
    task: str


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    speech_model: str
    speech_model_ready: bool
    speech_model_error: str | None
