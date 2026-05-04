import base64
import logging
import os
import tempfile
import uuid
from typing import AsyncGenerator

from openai import AsyncOpenAI

from services.tts_cache import get_tts_cache

logger = logging.getLogger(__name__)


class AudioService:
    """Service for text-to-speech generation with streaming support.

    Sprint 3.3: integrates with TTSCache (PostgreSQL BYTEA) on the
    `generate_mp3` path. Streaming PCM is intentionally NOT cached — see
    tts_cache.py docstring for the rationale (chunk framing is too tied
    to the live SSE handler to cache meaningfully).
    """

    def __init__(self, openai_api_key: str, tts_model: str = "gpt-4o-mini-tts"):
        self._client = AsyncOpenAI(api_key=openai_api_key)
        self._tts_model = tts_model
        self._temp_dir = tempfile.gettempdir()

    @property
    def model(self) -> str:
        return self._tts_model

    async def stream_tts(
        self,
        text: str,
        voice: str,
        instructions: str,
    ) -> AsyncGenerator[str, None]:
        """
        Stream TTS audio as base64-encoded PCM chunks.

        Args:
            text: Text to convert to speech
            voice: Voice to use
            instructions: TTS instructions for tone/style

        Yields:
            Base64-encoded PCM audio chunks
        """
        async with self._client.audio.speech.with_streaming_response.create(
            model=self._tts_model,
            voice=voice,
            input=text,
            instructions=instructions,
            response_format="pcm",
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=4096):
                yield base64.b64encode(chunk).decode("utf-8")

    async def generate_mp3(
        self,
        text: str,
        voice: str,
        instructions: str,
    ) -> str:
        """
        Generate (or fetch cached) MP3 audio file.

        Args:
            text: Text to convert to speech
            voice: Voice to use
            instructions: TTS instructions for tone/style

        Returns:
            Path to the generated MP3 file (always a fresh tempfile, even
            on cache hits — the caller may schedule it for deletion).
        """
        # Sprint 3.3: cache lookup keyed by (model, voice, text). Note that
        # `instructions` is intentionally NOT in the key — the model treats
        # it as a style hint, and the same FAQ shouldn't be cached as N
        # different blobs just because we tweaked the tone.
        cache = get_tts_cache()
        cache_hit = False
        audio_bytes: bytes

        if cache is not None:
            hit = await cache.get(text=text, voice=voice, model=self._tts_model)
            if hit is not None:
                audio_bytes, _content_type = hit
                cache_hit = True
                logger.debug(
                    "tts_cache hit: voice=%s text_len=%d", voice, len(text)
                )

        if not cache_hit:
            response = await self._client.audio.speech.create(
                model=self._tts_model,
                voice=voice,
                input=text,
                instructions=instructions,
                response_format="mp3",
            )
            audio_bytes = response.content

            if cache is not None:
                # Store after the user gets their file — fire and forget.
                # We await to keep error handling simple; cost is one
                # round-trip to local PG (~2-5ms).
                try:
                    await cache.set(
                        text=text,
                        voice=voice,
                        model=self._tts_model,
                        audio_data=audio_bytes,
                        content_type="audio/mpeg",
                    )
                except Exception as e:
                    # Cache write failure must NEVER break the user-facing
                    # path. Log and move on.
                    logger.warning("tts_cache write failed: %s", e)

        file_path = os.path.join(self._temp_dir, f"response_{uuid.uuid4()}.mp3")
        with open(file_path, "wb") as f:
            f.write(audio_bytes)

        return file_path


# Singleton instance
_audio_service: AudioService | None = None


def get_audio_service() -> AudioService:
    """Get the singleton audio service instance."""
    global _audio_service
    if _audio_service is None:
        from config import get_settings
        settings = get_settings()
        _audio_service = AudioService(
            openai_api_key=settings.openai_api_key,
            tts_model=settings.tts_model,
        )
    return _audio_service
