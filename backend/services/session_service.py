"""Postgres-backed session store (Onda 3 — D7).

Replaces the previous in-memory `SessionStore` with an asyncpg-backed
implementation. Why:
- HA: the API can be horizontally scaled without sticky sessions.
- Restart-safe: sessions, quotas and per-IP rate limit windows survive a
  container redeploy.
- One process is no longer the global rate-limit bottleneck.

Design notes:
- Reuses the connection pool owned by `VectorService` to avoid opening a
  second pool against the same database. The pool is wired in via
  `set_pool()` from `main.py` lifespan.
- The `queries` list on the Session domain model is *not* persisted in
  Postgres — only `query_count`. The list was used by the old in-memory
  store for /queries history; now /queries returns an empty list (or can
  be wired to a separate table later). `query_count` is the source of
  truth for quota enforcement.
- Sliding-window per-IP rate limit on session creation uses a tiny
  `session_create_log` table — we INSERT then COUNT rows newer than 60s.
  Cheap with the (ip, created_at) index. A daily cleanup keeps it small.
- All timestamps use timezone-aware UTC (`datetime.now(timezone.utc)`)
  since `datetime.utcnow()` is deprecated in Python 3.12+.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

import asyncpg

from models.schemas import Session, SessionDocument, QueryRecord

logger = logging.getLogger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    transcribe_count INT NOT NULL DEFAULT 0,
    query_count INT NOT NULL DEFAULT 0,
    documents JSONB NOT NULL DEFAULT '[]'::jsonb,
    creator_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS session_create_log (
    id BIGSERIAL PRIMARY KEY,
    ip TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_session_create_log_ip_ts
    ON session_create_log(ip, created_at);
"""


class SessionRateLimitError(Exception):
    """Raised when a per-IP session creation rate limit is hit."""


