from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


# ============ Domain Models ============

class SessionDocument(BaseModel):
    document_id: str
    file_name: str
    page_count: int
    chunk_count: int
    processed_at: datetime


class QueryRecord(BaseModel):
    query_id: str
    question: str
    response: str
    voice: str
    sources: list[str]
    created_at: datetime


class Session(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    documents: list[SessionDocument] = Field(default_factory=list)
    queries: list[QueryRecord] = Field(default_factory=list)
    # Onda 3 — counters persisted in Postgres (see services/session_service.py).
    # `queries` list is not persisted across restarts, so query_count is the
    # source of truth for quota enforcement.
    transcribe_count: int = 0
    query_count: int = 0
    creator_ip: str | None = None

    @property
    def is_ready(self) -> bool:
        return len(self.documents) > 0


# ============ Request Models ============

class SessionCreate(BaseModel):
    client_id: str | None = None


VoiceType = Literal[
    "alloy", "ash", "ballad", "coral", "echo",
    "fable", "onyx", "nova", "sage", "shimmer", "verse",
    "marin", "cedar"
]


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    voice: VoiceType = "coral"
    stream_audio: bool = True


# ============ Response Models ============

class SessionResponse(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime
    documents: list[SessionDocument]
    is_ready: bool
    query_count: int = 0
    queries_remaining: int = 5
    documents_remaining: int = 3
    transcribes_remaining: int = 15


class DocumentUploadResponse(BaseModel):
    document_id: str
    file_name: str
    page_count: int
    chunk_count: int
    processed_at: datetime
    status: Literal["processing", "completed", "error"]


class DocumentListResponse(BaseModel):
    documents: list[SessionDocument]


class SourceInfo(BaseModel):
    file_name: str
    page_number: int | None = None
    snippet: str


class QueryResponse(BaseModel):
    query_id: str
    text_response: str
    sources: list[SourceInfo]
    audio_stream_url: str | None = None
    audio_download_url: str | None = None


class QueryHistoryResponse(BaseModel):
    queries: list[QueryRecord]


class VoiceOption(BaseModel):
    id: VoiceType
    name: str
    description: str


class VoicesResponse(BaseModel):
    voices: list[VoiceOption]


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    database_connected: bool


# ============ Sprint 3.1 — STT ============

class TranscriptionResponse(BaseModel):
    """Response from POST /api/session/{id}/transcribe.

    `text` is the recognized utterance, ready to be passed back into
    /query as `body.query`. `language` is Whisper's detected ISO-639-1
    code (None when a language hint was supplied).
    """
    text: str
    language: str | None = None
    duration_ms: int | None = None
