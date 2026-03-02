import json
import logging
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse

from models.schemas import (
    QueryRequest,
    QueryResponse,
    QueryHistoryResponse,
    QueryRecord,
    SourceInfo,
)
from config import get_settings
from services.session_service import SessionStore, get_session_store
from services.vector_service import VectorService, get_vector_service
from services.embedding_service import EmbeddingService, get_embedding_service
from services.agent_service import AgentService, get_agent_service
from services.audio_service import AudioService, get_audio_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session/{session_id}", tags=["query"])

# In-memory storage for query results with TTL (for audio streaming)
# Structure: {query_id: {"data": {...}, "created_at": timestamp}}
_query_results: OrderedDict[str, dict] = OrderedDict()
QUERY_RESULT_TTL_SECONDS = 300  # 5 minutes (audio is consumed immediately)
MAX_QUERY_RESULTS = 100


def _cleanup_expired_query_results() -> int:
    """Remove query results older than TTL. Returns count of removed entries."""
    now = time.time()
    expired = [
        qid for qid, entry in _query_results.items()
        if now - entry.get("created_at", 0) > QUERY_RESULT_TTL_SECONDS
    ]
    for qid in expired:
        del _query_results[qid]
    return len(expired)


def _remove_query_result(query_id: str) -> None:
    """Remove a specific query result after use."""
    _query_results.pop(query_id, None)


@router.post("/query", response_model=QueryResponse)
async def submit_query(
    session_id: str,
    body: QueryRequest,
    session_store: SessionStore = Depends(get_session_store),
    vector_service: VectorService = Depends(get_vector_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    agent_service: AgentService = Depends(get_agent_service),
):
    """Submit a query and get a text response with audio URLs."""
    # Validate session
    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not session.is_ready:
        raise HTTPException(status_code=400, detail="No documents uploaded yet")

    # Enforce query limit
    settings = get_settings()
    if len(session.queries) >= settings.max_queries_per_session:
        raise HTTPException(
            status_code=429,
            detail=f"Query limit reached ({settings.max_queries_per_session} per session). Restart to create a new session.",
        )

    try:
        # Generate query embedding (async to not block event loop)
        query_embedding = await embedding_service.embed_single(body.query)

        # Search for relevant documents in PostgreSQL
        search_results = await vector_service.search(
            session_id=session_id,
            query_embedding=query_embedding,
            limit=3,
        )

        if not search_results:
            raise HTTPException(
                status_code=404,
                detail="No relevant documents found. Please upload documents first.",
            )

        # Process query with agents
        text_response, voice_instructions, sources = await agent_service.process_query(
            query=body.query,
            context=search_results,
        )

        # Generate query ID
        query_id = str(uuid.uuid4())

        # Cleanup expired results periodically
        _cleanup_expired_query_results()

        # Evict oldest entry if at capacity
        while len(_query_results) >= MAX_QUERY_RESULTS:
            _query_results.popitem(last=False)

        # Store query result for audio streaming with timestamp
        _query_results[query_id] = {
            "data": {
                "text_response": text_response,
                "voice_instructions": voice_instructions,
                "voice": body.voice,
                "session_id": session_id,
            },
            "created_at": time.time(),
        }

        # Build source info
        source_infos = []
        for result in search_results:
            source_infos.append(SourceInfo(
                file_name=result.get("file_name", "Unknown"),
                page_number=result.get("page_number"),
                snippet=result.get("content", "")[:200] + "...",
            ))

        # Save query to session history
        query_record = QueryRecord(
            query_id=query_id,
            question=body.query,
            response=text_response,
            voice=body.voice,
            sources=sources,
            created_at=datetime.utcnow(),
        )
        await session_store.add_query(session_id, query_record)

        return QueryResponse(
            query_id=query_id,
            text_response=text_response,
            sources=source_infos,
            audio_stream_url=f"/api/session/{session_id}/query/{query_id}/audio/stream" if body.stream_audio else None,
            audio_download_url=f"/api/session/{session_id}/query/{query_id}/audio/download",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


@router.get("/queries", response_model=QueryHistoryResponse)
async def get_query_history(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
):
    """Get query history for a session."""
    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    queries = await session_store.get_queries(session_id)
    return QueryHistoryResponse(queries=queries)


@router.get("/query/{query_id}/audio/stream")
async def stream_audio(
    session_id: str,
    query_id: str,
    audio_service: AudioService = Depends(get_audio_service),
):
    """Stream audio as Server-Sent Events."""
    query_entry = _query_results.get(query_id)
    if query_entry is None:
        raise HTTPException(status_code=404, detail="Query not found or expired")

    query_data = query_entry.get("data", {})
    if query_data.get("session_id") != session_id:
        raise HTTPException(status_code=403, detail="Query belongs to different session")

    async def event_generator():
        chunk_index = 0
        try:
            async for chunk in audio_service.stream_tts(
                text=query_data["text_response"],
                voice=query_data["voice"],
                instructions=query_data["voice_instructions"],
            ):
                data = json.dumps({"chunk": chunk, "index": chunk_index})
                yield f"event: audio_chunk\ndata: {data}\n\n"
                chunk_index += 1

            yield f"event: audio_complete\ndata: {json.dumps({'total_chunks': chunk_index})}\n\n"
        except Exception as e:
            logger.error(f"Error streaming audio for query {query_id}: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Clean up query result after streaming completes
            _remove_query_result(query_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def periodic_cleanup_query_results() -> None:
    """Background task to periodically clean up expired query results."""
    import asyncio
    while True:
        await asyncio.sleep(60)
        try:
            removed = _cleanup_expired_query_results()
            if removed > 0:
                logger.info(f"Cleaned up {removed} expired query results")
        except Exception as e:
            logger.error(f"Error during query results cleanup: {e}")


def _cleanup_temp_file(file_path: str) -> None:
    """Remove temporary file after download."""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        logger.warning(f"Failed to cleanup temp file {file_path}: {e}")


@router.get("/query/{query_id}/audio/download")
async def download_audio(
    session_id: str,
    query_id: str,
    background_tasks: BackgroundTasks,
    audio_service: AudioService = Depends(get_audio_service),
):
    """Download audio as MP3 file."""
    query_entry = _query_results.get(query_id)
    if query_entry is None:
        raise HTTPException(status_code=404, detail="Query not found or expired")

    query_data = query_entry.get("data", {})
    if query_data.get("session_id") != session_id:
        raise HTTPException(status_code=403, detail="Query belongs to different session")

    try:
        file_path = await audio_service.generate_mp3(
            text=query_data["text_response"],
            voice=query_data["voice"],
            instructions=query_data["voice_instructions"],
        )

        # Schedule cleanup of temp file after response is sent
        background_tasks.add_task(_cleanup_temp_file, file_path)

        return FileResponse(
            path=file_path,
            media_type="audio/mpeg",
            filename=f"response_{query_id}.mp3",
        )
    except Exception as e:
        logger.error(f"Error generating audio for query {query_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating audio: {str(e)}")