class SessionStore:
    """Postgres-backed session store with inactivity-based cleanup."""

    def __init__(
        self,
        inactivity_minutes: int = 5,
        max_sessions_per_minute: int = 10,
        max_sessions_per_minute_per_ip: int = 10,
    ):
        self._pool: asyncpg.Pool | None = None
        self._inactivity_minutes = inactivity_minutes
        self._max_sessions_per_minute = max_sessions_per_minute
        self._max_sessions_per_minute_per_ip = max_sessions_per_minute_per_ip
        self._cleanup_callback: Callable[[str], Awaitable[None]] | None = None

    # ----- wiring ---------------------------------------------------------

    def set_pool(self, pool: asyncpg.Pool) -> None:
        """Inject the asyncpg pool (shared with VectorService)."""
        self._pool = pool

    async def ensure_schema(self) -> None:
        """Create tables/indexes if they don't exist. Idempotent."""
        assert self._pool is not None, "SessionStore.set_pool() must be called first"
        async with self._pool.acquire() as conn:
            await conn.execute(_SCHEMA_SQL)

    def set_cleanup_callback(
        self, callback: Callable[[str], Awaitable[None]]
    ) -> None:
        """Set callback to clean up external resources (e.g., DB vectors)."""
        self._cleanup_callback = callback

    # ----- helpers --------------------------------------------------------

    def _calculate_expires_at(self, from_time: datetime) -> datetime:
        return from_time + timedelta(minutes=self._inactivity_minutes)

    @staticmethod
    def _row_to_session(row: asyncpg.Record) -> Session:
        raw_docs = row["documents"]
        if isinstance(raw_docs, str):
            raw_docs = json.loads(raw_docs)
        documents = [SessionDocument(**d) for d in (raw_docs or [])]
        return Session(
            session_id=str(row["session_id"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            last_activity=row["last_activity"],
            documents=documents,
            queries=[],  # not persisted; query_count is the quota signal
            transcribe_count=row["transcribe_count"],
            query_count=row["query_count"],
            creator_ip=row["creator_ip"],
        )

    @staticmethod
    def _docs_to_jsonb(docs: list[SessionDocument]) -> str:
        return json.dumps(
            [d.model_dump(mode="json") for d in docs],
            default=str,
        )

    # ----- public API -----------------------------------------------------

    async def create(
        self,
        client_id: str | None = None,
        creator_ip: str | None = None,
    ) -> Session:
        """Create a new session.

        Raises SessionRateLimitError if the global or per-IP creation rate
        limit (sliding 1-minute window) is exceeded.
        """
        assert self._pool is not None
        now = datetime.now(timezone.utc)
        expires_at = self._calculate_expires_at(now)
        session_id = str(uuid.uuid4())
        ip = creator_ip or "unknown"

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Per-IP sliding window
                await conn.execute(
                    "INSERT INTO session_create_log (ip) VALUES ($1)",
                    ip,
                )
                ip_count = await conn.fetchval(
                    """
                    SELECT count(*) FROM session_create_log
                    WHERE ip = $1
                      AND created_at > now() - interval '1 minute'
                    """,
                    ip,
                )
                if ip_count > self._max_sessions_per_minute_per_ip:
                    raise SessionRateLimitError(
                        f"Too many sessions from this IP. Limit: "
                        f"{self._max_sessions_per_minute_per_ip} per minute."
                    )

                # Global sliding window (kept for parity with old behavior).
                global_count = await conn.fetchval(
                    """
                    SELECT count(*) FROM session_create_log
                    WHERE created_at > now() - interval '1 minute'
                    """
                )
                if global_count > self._max_sessions_per_minute:
                    raise SessionRateLimitError(
                        f"Too many sessions created. Limit: "
                        f"{self._max_sessions_per_minute} per minute."
                    )

                await conn.execute(
                    """
                    INSERT INTO sessions (
                        session_id, created_at, last_activity,
                        expires_at, documents, creator_ip
                    ) VALUES ($1, $2, $2, $3, '[]'::jsonb, $4)
                    """,
                    uuid.UUID(session_id), now, expires_at, ip,
                )

        return Session(
            session_id=session_id,
            created_at=now,
            expires_at=expires_at,
            last_activity=now,
            documents=[],
            queries=[],
            transcribe_count=0,
            query_count=0,
            creator_ip=ip,
        )

    async def get(self, session_id: str) -> Session | None:
        """Get session by ID; deletes + returns None if expired."""
        assert self._pool is not None
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            return None

        needs_cleanup = False
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sessions WHERE session_id = $1",
                sid,
            )
            if row is None:
                return None
            now = datetime.now(timezone.utc)
            if now > row["expires_at"]:
                await conn.execute(
                    "DELETE FROM sessions WHERE session_id = $1",
                    sid,
                )
                needs_cleanup = True

        if needs_cleanup:
            await self._cleanup_session_data(session_id)
            return None
        return self._row_to_session(row)

    async def touch(self, session_id: str) -> bool:
        assert self._pool is not None
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            return False
        now = datetime.now(timezone.utc)
        expires_at = self._calculate_expires_at(now)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sessions
                SET last_activity = $2, expires_at = $3
                WHERE session_id = $1
                """,
                sid, now, expires_at,
            )
        return result.endswith(" 1")

    async def delete(self, session_id: str) -> bool:
        assert self._pool is not None
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            return False
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM sessions WHERE session_id = $1",
                sid,
            )
        deleted = result.endswith(" 1")
        if deleted:
            await self._cleanup_session_data(session_id)
        return deleted

    async def add_document(
        self, session_id: str, document: SessionDocument
    ) -> bool:
        assert self._pool is not None
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            return False
        now = datetime.now(timezone.utc)
        expires_at = self._calculate_expires_at(now)
        doc_json = json.dumps(document.model_dump(mode="json"), default=str)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sessions
                SET documents = documents || $2::jsonb,
                    last_activity = $3,
                    expires_at = $4
                WHERE session_id = $1
                """,
                sid, doc_json, now, expires_at,
            )
        return result.endswith(" 1")

    async def remove_document(
        self, session_id: str, document_id: str
    ) -> bool:
        assert self._pool is not None
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            return False
        now = datetime.now(timezone.utc)
        expires_at = self._calculate_expires_at(now)
        async with self._pool.acquire() as conn:
            # Filter out the matching document_id from the JSONB array.
            result = await conn.execute(
                """
                UPDATE sessions
                SET documents = COALESCE(
                        (SELECT jsonb_agg(d) FROM jsonb_array_elements(documents) d
                         WHERE d->>'document_id' <> $2),
                        '[]'::jsonb
                    ),
                    last_activity = $3,
                    expires_at = $4
                WHERE session_id = $1
                """,
                sid, document_id, now, expires_at,
            )
        return result.endswith(" 1")

    async def add_query(
        self, session_id: str, query: QueryRecord
    ) -> bool:
        """Bumps query_count + activity. The query record itself is NOT
        persisted (history is intentionally ephemeral in this MVP).
        """
        assert self._pool is not None
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            return False
        now = datetime.now(timezone.utc)
        expires_at = self._calculate_expires_at(now)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sessions
                SET query_count = query_count + 1,
                    last_activity = $2,
                    expires_at = $3
                WHERE session_id = $1
                """,
                sid, now, expires_at,
            )
        return result.endswith(" 1")

    async def increment_query_count(self, session_id: str) -> bool:
        """Alias used by future call sites that don't have a QueryRecord."""
        # Pre-built QueryRecord is required by /query, so we just keep this
        # for symmetry with increment_transcribe_count.
        assert self._pool is not None
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            return False
        now = datetime.now(timezone.utc)
        expires_at = self._calculate_expires_at(now)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sessions
                SET query_count = query_count + 1,
                    last_activity = $2,
                    expires_at = $3
                WHERE session_id = $1
                """,
                sid, now, expires_at,
            )
        return result.endswith(" 1")

    async def increment_transcribe_count(self, session_id: str) -> bool:
        """Bump transcribe_count after a successful Whisper call."""
        assert self._pool is not None
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            return False
        now = datetime.now(timezone.utc)
        expires_at = self._calculate_expires_at(now)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sessions
                SET transcribe_count = transcribe_count + 1,
                    last_activity = $2,
                    expires_at = $3
                WHERE session_id = $1
                """,
                sid, now, expires_at,
            )
        return result.endswith(" 1")

    async def get_queries(self, session_id: str) -> list[QueryRecord]:
        """Query history is no longer persisted. Returns []."""
        return []

    async def cleanup_expired(self) -> int:
        """Remove all sessions past `expires_at`. Returns count removed.

        Also evicts session_create_log rows older than 1 day to keep the
        rate-limit table small.
        """
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "DELETE FROM sessions WHERE expires_at < now() RETURNING session_id"
            )
            await conn.execute(
                "DELETE FROM session_create_log "
                "WHERE created_at < now() - interval '1 day'"
            )
        for r in rows:
            sid = str(r["session_id"])
            logger.info(f"Cleaning up inactive session {sid}")
            await self._cleanup_session_data(sid)
        return len(rows)

    async def _cleanup_session_data(self, session_id: str) -> None:
        if self._cleanup_callback:
            try:
                await self._cleanup_callback(session_id)
            except Exception as e:
                logger.error(f"Error cleaning up session {session_id}: {e}")

    @property
    def active_sessions_count(self) -> int:
        """Best-effort stat. Returns -1 because counting is async-only.

        The /health endpoint should call `get_active_count()` for a real
        number; this sync property is kept for backward compat with code
        paths that don't await.
        """
        return -1

    async def get_active_count(self) -> int:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT count(*) FROM sessions")


# Singleton instance
_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Get the singleton session store instance."""
    global _session_store
    if _session_store is None:
        from config import get_settings
        settings = get_settings()
        _session_store = SessionStore(
            inactivity_minutes=settings.session_inactivity_minutes,
            max_sessions_per_minute=settings.max_sessions_per_minute,
            max_sessions_per_minute_per_ip=settings.max_sessions_per_minute_per_ip,
        )
    return _session_store
