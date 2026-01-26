import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Callable, Awaitable

from models.schemas import Session, SessionDocument, QueryRecord

logger = logging.getLogger(__name__)


class SessionStore:
    """Thread-safe in-memory session store with inactivity-based cleanup."""

    def __init__(self, inactivity_minutes: int = 5):
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._inactivity_minutes = inactivity_minutes
        self._cleanup_callback: Callable[[str], Awaitable[None]] | None = None

    def set_cleanup_callback(
        self, callback: Callable[[str], Awaitable[None]]
    ) -> None:
        """Set callback to clean up external resources (e.g., database vectors)."""
        self._cleanup_callback = callback

    def _calculate_expires_at(self, from_time: datetime) -> datetime:
        """Calculate expiration time based on inactivity period."""
        return from_time + timedelta(minutes=self._inactivity_minutes)

    async def create(self, client_id: str | None = None) -> Session:
        """Create a new session."""
        async with self._lock:
            now = datetime.utcnow()
            session = Session(
                session_id=str(uuid.uuid4()),
                created_at=now,
                expires_at=self._calculate_expires_at(now),
                last_activity=now,
                documents=[],
                queries=[],
            )
            self._sessions[session.session_id] = session
            return session

    async def get(self, session_id: str) -> Session | None:
        """Get session by ID, returns None if not found or expired."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if datetime.utcnow() > session.expires_at:
                # Clean up expired session
                await self._cleanup_session_data(session_id)
                del self._sessions[session_id]
                return None
            return session

    async def touch(self, session_id: str) -> bool:
        """Update last_activity to extend session expiration."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            now = datetime.utcnow()
            session.last_activity = now
            session.expires_at = self._calculate_expires_at(now)
            return True

    async def delete(self, session_id: str) -> bool:
        """Delete a session and clean up associated resources."""
        async with self._lock:
            if session_id not in self._sessions:
                return False
            await self._cleanup_session_data(session_id)
            del self._sessions[session_id]
            return True

    async def add_document(
        self, session_id: str, document: SessionDocument
    ) -> bool:
        """Add a document to a session and update activity."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            now = datetime.utcnow()
            session.documents.append(document)
            session.last_activity = now
            session.expires_at = self._calculate_expires_at(now)
            return True

    async def remove_document(
        self, session_id: str, document_id: str
    ) -> bool:
        """Remove a document from a session and update activity."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            original_count = len(session.documents)
            session.documents = [
                d for d in session.documents if d.document_id != document_id
            ]
            if len(session.documents) < original_count:
                now = datetime.utcnow()
                session.last_activity = now
                session.expires_at = self._calculate_expires_at(now)
                return True
            return False

    async def add_query(
        self, session_id: str, query: QueryRecord
    ) -> bool:
        """Add a query record to a session's history and update activity."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            now = datetime.utcnow()
            session.queries.append(query)
            session.last_activity = now
            session.expires_at = self._calculate_expires_at(now)
            return True

    async def get_queries(self, session_id: str) -> list[QueryRecord]:
        """Get query history for a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            return list(session.queries)  # Return copy to prevent mutation

    async def cleanup_expired(self) -> int:
        """Remove all inactive sessions. Returns count of removed sessions."""
        async with self._lock:
            now = datetime.utcnow()
            expired = [
                sid for sid, s in self._sessions.items()
                if now > s.expires_at
            ]
            for sid in expired:
                logger.info(f"Cleaning up inactive session {sid}")
                await self._cleanup_session_data(sid)
                del self._sessions[sid]
            return len(expired)

    async def _cleanup_session_data(self, session_id: str) -> None:
        """Clean up external resources for a session."""
        if self._cleanup_callback:
            try:
                await self._cleanup_callback(session_id)
            except Exception as e:
                logger.error(f"Error cleaning up session {session_id}: {e}")

    @property
    def active_sessions_count(self) -> int:
        """Get count of active sessions."""
        return len(self._sessions)


# Singleton instance
_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Get the singleton session store instance."""
    global _session_store
    if _session_store is None:
        from config import get_settings
        settings = get_settings()
        _session_store = SessionStore(inactivity_minutes=settings.session_inactivity_minutes)
    return _session_store
