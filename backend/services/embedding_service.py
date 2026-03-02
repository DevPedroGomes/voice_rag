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

        Args:
            text: Text string to embed

        Returns:
            Embedding vector
        """
        embeddings = await self.embed([text])
        return embeddings[0]


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
