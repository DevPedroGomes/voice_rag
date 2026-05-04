"""Speech-to-Text endpoint.

Sprint 3.1b — exposes the TranscriptionService over HTTP. Mounted under
/api/session/{session_id}/transcribe to keep the session-scoped pattern
consistent with /documents and /query (the session must exist and be
within rate limits before we'll spend Whisper budget on its audio).

Flow:
    1. Browser records audio with MediaRecorder (webm/opus or mp4/aac).
    2. Browser POSTs the blob as multipart/form-data to this endpoint.
    3. We forward to Whisper, return {text, language}.
    4. Browser shows the transcript in the textarea — user can edit
       before submitting to /query. This editability is intentional:
       Whisper isn't perfect, and a typo in voice is much more annoying
       than a typo in text.
"""

import logging
import time

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from config import get_settings
from models.schemas import TranscriptionResponse
from services.session_service import SessionStore, get_session_store
from services.transcription_service import (
    ALLOWED_AUDIO_EXTENSIONS,
    MAX_AUDIO_BYTES,
    TranscriptionError,
    TranscriptionService,
    WHISPER_LANGUAGES,
    get_transcription_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session/{session_id}", tags=["transcription"])


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    session_id: str,
    audio: UploadFile = File(..., description="Recorded audio blob"),
    language: str | None = Query(
        default=None,
        pattern=r"^[a-z]{2}(-[A-Z]{2})?$",
        description="ISO-639-1 hint (e.g. 'pt', 'en'). Omit for auto-detect.",
    ),
    session_store: SessionStore = Depends(get_session_store),
    transcription_service: TranscriptionService = Depends(get_transcription_service),
):
    """Transcribe a recorded audio blob into text.

    The endpoint enforces session existence (so anonymous traffic can't
    burn Whisper credit) but does NOT consume the per-session query quota
    — transcription is a precondition for asking, not asking itself.
    """
    settings = get_settings()
    if not settings.enable_stt:
        raise HTTPException(
            status_code=503,
            detail="Speech-to-text is disabled on this server.",
        )

    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # Onda 3 — Whisper transcription quota (per-session). Enforced BEFORE we
    # read the audio bytes, so an exhausted quota costs the server zero
    # bandwidth.
    if session.transcribe_count >= settings.max_transcribes_per_session:
        raise HTTPException(
            status_code=429,
            detail="Transcription quota exceeded for this session",
            headers={"Retry-After": "0"},
        )

    # Onda 3 — language whitelist. Pattern already enforced 2-letter ISO-639-1
    # (optionally with country); this verifies it's actually a Whisper-known
    # code so we never burn the round trip on a bogus hint.
    if language is not None:
        primary = language.split("-", 1)[0]
        if primary not in WHISPER_LANGUAGES:
            raise HTTPException(status_code=400, detail="Unsupported language")

    if not audio.filename:
        raise HTTPException(status_code=400, detail="audio file is required")

    # Pre-validate extension before reading bytes — saves bandwidth on
    # obviously bad uploads.
    ext = audio.filename.rsplit(".", 1)[-1].lower() if "." in audio.filename else ""
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio extension '{ext}'. "
                f"Use one of: {sorted(ALLOWED_AUDIO_EXTENSIONS)}"
            ),
        )

    # Read up to MAX_AUDIO_BYTES + 1 so we can detect oversized uploads
    # without holding an arbitrary file in memory.
    audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large. Maximum size is {MAX_AUDIO_BYTES} bytes.",
        )

    started = time.monotonic()
    try:
        text, detected_lang = await transcription_service.transcribe(
            audio_bytes=audio_bytes,
            filename=audio.filename,
            language_hint=language,
        )
    except TranscriptionError as e:
        # User-fixable problems (empty audio, no speech, oversized) → 400.
        # Vendor outages → 502 so the frontend can show a clean retry UI.
        msg = str(e)
        status = 400 if any(
            kw in msg for kw in ("empty", "no speech", "extension", "too large")
        ) else 502
        logger.info(
            "transcription rejected (%d) for session %s: %s",
            status, session_id, msg,
        )
        raise HTTPException(status_code=status, detail=msg)

    duration_ms = int((time.monotonic() - started) * 1000)
    # Onda 3 — only count *successful* transcriptions toward the quota.
    # Bad recordings (TranscriptionError above) are already a UX cost.
    await session_store.increment_transcribe_count(session_id)
    logger.info(
        "transcription ok: session=%s len=%dB chars=%d lang=%s took=%dms",
        session_id, len(audio_bytes), len(text),
        detected_lang or language or "?", duration_ms,
    )

    return TranscriptionResponse(
        text=text,
        language=detected_lang or language,
        duration_ms=duration_ms,
    )
