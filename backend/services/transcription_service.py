"""Speech-to-Text service backed by OpenAI Whisper.

Sprint 3.1 — closes the voice loop. Until now the user could *hear* answers
but had to *type* questions. This service accepts an audio blob from the
browser (webm/opus, wav, mp3, mp4, m4a) and returns the recognized text plus
the detected language so downstream code can match the response language.

Why a service module (and not just an inline OpenAI call in the router):
- Keeps the OpenAI client lazy and singleton-shaped, consistent with
  audio_service / agent_service.
- Centralizes file size + duration safety limits, language hints, and
  error normalization (a Whisper outage shouldn't crash /api/transcribe —
  the user should see a clean 503).
- Lets us swap to a local Whisper or to a different STT provider behind
  the same `transcribe()` interface.
"""

import io
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


# Whisper API hard limit is 25 MB per request. We cap a bit lower so users
# get a 413 from FastAPI before paying the round trip.
MAX_AUDIO_BYTES = 24 * 1024 * 1024

# Files Whisper accepts. Browser MediaRecorder typically emits webm/opus on
# Chromium and mp4/aac on Safari, so both must work end-to-end.
ALLOWED_AUDIO_EXTENSIONS = {
    "flac", "m4a", "mp3", "mp4", "mpeg", "mpga", "oga", "ogg", "wav", "webm",
}

# Onda 3 — Whisper-supported ISO-639-1 codes. Used by the router to reject
# bogus language hints with a 400 before paying a Whisper round trip. Pattern
# also accepts BCP-47 with country (pt-BR), but only the 2-letter prefix is
# matched here.
WHISPER_LANGUAGES: frozenset[str] = frozenset({
    "en", "pt", "es", "fr", "de", "it", "nl", "ja", "ko", "zh",
    "ar", "ru", "hi", "tr", "pl", "sv", "no", "da", "fi", "el",
    "he", "id", "ms", "th", "vi", "ro", "hu", "cs", "uk", "sk",
    "bg", "hr", "sr", "sl", "et", "lv", "lt", "ca", "eu", "gl",
    "cy", "ga", "mt", "is", "mk", "sq", "hy", "ka", "az", "kk",
    "ky", "uz", "mn", "my", "km", "lo", "si", "ta", "te", "ml",
    "kn", "mr", "gu", "pa", "bn", "ur", "fa", "ps", "am", "sw",
    "yo", "ha", "ig",
})


class TranscriptionError(Exception):
    """Wraps STT failures so the router can map them to a 4xx/5xx cleanly."""


class TranscriptionService:
    """Wrapper around OpenAI Whisper transcription endpoint."""

    def __init__(self, openai_api_key: str, model: str = "whisper-1"):
        self._client = AsyncOpenAI(api_key=openai_api_key)
        self._model = model

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language_hint: str | None = None,
    ) -> tuple[str, str | None]:
        """Transcribe a single audio blob.

        Args:
            audio_bytes: Raw bytes of the recorded audio. The blob keeps its
                original container (webm/mp4/wav...) — Whisper auto-detects.
            filename: Original or synthesized filename. Whisper uses the
                extension to pick a decoder, so this MUST end with one of
                ALLOWED_AUDIO_EXTENSIONS.
            language_hint: Optional ISO-639-1 code (e.g. "pt", "en"). When
                provided, Whisper skips language detection — slightly faster
                and more accurate. None lets Whisper detect.

        Returns:
            (text, detected_language). `detected_language` is None when a
            language_hint was supplied (the API doesn't echo it back in
            verbose_json with hints).

        Raises:
            TranscriptionError: For any user-fixable problem (empty audio,
                bad extension, file too big) or vendor failure.
        """
        if not audio_bytes:
            raise TranscriptionError("audio is empty")

        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise TranscriptionError(
                f"audio too large ({len(audio_bytes)} bytes); "
                f"max is {MAX_AUDIO_BYTES}"
            )

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            raise TranscriptionError(
                f"unsupported audio extension '{ext}'; expected one of "
                f"{sorted(ALLOWED_AUDIO_EXTENSIONS)}"
            )

        # The OpenAI SDK accepts a file-like object with a name attribute.
        # We wrap the bytes in BytesIO so we don't touch the disk.
        buf = io.BytesIO(audio_bytes)
        buf.name = filename  # SDK reads .name to determine MIME

        try:
            kwargs: dict = {
                "model": self._model,
                "file": buf,
                # verbose_json gives us .language for free when no hint is set.
                "response_format": "verbose_json",
            }
            if language_hint:
                kwargs["language"] = language_hint

            response = await self._client.audio.transcriptions.create(**kwargs)
        except Exception as e:
            logger.warning("transcription: Whisper call failed: %s", e)
            raise TranscriptionError(f"transcription failed: {e}") from e

        # response is a Pydantic-like object exposing .text and .language
        text = (getattr(response, "text", "") or "").strip()
        detected = getattr(response, "language", None)

        if not text:
            raise TranscriptionError("no speech detected in audio")

        return text, detected


# Singleton
_transcription_service: TranscriptionService | None = None


def get_transcription_service() -> TranscriptionService:
    """Return the singleton transcription service."""
    global _transcription_service
    if _transcription_service is None:
        from config import get_settings

        settings = get_settings()
        _transcription_service = TranscriptionService(
            openai_api_key=settings.openai_api_key,
            model=settings.whisper_model,
        )
    return _transcription_service
