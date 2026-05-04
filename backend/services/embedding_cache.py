"""In-memory LRU + TTL cache for query embeddings.

Why in-memory and not Redis/Postgres?
- FastEmbed runs locally (~10-30ms per query). Cache benefit is not cost
  reduction (it's already free), it's latency stability under load.
- Voice_rag has short session TTLs and no horizontal scaling yet.
- Simple LRU+TTL inside the worker process is the right tradeoff. When/if we
  scale out (or move to Sprint 3 TTS audio cache where benefit is real $$),
  we can swap this implementation behind the same interface.

Thread-safety: protected by an asyncio.Lock so concurrent /query requests
don't corrupt the OrderedDict.
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """LRU cache with TTL for query → embedding lookups."""

    def __init__(self, max_entries: int = 512, ttl_seconds: int = 3600):
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[list[float], float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(text: str) -> str:
        # Normalize: strip + lowercase. SHA256 keeps the cache O(1) on memory
        # regardless of query length.
        normalized = text.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def get(self, text: str) -> list[float] | None:
        """Return cached embedding or None on miss/expiry."""
        if not text:
            return None
        key = self._key(text)
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            embedding, stored_at = entry
            if time.monotonic() - stored_at > self._ttl:
                # Expired — drop it.
                del self._store[key]
                self._misses += 1
                return None
            # LRU: move to end (most recently used)
            self._store.move_to_end(key)
            self._hits += 1
            return embedding

    async def set(self, text: str, embedding: list[float]) -> None:
        """Store an embedding, evicting the oldest entry if over capacity."""
        if not text or not embedding:
            return
        key = self._key(text)
        async with self._lock:
            self._store[key] = (embedding, time.monotonic())
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    async def stats(self) -> dict:
        """Return basic stats for /health or /metrics endpoints."""
        async with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._store),
                "max": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": (self._hits / total) if total else 0.0,
            }

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0


# Singleton
_embedding_cache: EmbeddingCache | None = None


def get_embedding_cache() -> EmbeddingCache:
    """Return the singleton embedding cache.

    Settings are read lazily so tests can monkey-patch get_settings before
    the first call.
    """
    global _embedding_cache
    if _embedding_cache is None:
        from config import get_settings

        settings = get_settings()
        _embedding_cache = EmbeddingCache(
            max_entries=settings.embedding_cache_max_entries,
            ttl_seconds=settings.embedding_cache_ttl_seconds,
        )
    return _embedding_cache
