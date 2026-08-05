import asyncio
import os
from fastembed import TextEmbedding


# Modelo fixado explicitamente em vez de depender do default do FastEmbed.
# O default e uma escolha da biblioteca e pode mudar entre versoes — se mudar,
# muda a dimensao, e a coluna `embeddings.embedding` e `vector(384)` fixo. O
# projeto irmao (group-documents) ficou com a ingestao 100% quebrada por meses
# exatamente por esse desalinhamento entre modelo e schema.
# Multilingue desde 05/08/2026. O anterior era BAAI/bge-small-en-v1.5 — o "en"
# do nome e literal, e este app e de VOZ, com metade do publico falando
# portugues.
#
# Medido no mesmo par pergunta/resposta com um distrator do mesmo idioma, pela
# margem de separacao (similaridade da resposta certa menos a do distrator, que
# e o que decide o ranking):
#
#     bge-small-en-v1.5               EN +0.257   PT +0.103
#     paraphrase-multilingual-MiniLM  EN +0.418   PT +0.386
#
# Em portugues a margem antiga caia 60%. Com poucos chunks ainda acertava; num
# PDF real, com dezenas, o ranking ficava fragil. O novo ganha nos DOIS idiomas.
#
# Mesma dimensao 384, entao o schema `vector(384)` nao muda.
#
# Nao existe migration de dados aqui, e vale registrar por que: sessao expira em
# 5 minutos de inatividade e o cleanup apaga os embeddings junto, entao nao ha
# vetor antigo que sobreviva a troca. Se um dia a base virar persistente,
# ATENCAO: vetor do modelo velho e do novo tem o MESMO tamanho e espacos
# vetoriais diferentes — nada quebraria, nenhum erro apareceria, a busca so
# devolveria o chunk errado com um score plausivel. Nesse dia, re-embeddar
# passa a ser obrigatorio antes de subir.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Tem que bater com vector(N) em `embeddings.embedding`. Mudar exige migration.
EMBEDDING_DIM = 384


class EmbeddingService:
    """Service for generating text embeddings using FastEmbed."""

    def __init__(self):
        self._model = TextEmbedding(
            model_name=EMBEDDING_MODEL,
            cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"),
        )
        # Confere contra o schema logo no boot: falhar aqui, alto e claro, e
        # muito melhor que gravar vetor de dimensao errada e so descobrir no
        # INSERT — ou pior, nao descobrir.
        test_embedding = list(self._model.embed(["test"]))[0]
        self._embedding_dim = len(test_embedding)
        if self._embedding_dim != EMBEDDING_DIM:
            raise RuntimeError(
                f"Dimensao do embedding mudou: modelo '{EMBEDDING_MODEL}' devolveu "
                f"{self._embedding_dim}, mas o schema espera {EMBEDDING_DIM}. "
                f"Alinhe o modelo, EMBEDDING_DIM e o vector(N) da tabela."
            )

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
