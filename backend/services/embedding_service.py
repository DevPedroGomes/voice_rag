import asyncio
import os
from fastembed import TextEmbedding


class EmbeddingService:
    """Service for generating text embeddings using FastEmbed."""

    def __init__(self):
        self._model = TextEmbedding(cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))
        # Get embedding dimension from a test embedding
        test_embedding = list(self._model.embed(["test"]))[0]
        self._embedding_dim = len(test_embedding)

    @property
    def embedding_dim(self) -> int:
        """Get the dimension of the embedding vectors."""
        return self._embedding_dim

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous embedding generation."""
        embeddings = list(self._model.embed(texts))
        return [emb.tolist() for emb in embeddings]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts (async, non-blocking).

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        return await asyncio.to_thread(self._embed_sync, texts)

    async def embed_single(self, text: str) -> list[float]:
        """
        Generate embedding for a single text (async, non-blocking).

        Uses an in-memory LRU+TTL cache to avoid recomputing embeddings for
        repeated queries within the cache's lifetime. Cache lookup is O(1)
        and bypasses both the lock-protected ONNX runtime and the
        asyncio.to_thread context switch.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector
        """
        # Lazy import to avoid circular dependency at module load time and
        # to keep this method usable in environments where settings aren't
        # fully wired (e.g., unit tests).
        from config import get_settings
        from services.embedding_cache import get_embedding_cache

        settings = get_settings()
        cache = get_embedding_cache() if settings.enable_embedding_cache else None

        if cache is not None:
            cached = await cache.get(text)
            if cached is not None:
                return cached

        embeddings = await self.embed([text])
        result = embeddings[0]

        if cache is not None:
            await cache.set(text, result)

        return result


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
