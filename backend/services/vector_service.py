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
        """Create the embeddings table if it doesn't exist."""
        async with self._pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # Create embeddings table
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

            # Create indexes for efficient querying
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_session_id
                ON embeddings(session_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_document_id
                ON embeddings(document_id)
            """)

            # Create vector index for similarity search (IVFFlat)
            # Only create if table has data, otherwise use exact search
            try:
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_embeddings_vector
                    ON embeddings USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                """)
            except asyncpg.exceptions.InvalidParameterValueError:
                # IVFFlat requires data to build, will be created later
                logger.info("IVFFlat index will be created when data is added")

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
