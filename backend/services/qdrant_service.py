import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams


class QdrantService:
    """Service for Qdrant vector database operations with session isolation."""

    def __init__(
        self,
        url: str,
        api_key: str,
        collection_name: str,
        embedding_dim: int = 384,
    ):
        self._client = QdrantClient(url=url, api_key=api_key)
        self._collection_name = collection_name
        self._embedding_dim = embedding_dim
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        try:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise

    def store_embeddings(
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
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            point = models.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "session_id": session_id,
                    "document_id": document_id,
                    "content": chunk["content"],
                    "file_name": chunk["file_name"],
                    "page_number": chunk.get("page_number"),
                },
            )
            points.append(point)

        if points:
            self._client.upsert(
                collection_name=self._collection_name,
                points=points,
            )

        return len(points)

    def search(
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
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=query_embedding,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="session_id",
                        match=models.MatchValue(value=session_id),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )

        results = []
        for point in response.points:
            if point.payload:
                results.append({
                    "content": point.payload.get("content", ""),
                    "file_name": point.payload.get("file_name", "Unknown"),
                    "page_number": point.payload.get("page_number"),
                    "document_id": point.payload.get("document_id"),
                    "score": point.score,
                })

        return results

    def delete_session_data(self, session_id: str) -> None:
        """Delete all vectors belonging to a session."""
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="session_id",
                            match=models.MatchValue(value=session_id),
                        )
                    ]
                )
            ),
        )

    def delete_document(self, session_id: str, document_id: str) -> None:
        """Delete all vectors belonging to a specific document in a session."""
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="session_id",
                            match=models.MatchValue(value=session_id),
                        ),
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        ),
                    ]
                )
            ),
        )

    def health_check(self) -> bool:
        """Check if Qdrant connection is healthy."""
        try:
            self._client.get_collection(self._collection_name)
            return True
        except Exception:
            return False


# Singleton instance
_qdrant_service: QdrantService | None = None


def get_qdrant_service() -> QdrantService:
    """Get the singleton Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        from config import get_settings
        settings = get_settings()
        _qdrant_service = QdrantService(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            collection_name=settings.qdrant_collection_name,
        )
    return _qdrant_service
