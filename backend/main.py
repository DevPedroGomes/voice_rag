import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import session_router, documents_router, query_router
from routers.query import periodic_cleanup_query_results
from services.session_service import get_session_store
from services.vector_service import get_vector_service
from services.embedding_service import get_embedding_service
from services.agent_service import get_agent_service
from services.audio_service import get_audio_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def cleanup_expired_sessions():
    """Background task to periodically clean up expired sessions."""
    settings = get_settings()
    session_store = get_session_store()
    interval = settings.cleanup_interval_minutes * 60
    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        await asyncio.sleep(interval)
        try:
            removed = await session_store.cleanup_expired()
            if removed > 0:
                logger.info(f"Cleaned up {removed} expired sessions")
            consecutive_errors = 0  # Reset on success
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error during session cleanup (attempt {consecutive_errors}): {e}")
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(
                    f"Session cleanup failed {max_consecutive_errors} times consecutively. "
                    "Manual intervention may be required."
                )
                consecutive_errors = 0  # Reset but keep running


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    settings = get_settings()

    # Initialize vector service (PostgreSQL + pgvector)
    vector_service = get_vector_service()
    await vector_service.initialize(settings.database_url)

    # Initialize session store and set up cleanup callback
    session_store = get_session_store()

    async def cleanup_session_data(session_id: str):
        await vector_service.delete_session_data(session_id)

    session_store.set_cleanup_callback(cleanup_session_data)

    # Eagerly initialize services to avoid cold start on first request
    logger.info("Pre-loading embedding model (ONNX)...")
    await asyncio.to_thread(get_embedding_service)
    logger.info("Embedding model loaded")

    logger.info("Initializing agent service...")
    get_agent_service()
    logger.info("Agent service ready")

    logger.info("Initializing audio service...")
    get_audio_service()
    logger.info("Audio service ready")

    # Start background cleanup tasks
    cleanup_task = asyncio.create_task(cleanup_expired_sessions())
    query_cleanup_task = asyncio.create_task(periodic_cleanup_query_results())

    logger.info("Voice RAG API started")
    logger.info(f"Session inactivity timeout: {settings.session_inactivity_minutes} minutes")
    logger.info(f"Cleanup interval: {settings.cleanup_interval_minutes} minute(s)")

    yield

    # Shutdown
    logger.info("Shutting down Voice RAG API...")
    cleanup_task.cancel()
    query_cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await query_cleanup_task
    except asyncio.CancelledError:
        pass
    await vector_service.close()
    logger.info("Voice RAG API stopped")


app = FastAPI(
    title="Voice RAG API",
    description="Voice-enabled Retrieval-Augmented Generation API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(session_router)
app.include_router(documents_router)
app.include_router(query_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Voice RAG API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    session_store = get_session_store()
    vector_service = get_vector_service()
    db_healthy = await vector_service.health_check()
    return {
        "status": "healthy" if db_healthy else "degraded",
        "active_sessions": session_store.active_sessions_count,
        "database": "connected" if db_healthy else "disconnected",
    }
