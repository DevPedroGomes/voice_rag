"""TTS audio cache backed by PostgreSQL.

Sprint 3.3 — Most voice_rag answers are FAQs ("what's the phone number?",
"what's the address?"). Generating the same TTS audio over and over is
the lowest-hanging fruit for both latency and cost.

Why PostgreSQL and not Redis or filesystem?
- Voice_rag already runs PostgreSQL. Adding a service is overkill at this scale.
- Audio blobs are small (a 30-second answer is ~250-400 KB of MP3).
- BYTEA + HASH index gives us O(1) lookups in <5ms.
- Survives backend restarts (in-memory cache would warm cold every deploy).
- Trivially TTL-able from a periodic cleanup task.

Key = SHA256(text + voice + tts_model). The model in the key is critical:
swapping models invalidates the cache automatically without manual flushes.

Caveat: this caches the *complete MP3*, used by /audio/download. The SSE
streaming path (PCM chunks) is harder to cache meaningfully because clients
expect chunked frames; for streaming, the win comes from Sprint 3.4
(parallel TTS↔LLM), not the cache.
"""

import hashlib
import logging
import time

import asyncpg

logger = logging.getLogger(__name__)


def _cache_key(text: str, voice: str, model: str) -> str:
    """Stable cache key. Includes model so a TTS upgrade auto-invalidates."""
    payload = f"{model}\x00{voice}\x00{text.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TTSCache:
    """PostgreSQL-backed cache for full TTS audio blobs."""

    def __init__(self, pool: asyncpg.Pool, ttl_seconds: int = 86400):
        self._pool = pool
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    @classmethod
    async def ensure_schema(cls, pool: asyncpg.Pool) -> None:
        """Create the cache table if missing. Idempotent.

        Stored fields:
            cache_key   sha256 of (model, voice, text) — primary key
            audio_data  raw audio bytes (mp3 by default)
            content_type 'audio/mpeg' for mp3, etc.
            created_at  for TTL cleanup
        """
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tts_cache (
                    cache_key CHAR(64) PRIMARY KEY,
                    audio_data BYTEA NOT NULL,
                    content_type VARCHAR(32) NOT NULL DEFAULT 'audio/mpeg',
                    voice VARCHAR(32) NOT NULL,
                    model VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # created_at index speeds up the periodic TTL sweep.
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tts_cache_created_at
                ON tts_cache(created_at)
            """)

    async def get(
        self, text: str, voice: str, model: str
    ) -> tuple[bytes, str] | None:
        """Return (audio_bytes, content_type) on hit, None on miss/expiry."""
        key = _cache_key(text, voice, model)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT audio_data, content_type, created_at
                FROM tts_cache
                WHERE cache_key = $1
                """,
                key,
            )
        if row is None:
            self._misses += 1
            return None

        # Check TTL in Python — avoids burning a row lock and lets us
        # log the eviction explicitly.
        age = (time.time() - row["created_at"].timestamp())
        if age > self._ttl:
            # Stale; let the cleanup job collect it.
            self._misses += 1
            return None

        self._hits += 1
        return bytes(row["audio_data"]), row["content_type"]

    async def set(
        self,
        text: str,
        voice: str,
        model: str,
        audio_data: bytes,
        content_type: str = "audio/mpeg",
    ) -> None:
        """Store an audio blob. UPSERT — last write wins on key collision."""
        if not audio_data:
            return
        key = _cache_key(text, voice, model)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tts_cache (cache_key, audio_data, content_type, voice, model)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (cache_key) DO UPDATE
                SET audio_data = EXCLUDED.audio_data,
                    content_type = EXCLUDED.content_type,
                    created_at = NOW()
                """,
                key,
                audio_data,
                content_type,
                voice,
                model,
            )

    async def cleanup_expired(self) -> int:
        """Delete entries older than TTL. Returns row count."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM tts_cache
                WHERE created_at < NOW() - ($1 || ' seconds')::interval
                """,
                str(self._ttl),
            )
        # asyncpg returns "DELETE N"
        try:
            removed = int(result.split()[-1])
        except (ValueError, IndexError):
            removed = 0
        if removed:
            logger.info("tts_cache: cleaned %d expired entries", removed)
        return removed

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (self._hits / total) if total else 0.0,
        }


# Singleton wiring — initialized from main.py lifespan after the
# vector_service pool is up (we share the pool to avoid a second
# connection set).
_tts_cache: TTSCache | None = None


def init_tts_cache(pool: asyncpg.Pool, ttl_seconds: int) -> TTSCache:
    """Build the cache singleton. Call once at startup."""
    global _tts_cache
    _tts_cache = TTSCache(pool=pool, ttl_seconds=ttl_seconds)
    return _tts_cache


def get_tts_cache() -> TTSCache | None:
    """Return the singleton or None if it wasn't initialized (cache disabled)."""
    return _tts_cache
