import asyncio
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File

from models.schemas import (
    DocumentUploadResponse,
    DocumentListResponse,
    SessionDocument,
)
from config import get_settings
from services.session_service import SessionStore, get_session_store
from services.vector_service import VectorService, get_vector_service
from services.embedding_service import EmbeddingService, get_embedding_service
from utils.pdf_processor import process_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session/{session_id}", tags=["documents"])


@router.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(
    session_id: str,
    file: UploadFile = File(...),
    session_store: SessionStore = Depends(get_session_store),
    vector_service: VectorService = Depends(get_vector_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """Upload and process a PDF document."""
    # Validate session
    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # Enforce document limit
    settings = get_settings()
    if len(session.documents) >= settings.max_documents_per_session:
        raise HTTPException(
            status_code=429,
            detail=f"Document limit reached ({settings.max_documents_per_session} per session). Restart to create a new session.",
        )

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        # Read file content
        content = await file.read()

        # Validate file size
        settings = get_settings()
        if len(content) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {settings.max_file_size_mb}MB"
            )

        # Validate PDF magic bytes
        if not content[:5].startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="File content does not match PDF format")

        # Process PDF (run in thread to avoid blocking event loop)
        chunks, page_count = await asyncio.to_thread(process_pdf, content, file.filename)

        if not chunks:
            raise HTTPException(status_code=400, detail="No content extracted from PDF")

        # Generate document ID
        document_id = str(uuid.uuid4())

        # Generate embeddings (async to not block event loop)
        texts = [chunk["content"] for chunk in chunks]
        embeddings = await embedding_service.embed(texts)

        # Store in PostgreSQL with pgvector
        chunk_count = await vector_service.store_embeddings(
            session_id=session_id,
            document_id=document_id,
            chunks=chunks,
            embeddings=embeddings,
        )

        # Add document to session
        now = datetime.utcnow()
        doc = SessionDocument(
            document_id=document_id,
            file_name=file.filename,
            page_count=page_count,
            chunk_count=chunk_count,
            processed_at=now,
        )
        await session_store.add_document(session_id, doc)

        return DocumentUploadResponse(
            document_id=document_id,
            file_name=file.filename,
            page_count=page_count,
            chunk_count=chunk_count,
            processed_at=now,
            status="completed",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
):
    """List all documents in a session."""
    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    return DocumentListResponse(documents=session.documents)


@router.delete("/documents/{document_id}")
async def delete_document(
    session_id: str,
    document_id: str,
    session_store: SessionStore = Depends(get_session_store),
    vector_service: VectorService = Depends(get_vector_service),
):
    """Delete a document from the session."""
    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # Remove from PostgreSQL
    await vector_service.delete_document(session_id, document_id)

    # Remove from session
    success = await session_store.remove_document(session_id, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"success": True}
