# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice RAG - A modern voice-enabled Retrieval-Augmented Generation system with:
- **Backend**: FastAPI REST API with multi-tenant session support
- **Frontend**: Next.js + shadcn/ui with real-time audio streaming

## Project Structure

```
voice_rag_openaisdk/
├── backend/                 # FastAPI backend
│   ├── main.py             # App entry point + lifespan
│   ├── config.py           # Environment variables
│   ├── routers/            # API endpoints
│   ├── services/           # Business logic
│   ├── models/             # Pydantic schemas
│   └── utils/              # PDF processing
├── frontend/               # Next.js frontend
│   └── src/
│       ├── app/            # Pages
│       ├── components/     # UI components
│       ├── hooks/          # React hooks
│       ├── lib/            # API client, audio utils
│       └── types/          # TypeScript types
└── rag_voice.py            # Original Streamlit app (reference)
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
- Qdrant queries filter by `session_id` in payload
- Background task cleans expired sessions (24h TTL)

### Data Flow
1. **Upload**: PDF → chunks → FastEmbed → Qdrant (with session_id)
2. **Query**: question → embedding → Qdrant search (filtered) → context
3. **Response**: Processor Agent (GPT-4o) → TTS Agent → gpt-4o-mini-tts
4. **Audio**: SSE streaming PCM → Web Audio API playback

### API Endpoints
- `POST /api/session` - Create session
- `POST /api/session/{id}/documents` - Upload PDF
- `POST /api/session/{id}/query` - Submit question
- `GET /api/session/{id}/query/{qid}/audio/stream` - SSE audio stream

## Key Dependencies

### Backend
- `fastapi`, `uvicorn`: Web framework
- `openai-agents`: Agent orchestration
- `qdrant-client`: Vector database
- `fastembed`: Local embeddings (384 dims)
- `langchain-text-splitters`: PDF chunking

### Frontend
- `next`: React framework
- `shadcn/ui`: Component library
- Web Audio API: Real-time audio playback

## Environment Variables

### Backend (.env)
```
OPENAI_API_KEY=...
QDRANT_URL=...
QDRANT_API_KEY=...
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```
