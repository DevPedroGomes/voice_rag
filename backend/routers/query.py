import asyncio
import json
import logging
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

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
from services.agent_service import AgentService, DEFAULT_TTS_INSTRUCTIONS, get_agent_service
from services.audio_service import AudioService, get_audio_service
from services.grader import grade_documents
from services.reranker import rerank_documents
from services.query_expansion import expand_query
from services.sentence_buffer import split_complete_sentences, flush_remainder

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


async def _retrieve_and_grade(
    *,
    session_id: str,
    query: str,
    settings,
    vector_service: VectorService,
    embedding_service: EmbeddingService,
) -> tuple[list[dict], bool]:
    """Run the full retrieval pipeline (multi-query → hybrid → rerank → grade).

    Shared by /query (sync) and /query/stream (SSE). Returns the graded
    chunks the LLM will see plus the low_confidence flag.

    Raises:
        HTTPException(404) when no results survive retrieval.
    """
    retrieval_limit = (
        settings.search_top_k * settings.search_candidates_multiplier
        if settings.enable_reranker
        else settings.search_top_k
    )

    # Multi-query expansion in parallel with the original embedding.
    original_embed_task = asyncio.create_task(
        embedding_service.embed_single(query)
    )
    if settings.enable_multi_query:
        expansion_task = asyncio.create_task(
            expand_query(
                query,
                api_key=settings.anthropic_api_key,
                model=settings.contextual_model,
                count=settings.multi_query_count,
                max_tokens=settings.multi_query_max_tokens,
            )
        )
    else:
        expansion_task = None

    query_embedding = await original_embed_task
    variants = await expansion_task if expansion_task is not None else []
    all_queries = [query] + variants

    if variants:
        variant_embeddings = await asyncio.gather(
            *[embedding_service.embed_single(v) for v in variants]
        )
        all_embeddings = [query_embedding] + list(variant_embeddings)
    else:
        all_embeddings = [query_embedding]

    if settings.enable_hybrid_search:
        results_per_query = await asyncio.gather(*[
            vector_service.search_hybrid(
                session_id=session_id,
                query_text=q,
                query_embedding=emb,
                limit=retrieval_limit,
                candidates_multiplier=1,
                rrf_k=settings.rrf_k,
            )
            for q, emb in zip(all_queries, all_embeddings)
        ])
        merged: dict[str, dict] = {}
        for results in results_per_query:
            for r in results:
                rid = r.get("id")
                if rid is None:
                    continue
                if rid not in merged or r.get("score", 0.0) > merged[rid].get("score", 0.0):
                    merged[rid] = r
        search_results = sorted(
            merged.values(), key=lambda x: x.get("score", 0.0), reverse=True
        )[:retrieval_limit]
    else:
        search_results = await vector_service.search(
            session_id=session_id,
            query_embedding=query_embedding,
            limit=settings.search_top_k,
        )

    if not search_results:
        raise HTTPException(
            status_code=404,
            detail="No relevant documents found. Please upload documents first.",
        )

    if settings.enable_reranker:
        search_results = await rerank_documents(
            query=query,
            documents=search_results,
            top_n=settings.search_top_k,
            model=settings.cohere_rerank_model,
            api_key=settings.cohere_api_key,
        )

    threshold = (
        settings.relevance_threshold_reranked
        if settings.enable_reranker
        else settings.relevance_threshold
    )
    graded_results, low_confidence = grade_documents(
        documents=search_results,
        threshold=threshold,
    )

    if low_confidence:
        logger.info(
            "query %s: low_confidence=True (graded %d/%d above threshold %.3f, "
            "reranked=%s)",
            session_id,
            len(graded_results),
            len(search_results),
            threshold,
            settings.enable_reranker,
        )

    return graded_results, low_confidence


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

    # Enforce query limit (Onda 3 — query_count is the persisted source of truth)
    settings = get_settings()
    if session.query_count >= settings.max_queries_per_session:
        raise HTTPException(
            status_code=429,
            detail=f"Query limit reached ({settings.max_queries_per_session} per session). Restart to create a new session.",
        )

    try:
        graded_results, low_confidence = await _retrieve_and_grade(
            session_id=session_id,
            query=body.query,
            settings=settings,
            vector_service=vector_service,
            embedding_service=embedding_service,
        )

        # Process query with agents
        text_response, voice_instructions, sources = await agent_service.process_query(
            query=body.query,
            context=graded_results,
            low_confidence=low_confidence,
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

        # Build source info from graded results (only the docs the agent saw).
        source_infos = []
        for result in graded_results:
            source_infos.append(SourceInfo(
                file_name=result.get("file_name", "Unknown"),
                page_number=result.get("page_number"),
                snippet=result.get("content", "")[:200] + "...",
            ))

        # Save query to session history (bumps persisted query_count)
        query_record = QueryRecord(
            query_id=query_id,
            question=body.query,
            response=text_response,
            voice=body.voice,
            sources=sources,
            created_at=datetime.now(timezone.utc),
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
    except Exception:
        # Onda 3 — never leak internal error details to clients.
        logger.exception("Error processing query for session %s", session_id)
        raise HTTPException(status_code=500, detail="Error processing query")


@router.post("/query/stream")
async def submit_query_stream(
    session_id: str,
    body: QueryRequest,
    session_store: SessionStore = Depends(get_session_store),
    vector_service: VectorService = Depends(get_vector_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    agent_service: AgentService = Depends(get_agent_service),
    audio_service: AudioService = Depends(get_audio_service),
):
    """Streaming variant of /query — interleaves text deltas and audio chunks
    on a single SSE stream. Cuts first-audible-word latency dramatically:
    TTS for sentence #1 starts while the LLM is still writing sentence #2.

    SSE event vocabulary:
        event: sources       — once, before any text. data: {sources: [...]}
        event: text_delta    — many. data: {delta: "..."}
        event: audio_chunk   — many. data: {chunk: <base64>, sentence_idx, chunk_idx}
        event: complete      — once, last event. data: {query_id, total_sentences}
        event: error         — terminal failure. data: {error: "..."}

    The frontend can choose to render text deltas live, queue audio_chunk
    bytes into a single Web Audio AudioBufferSourceNode, or both. Audio
    chunks are PCM (same format as /audio/stream), base64-encoded.

    Sentence boundary detection is best-effort (see services/sentence_buffer.py).
    Any text after the last detected boundary is flushed as a final TTS pass.
    """
    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not session.is_ready:
        raise HTTPException(status_code=400, detail="No documents uploaded yet")

    settings = get_settings()
    if session.query_count >= settings.max_queries_per_session:
        raise HTTPException(
            status_code=429,
            detail=f"Query limit reached ({settings.max_queries_per_session} per session). Restart to create a new session.",
        )

    try:
        graded_results, low_confidence = await _retrieve_and_grade(
            session_id=session_id,
            query=body.query,
            settings=settings,
            vector_service=vector_service,
            embedding_service=embedding_service,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error during retrieval for session %s", session_id)
        raise HTTPException(status_code=500, detail="Error processing query")

    sources = agent_service.get_sources_for_query(
        query=body.query, context=graded_results, low_confidence=low_confidence
    )
    query_id = str(uuid.uuid4())

    # Bounded concurrency for TTS fan-out. Voice answers are 2-4 sentences,
    # so this realistically caps at ≤ 4 concurrent TTS calls in steady state
    # — the semaphore exists to prevent a degenerate prompt with many tiny
    # sentences from spawning 50 parallel OpenAI calls.
    tts_semaphore = asyncio.Semaphore(4)

    async def event_generator():
        # Multiplex text + audio onto one stream via a queue. The text
        # producer reads LLM deltas; per detected sentence boundary it
        # spawns a TTS task that pushes audio chunks back into the queue.
        # The main coroutine drains the queue and yields SSE-framed events.
        queue: asyncio.Queue = asyncio.Queue()
        producer_done = asyncio.Event()
        text_buffer: list[str] = [""]  # mutable holder for closure access
        accumulated_text: list[str] = [""]
        sentence_idx_holder = [0]
        tts_tasks: list[asyncio.Task] = []

        try:
            yield (
                "event: sources\n"
                f"data: {json.dumps({'sources': sources})}\n\n"
            )
        except Exception:
            pass  # if the client already disconnected, fall through to cleanup

        async def tts_for_sentence(sentence: str, sentence_idx: int) -> None:
            """Stream PCM chunks for one sentence into the queue.

            Bounded by tts_semaphore to cap concurrent OpenAI calls when the
            LLM emits many short sentences in a burst. Failures are logged
            and surfaced as audio_error events; they never abort the stream.
            """
            async with tts_semaphore:
                try:
                    chunk_idx = 0
                    async for b64chunk in audio_service.stream_tts(
                        text=sentence,
                        voice=body.voice,
                        instructions=DEFAULT_TTS_INSTRUCTIONS,
                    ):
                        await queue.put({
                            "event": "audio_chunk",
                            "data": {
                                "chunk": b64chunk,
                                "sentence_idx": sentence_idx,
                                "chunk_idx": chunk_idx,
                            },
                        })
                        chunk_idx += 1
                except Exception:
                    logger.exception(
                        "tts_for_sentence: failed for sentence %d (query %s)",
                        sentence_idx, query_id,
                    )
                    await queue.put({
                        "event": "audio_error",
                        "data": {"sentence_idx": sentence_idx, "error": "tts_failed"},
                    })

        async def text_producer() -> None:
            """Drive LLM streaming, push text deltas, fan out TTS per sentence."""
            try:
                async for delta in agent_service.stream_response(
                    query=body.query,
                    context=graded_results,
                    low_confidence=low_confidence,
                ):
                    accumulated_text[0] += delta
                    text_buffer[0] += delta
                    await queue.put({
                        "event": "text_delta",
                        "data": {"delta": delta},
                    })

                    sentences, remainder = split_complete_sentences(text_buffer[0])
                    text_buffer[0] = remainder
                    for sentence in sentences:
                        idx = sentence_idx_holder[0]
                        sentence_idx_holder[0] += 1
                        tts_tasks.append(
                            asyncio.create_task(tts_for_sentence(sentence, idx))
                        )

                # LLM done — flush any trailing remainder as the final sentence.
                final = flush_remainder(text_buffer[0])
                if final:
                    idx = sentence_idx_holder[0]
                    sentence_idx_holder[0] += 1
                    tts_tasks.append(
                        asyncio.create_task(tts_for_sentence(final, idx))
                    )
            except Exception:
                logger.exception(
                    "text_producer: failed for session %s query %s",
                    session_id, query_id,
                )
                await queue.put({
                    "event": "error",
                    "data": {"error": "text_stream_failed"},
                })
            finally:
                # Wait for all spawned TTS tasks to drain their chunks before
                # signaling done — otherwise the consumer may exit early and
                # cancel pending audio.
                if tts_tasks:
                    await asyncio.gather(*tts_tasks, return_exceptions=True)
                producer_done.set()

        producer = asyncio.create_task(text_producer())

        # Drain the queue until producer is done AND queue is empty.
        try:
            while not (producer_done.is_set() and queue.empty()):
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                yield (
                    f"event: {event['event']}\n"
                    f"data: {json.dumps(event['data'])}\n\n"
                )

            yield (
                "event: complete\n"
                f"data: {json.dumps({'query_id': query_id, 'total_sentences': sentence_idx_holder[0]})}\n\n"
            )
        finally:
            try:
                await producer  # ensure cancellations propagate cleanly
            except Exception:
                pass

            full_text = accumulated_text[0]

            # Anti-abuse: always bump query_count once we got past the
            # rate-limit check, even when the stream errored or produced
            # empty text. The user consumed retrieval / LLM / partial TTS
            # budget regardless, and gating persistence on success would
            # let them retry a failed stream for free.
            try:
                await session_store.add_query(
                    session_id,
                    QueryRecord(
                        query_id=query_id,
                        question=body.query,
                        response=full_text or "",
                        voice=body.voice,
                        sources=sources,
                        created_at=datetime.now(timezone.utc),
                    ),
                )
            except Exception:
                logger.exception(
                    "submit_query_stream: failed to persist query history"
                )

            # Cache the text only when there's something to TTS — the
            # /audio/stream and /audio/download endpoints look up by
            # query_id, and empty text isn't useful to either.
            if full_text.strip():
                _cleanup_expired_query_results()
                while len(_query_results) >= MAX_QUERY_RESULTS:
                    _query_results.popitem(last=False)
                _query_results[query_id] = {
                    "data": {
                        "text_response": full_text,
                        "voice_instructions": DEFAULT_TTS_INSTRUCTIONS,
                        "voice": body.voice,
                        "session_id": session_id,
                    },
                    "created_at": time.time(),
                }

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
        start_time = asyncio.get_event_loop().time()
        max_duration = 300  # 5 minute hard limit
        try:
            async for chunk in audio_service.stream_tts(
                text=query_data["text_response"],
                voice=query_data["voice"],
                instructions=query_data["voice_instructions"],
            ):
                if asyncio.get_event_loop().time() - start_time > max_duration:
                    logger.warning(f"Audio stream timeout for query {query_id}")
                    break
                data = json.dumps({"chunk": chunk, "index": chunk_index})
                yield f"event: audio_chunk\ndata: {data}\n\n"
                chunk_index += 1

            yield f"event: audio_complete\ndata: {json.dumps({'total_chunks': chunk_index})}\n\n"
        except Exception:
            # Onda 3 — never echo raw exception payload to SSE clients.
            logger.exception(f"Error streaming audio for query {query_id}")
            yield f"event: error\ndata: {json.dumps({'error': 'stream_failed'})}\n\n"
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
    except Exception:
        # Onda 3 — generic external error message; details only in server log.
        logger.exception(f"Error generating audio for query {query_id}")
        raise HTTPException(status_code=500, detail="Error generating audio")
