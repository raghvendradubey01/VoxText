"""Validated, sanitised upload storage."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from ..config import get_settings
from .errors import UploadError

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB


@dataclass(frozen=True)
class StoredUpload:
    """A validated file that now lives on disk under our own generated name."""

    path: Path
    size: int
    original_name: str
    extension: str


def _safe_basename(filename: str | None) -> str:
    """Reduce a client-supplied name to a bare base name.

    Guards against path traversal such as ``..\\..\\windows\\system32\\x.mp3``
    or ``/etc/passwd`` arriving in the multipart filename field.
    """
    raw = (filename or "").strip()
    if not raw:
        raise UploadError("The uploaded file must include a file name.")
    # Normalise separators, then keep only the final path component.
    base = raw.replace("\\", "/").rsplit("/", 1)[-1]
    base = os.path.basename(base).strip()
    if base in {"", ".", ".."}:
        raise UploadError("The uploaded file name is not valid.")
    return base


def validate_extension(basename: str) -> str:
    settings = get_settings()
    extension = Path(basename).suffix.lower()
    if extension not in settings.allowed_audio_extensions:
        allowed = ", ".join(sorted(settings.allowed_audio_extensions))
        raise UploadError(
            f"Unsupported audio format '{extension or 'unknown'}'. Allowed: {allowed}.",
            status_code=415,
        )
    return extension


async def store_upload(audio: UploadFile, destination_dir: Path) -> StoredUpload:
    """Stream an upload to disk under a generated name with a hard size cap."""
    settings = get_settings()
    basename = _safe_basename(audio.filename)
    extension = validate_extension(basename)

    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / f"{uuid.uuid4().hex}{extension}"

    written = 0
    try:
        with target.open("wb") as handle:
            while True:
                chunk = await audio.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > settings.max_upload_bytes:
                    raise UploadError(
                        f"File is too large. Maximum supported size is "
                        f"{settings.max_upload_mb} MB.",
                        status_code=413,
                    )
                handle.write(chunk)
    except UploadError:
        target.unlink(missing_ok=True)
        raise
    except OSError:
        logger.exception("Could not store the uploaded file")
        target.unlink(missing_ok=True)
        raise UploadError("The uploaded file could not be stored.", status_code=500)
    except BaseException:
        # Includes asyncio.CancelledError when the client hangs up mid-upload:
        # the partially written file must not outlive the request.
        target.unlink(missing_ok=True)
        raise

    if written == 0:
        target.unlink(missing_ok=True)
        raise UploadError("The uploaded file is empty.")

    audio.file.close()
    return StoredUpload(
        path=target,
        size=written,
        original_name=basename,
        extension=extension,
    )


def discard_upload(stored: StoredUpload) -> None:
    try:
        stored.path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best-effort cleanup
        logger.warning("Could not delete temporary upload %s", stored.path)
