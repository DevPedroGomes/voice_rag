import base64
import os
import tempfile
import uuid
from typing import AsyncGenerator

from openai import AsyncOpenAI


class AudioService:
    """Service for text-to-speech generation with streaming support."""

    def __init__(self, openai_api_key: str):
        self._client = AsyncOpenAI(api_key=openai_api_key)
        self._temp_dir = tempfile.gettempdir()

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
            model="gpt-4o-mini-tts",
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
        Generate MP3 audio file.

        Args:
            text: Text to convert to speech
            voice: Voice to use
            instructions: TTS instructions for tone/style

        Returns:
            Path to the generated MP3 file
        """
        response = await self._client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
            instructions=instructions,
            response_format="mp3",
        )

        file_path = os.path.join(self._temp_dir, f"response_{uuid.uuid4()}.mp3")
        with open(file_path, "wb") as f:
            f.write(response.content)

        return file_path


# Singleton instance
_audio_service: AudioService | None = None


def get_audio_service() -> AudioService:
    """Get the singleton audio service instance."""
    global _audio_service
    if _audio_service is None:
        from config import get_settings
        settings = get_settings()
        _audio_service = AudioService(openai_api_key=settings.openai_api_key)
    return _audio_service
