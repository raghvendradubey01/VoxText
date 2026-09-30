"""Speech-to-text endpoints.

Behaviour matches the original API (``POST /api/transcribe`` with ``audio`` and
``task`` form fields), but access now requires a signed-in user, uploads are
validated and streamed to disk, and the model runs in a threadpool.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..models import User
from ..schemas import TranscriptionOut
from ..security.deps import get_current_user, require_same_origin
from ..services import speech
from ..services.errors import SpeechEngineError
from ..services.uploads import discard_upload, store_upload

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["speech"],
    dependencies=[Depends(require_same_origin)],
)


@router.post(
    "/transcribe",
    response_model=TranscriptionOut,
    summary="Transcribe or translate an audio recording",
)
async def transcribe(
    audio: UploadFile = File(..., description="Recorded blob or audio file."),
    task: str = Form("transcribe", description="'transcribe' or 'translate'."),
    current_user: User = Depends(get_current_user),
) -> TranscriptionOut:
    if task not in speech.TASKS:
        raise HTTPException(
            status_code=400, detail="task must be 'transcribe' or 'translate'."
        )

    settings = get_settings()
    # Validation happens before anything touches disk: extension allow-list,
    # sanitised name, generated file name, hard size ceiling.
    stored = await store_upload(audio, settings.resolved_upload_dir)
    logger.info(
        "user_id=%s started %s of %d bytes", current_user.id, task, stored.size
    )

    try:
        result = await run_in_threadpool(speech.transcribe, stored.path, task)
    except SpeechEngineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:  # noqa: BLE001 - reported generically on purpose
        # The real error goes to the server log, never to the browser.
        logger.exception("Transcription failed for %s", stored.path.name)
        raise HTTPException(
            status_code=500,
            detail="Transcription failed. Check that the recording contains valid audio.",
        ) from exc
    finally:
        discard_upload(stored)

    logger.info(
        "user_id=%s finished %s (%d characters)",
        current_user.id,
        task,
        len(result.text),
    )
    return TranscriptionOut(
        text=result.text,
        language=result.language,
        language_probability=result.language_probability,
        duration=result.duration,
        task=result.task,
    )