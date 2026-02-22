# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice RAG - A modern voice-enabled Retrieval-Augmented Generation system with:
- **Backend**: FastAPI REST API with multi-tenant session support
- **Frontend**: Next.js + shadcn/ui with real-time audio streaming
- **Database**: PostgreSQL + pgvector (NOT Supabase)
- **Showcase mode**: Rate-limited for portfolio demos

## Project Structure

```
voice_rag/
├── backend/                 # FastAPI backend
│   ├── main.py             # App entry point + lifespan
│   ├── config.py           # Environment variables + rate limits
│   ├── routers/            # API endpoints
│   ├── services/           # Business logic
│   ├── models/             # Pydantic schemas
│   └── utils/              # PDF processing
└── frontend/               # Next.js frontend
    └── src/
        ├── app/            # Pages
        ├── components/     # UI components
        ├── hooks/          # React hooks
        ├── lib/            # API client, audio utils
        └── types/          # TypeScript types
```

## Commands

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Architecture

### Multi-Tenant Session System
- Each user gets unique `session_id` stored in localStorage
- All documents and queries isolated by session
- PostgreSQL queries filter by `session_id`
- Background task cleans expired sessions (5 min inactivity TTL)

### Rate Limits (Showcase)
- **5 queries per session** (configurable via MAX_QUERIES_PER_SESSION)
- **3 documents per session** (configurable via MAX_DOCUMENTS_PER_SESSION)
- **10 sessions per minute** globally (sliding window)

### Data Flow
1. **Upload**: PDF → chunks → FastEmbed → PostgreSQL/pgvector (with session_id)
2. **Query**: question → embedding → pgvector search (filtered) → context
3. **Response**: Processor Agent (gpt-4.1-mini) → static TTS instructions
4. **Audio**: gpt-4o-mini-tts → SSE streaming PCM → Web Audio API playback

### API Endpoints
- `POST /api/session` - Create session (returns quota info)
- `POST /api/session/{id}/documents` - Upload PDF (enforces document limit)
- `POST /api/session/{id}/query` - Submit question (enforces query limit)
- `GET /api/session/{id}/query/{qid}/audio/stream` - SSE audio stream

## Key Dependencies

### Backend
- `fastapi`, `uvicorn`: Web framework
- `openai-agents`: Agent orchestration (single Processor Agent)
- `asyncpg`, `pgvector`: PostgreSQL with vector search
- `fastembed`: Local embeddings (BAAI/bge-small-en-v1.5, 384 dims)
- `langchain-text-splitters`: PDF chunking

### Frontend
- `next`: React framework
- `shadcn/ui`: Component library
- Web Audio API: Real-time audio playback

## Environment Variables

### Backend (.env)
```
OPENAI_API_KEY=...
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/voicerag
SESSION_INACTIVITY_MINUTES=5
MAX_QUERIES_PER_SESSION=5
MAX_DOCUMENTS_PER_SESSION=3
MAX_SESSIONS_PER_MINUTE=10
PROCESSOR_MODEL=gpt-4.1-mini
TTS_MODEL=gpt-4o-mini-tts
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```
