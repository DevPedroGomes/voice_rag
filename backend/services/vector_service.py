import logging
import uuid
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


class VectorService:
    """Service for vector database operations using PostgreSQL + pgvector."""

    def __init__(self, embedding_dim: int = 384):
        self._pool: asyncpg.Pool | None = None
        self._embedding_dim = embedding_dim

    async def initialize(self, database_url: str) -> None:
        """Initialize the database connection pool and schema."""
        self._pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            init=self._init_connection,
        )
        await self._ensure_schema()
        logger.info("VectorService initialized with pgvector")

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize pgvector extension on each connection."""
        await register_vector(conn)

    async def _ensure_schema(self) -> None:
        """Create the embeddings table and indexes if they don't exist.

        Idempotent: safe to run on every startup. Adds new columns/indexes
        without dropping existing data. Migrates IVFFlat → HNSW transparently.
        """
        async with self._pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # Create embeddings table (base schema)
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    session_id VARCHAR(36) NOT NULL,
                    document_id VARCHAR(36) NOT NULL,
                    content TEXT,
                    file_name VARCHAR(255),
                    page_number INT,
                    embedding vector({self._embedding_dim}),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Sprint 1.1 - Hybrid Search: add tsvector column for keyword search
            # GENERATED column auto-updates with content. 'simple' dict is
            # language-agnostic (works for pt-BR + en without aggressive stemming).
            await conn.execute("""
                ALTER TABLE embeddings
                ADD COLUMN IF NOT EXISTS search_vector tsvector
                GENERATED ALWAYS AS (
                    to_tsvector('simple', coalesce(content, ''))
                ) STORED
            """)

            # Session/document filters
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_session_id
                ON embeddings(session_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_document_id
                ON embeddings(document_id)
            """)

            # Sprint 1.1 - GIN index for keyword search (BM25-like via ts_rank)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_search_vector
                ON embeddings USING GIN(search_vector)
            """)

            # Sprint 1.1 - HNSW index for semantic search
            # Replaces previous IVFFlat (better recall, no need to rebuild after inserts).
            # Drop the old IVFFlat index if it exists (one-time migration).
            await conn.execute("DROP INDEX IF EXISTS idx_embeddings_vector")
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw
                ON embeddings USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)

    async def store_embeddings(
        self,
        session_id: str,
        document_id: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> int:
        """
        Store document chunk embeddings with session isolation.

        Args:
            session_id: Session identifier for isolation
            document_id: Document identifier
            chunks: List of dicts with 'content', 'page_number', 'file_name'
            embeddings: Corresponding embedding vectors

        Returns:
            Number of points stored
        """
        if not chunks:
            return 0

        async with self._pool.acquire() as conn:
            # Prepare data for batch insert
            records = [
                (
                    str(uuid.uuid4()),
                    session_id,
                    document_id,
                    chunk["content"],
                    chunk["file_name"],
                    chunk.get("page_number"),
                    embedding,
                )
                for chunk, embedding in zip(chunks, embeddings)
            ]

            await conn.executemany(
                """
                INSERT INTO embeddings (id, session_id, document_id, content, file_name, page_number, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                records,
            )

        return len(records)

    async def search(
        self,
        session_id: str,
        query_embedding: list[float],
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Search for similar documents within a session.

        Args:
            session_id: Session identifier for isolation
            query_embedding: Query vector
            limit: Maximum number of results

        Returns:
            List of matching documents with content and metadata
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    content,
                    file_name,
                    page_number,
                    document_id,
                    1 - (embedding <=> $1::vector) as score
                FROM embeddings
                WHERE session_id = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                query_embedding,
                session_id,
                limit,
            )

        return [
            {
                "content": row["content"],
                "file_name": row["file_name"],
                "page_number": row["page_number"],
                "document_id": row["document_id"],
                "score": float(row["score"]) if row["score"] else 0.0,
            }
            for row in rows
        ]

    async def search_hybrid(
        self,
        session_id: str,
        query_text: str,
        query_embedding: list[float],
        limit: int = 5,
        candidates_multiplier: int = 3,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Hybrid search combining semantic (HNSW cosine) + keyword (GIN tsvector)
        rankings via Reciprocal Rank Fusion.

        Args:
            session_id: Session identifier for isolation.
            query_text: Original query string (used for tsquery).
            query_embedding: Query vector for semantic search.
            limit: Final number of results to return.
            candidates_multiplier: Each ranker fetches limit*multiplier candidates
                before fusion (gives reranker headroom downstream).
            rrf_k: RRF constant (60 is the standard from Cormack et al. 2009).

        Returns:
            List of dicts ordered by RRF score, each with content/file_name/
            page_number/document_id/score (RRF) and rank metadata.
        """
        prefetch = max(limit * candidates_multiplier, limit)

        async with self._pool.acquire() as conn:
            # Two parallel rankings in a single round-trip via CTEs.
            # plainto_tsquery is permissive (no special syntax errors).
            rows = await conn.fetch(
                """
                WITH semantic AS (
                    SELECT
                        id,
                        content,
                        file_name,
                        page_number,
                        document_id,
                        ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS rank,
                        1 - (embedding <=> $1::vector) AS sem_score
                    FROM embeddings
                    WHERE session_id = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                ),
                keyword AS (
                    SELECT
                        id,
                        content,
                        file_name,
                        page_number,
                        document_id,
                        ROW_NUMBER() OVER (
                            ORDER BY ts_rank_cd(search_vector, plainto_tsquery('simple', $4)) DESC
                        ) AS rank,
                        ts_rank_cd(search_vector, plainto_tsquery('simple', $4)) AS kw_score
                    FROM embeddings
                    WHERE session_id = $2
                      AND search_vector @@ plainto_tsquery('simple', $4)
                    ORDER BY ts_rank_cd(search_vector, plainto_tsquery('simple', $4)) DESC
                    LIMIT $3
                ),
                fused AS (
                    SELECT
                        COALESCE(s.id, k.id) AS id,
                        COALESCE(s.content, k.content) AS content,
                        COALESCE(s.file_name, k.file_name) AS file_name,
                        COALESCE(s.page_number, k.page_number) AS page_number,
                        COALESCE(s.document_id, k.document_id) AS document_id,
                        COALESCE(1.0 / ($5 + s.rank), 0.0)
                            + COALESCE(1.0 / ($5 + k.rank), 0.0) AS rrf_score,
                        s.sem_score,
                        k.kw_score
                    FROM semantic s
                    FULL OUTER JOIN keyword k ON s.id = k.id
                )
                SELECT *
                FROM fused
                ORDER BY rrf_score DESC
                LIMIT $6
                """,
                query_embedding,
                session_id,
                prefetch,
                query_text,
                rrf_k,
                limit,
            )

        return [
            {
                "content": row["content"],
                "file_name": row["file_name"],
                "page_number": row["page_number"],
                "document_id": row["document_id"],
                # Primary score = RRF (used by grader). Keep raw signals for
                # debugging / future reranker integration.
                "score": float(row["rrf_score"]) if row["rrf_score"] else 0.0,
                "semantic_score": float(row["sem_score"]) if row["sem_score"] else 0.0,
                "keyword_score": float(row["kw_score"]) if row["kw_score"] else 0.0,
            }
            for row in rows
        ]

    async def delete_session_data(self, session_id: str) -> None:
        """Delete all vectors belonging to a session."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM embeddings WHERE session_id = $1",
                session_id,
            )

    async def delete_document(self, session_id: str, document_id: str) -> None:
        """Delete all vectors belonging to a specific document in a session."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM embeddings WHERE session_id = $1 AND document_id = $2",
                session_id,
                document_id,
            )

    async def health_check(self) -> bool:
        """Check if PostgreSQL connection is healthy."""
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("VectorService connection pool closed")


# Singleton instance
_vector_service: VectorService | None = None


def get_vector_service() -> VectorService:
    """Get the singleton vector service instance."""
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorService()
    return _vector_service
