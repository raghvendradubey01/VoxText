"""Operational endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import APP_VERSION, get_settings
from ..schemas import HealthOut
from ..services import speech

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthOut, summary="Service status")
def health() -> HealthOut:
    settings = get_settings()
    return HealthOut(
        status="ok",
        app=settings.app_name,
        version=APP_VERSION,
        speech_model=settings.whisper_model,
        speech_model_ready=speech.model_is_ready(),
        speech_model_error=speech.model_load_error(),
    )
