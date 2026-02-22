from fastapi import APIRouter, HTTPException, Depends

from config import get_settings
from models.schemas import (
    SessionCreate,
    SessionResponse,
    VoiceOption,
    VoicesResponse,
    HealthResponse,
)
from services.session_service import SessionStore, get_session_store
from services.vector_service import VectorService, get_vector_service

router = APIRouter(prefix="/api", tags=["session"])


AVAILABLE_VOICES: list[VoiceOption] = [
    VoiceOption(id="alloy", name="Alloy", description="Neutral and balanced"),
    VoiceOption(id="ash", name="Ash", description="Soft and gentle"),
    VoiceOption(id="ballad", name="Ballad", description="Warm and expressive"),
    VoiceOption(id="coral", name="Coral", description="Clear and friendly"),
    VoiceOption(id="echo", name="Echo", description="Smooth and calm"),
    VoiceOption(id="fable", name="Fable", description="Warm and narrative"),
    VoiceOption(id="onyx", name="Onyx", description="Deep and authoritative"),
    VoiceOption(id="nova", name="Nova", description="Energetic and bright"),
    VoiceOption(id="sage", name="Sage", description="Wise and measured"),
    VoiceOption(id="shimmer", name="Shimmer", description="Light and airy"),
    VoiceOption(id="verse", name="Verse", description="Poetic and melodic"),
    VoiceOption(id="marin", name="Marin", description="Confident and engaging"),
    VoiceOption(id="cedar", name="Cedar", description="Grounded and steady"),
]


@router.post("/session", response_model=SessionResponse)
async def create_session(
    body: SessionCreate | None = None,
    session_store: SessionStore = Depends(get_session_store),
):
    """Create a new user session."""
    client_id = body.client_id if body else None
    try:
        session = await session_store.create(client_id=client_id)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    settings = get_settings()
    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        documents=session.documents,
        is_ready=session.is_ready,
        query_count=len(session.queries),
        queries_remaining=settings.max_queries_per_session - len(session.queries),
        documents_remaining=settings.max_documents_per_session - len(session.documents),
    )


@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
):
    """Get session information and documents."""
    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    settings = get_settings()
    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        documents=session.documents,
        is_ready=session.is_ready,
        query_count=len(session.queries),
        queries_remaining=settings.max_queries_per_session - len(session.queries),
        documents_remaining=settings.max_documents_per_session - len(session.documents),
    )


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
):
    """Delete a session and all associated data."""
    success = await session_store.delete(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


@router.get("/voices", response_model=VoicesResponse)
async def get_voices():
    """Get available TTS voices."""
    return VoicesResponse(voices=AVAILABLE_VOICES)


@router.get("/health", response_model=HealthResponse)
async def health_check(
    vector_service: VectorService = Depends(get_vector_service),
):
    """Health check endpoint."""
    db_healthy = await vector_service.health_check()
    return HealthResponse(
        status="healthy" if db_healthy else "unhealthy",
        database_connected=db_healthy,
    )
