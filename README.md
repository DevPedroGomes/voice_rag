# Voice RAG

A voice-enabled Retrieval-Augmented Generation system. Upload PDF documents, ask questions, and receive spoken answers.

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15, React 19, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Python 3.12, OpenAI Agents SDK |
| Database | PostgreSQL with pgvector extension |
| Embeddings | FastEmbed (BAAI/bge-small-en-v1.5, 384 dimensions) |
| LLM | GPT-4o via OpenAI API |
| TTS | OpenAI gpt-4o-mini-tts |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Frontend                                    │
│                         (Next.js + React)                               │
├─────────────────────────────────────────────────────────────────────────┤
│  PDF Upload  │  Query Input  │  Audio Player  │  Session Management     │
└──────┬───────┴───────┬───────┴───────┬────────┴──────────┬──────────────┘
       │               │               │                   │
       ▼               ▼               ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           REST API Layer                                 │
│                             (FastAPI)                                    │
├──────────────┬───────────────┬────────────────┬─────────────────────────┤
│ /documents   │   /query      │  /audio/stream │    /session             │
└──────┬───────┴───────┬───────┴────────┬───────┴──────────┬──────────────┘
       │               │                │                  │
       ▼               ▼                ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Service Layer                                   │
├──────────────┬───────────────┬────────────────┬─────────────────────────┤
│ PDF Parser   │  RAG Agent    │  TTS Service   │  Session Store          │
│ (PyMuPDF)    │  (OpenAI SDK) │  (OpenAI TTS)  │  (In-Memory + TTL)      │
└──────┬───────┴───────┬───────┴────────────────┴─────────────────────────┘
       │               │
       ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        PostgreSQL + pgvector                             │
│              (Vector storage with cosine similarity search)              │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
1. UPLOAD FLOW
   User uploads PDF
        │
        ▼
   Extract text (PyMuPDF)
        │
        ▼
   Split into chunks (1000 chars, 200 overlap)
        │
        ▼
   Generate embeddings (FastEmbed)
        │
        ▼
   Store in PostgreSQL with session_id

2. QUERY FLOW
   User submits question
        │
        ▼
   Generate query embedding
        │
        ▼
   Vector similarity search (top 3 chunks)
        │
        ▼
   Build context from retrieved chunks
        │
        ▼
   Processor Agent (GPT-4o) generates answer
        │
        ▼
   TTS Agent optimizes text for speech
        │
        ▼
   OpenAI TTS converts to audio
        │
        ▼
   SSE stream to frontend → Web Audio API playback
```

## Backend Implementation

The backend is a FastAPI application with the following structure:

- **Routers**: Handle HTTP endpoints for sessions, documents, and queries
- **Services**: Business logic layer with dedicated services for:
  - `SessionService`: In-memory session management with 5-minute inactivity timeout
  - `VectorService`: PostgreSQL/pgvector operations for embedding storage and retrieval
  - `EmbeddingService`: Local embedding generation using FastEmbed
  - `AgentService`: OpenAI Agents SDK for RAG processing
  - `AudioService`: Text-to-speech generation

Multi-tenancy is achieved through session IDs. Each user gets a unique session, and all documents and queries are isolated by session_id in the database.

## Frontend Implementation

The frontend is a Next.js application with:

- **Components**: Modular UI built with shadcn/ui (Button, Card, Input, etc.)
- **Hooks**: Custom React hooks for state management:
  - `useSession`: Session lifecycle and document state
  - `useDocuments`: PDF upload and deletion
  - `useQuery`: Question submission and response handling
  - `useAudioStream`: Real-time audio playback with pause/resume
- **Audio**: Web Audio API for streaming PCM audio from SSE endpoint

## Integration

Frontend and backend communicate via REST API:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/session` | POST | Create new session |
| `/api/session/{id}` | GET | Get session status and documents |
| `/api/session/{id}/documents` | POST | Upload PDF |
| `/api/session/{id}/query` | POST | Submit question |
| `/api/session/{id}/query/{qid}/audio/stream` | GET | SSE audio stream |

CORS is configured to allow frontend origin. Session cleanup runs every minute, removing sessions inactive for 5+ minutes.

## Local Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY and DATABASE_URL

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install

# Configure environment
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev
```

### Database Setup

Requires PostgreSQL with pgvector extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Environment Variables

### Backend
- `OPENAI_API_KEY`: OpenAI API key
- `DATABASE_URL`: PostgreSQL connection string
- `CORS_ORIGINS`: Allowed frontend origins (JSON array)
- `SESSION_INACTIVITY_MINUTES`: Session timeout (default: 5)

### Frontend
- `NEXT_PUBLIC_API_URL`: Backend API URL

## Deployment

The application is designed for deployment on Railway with:
- PostgreSQL service (with pgvector)
- Backend service (Docker)
- Frontend service (Docker)

See `backend/Dockerfile` and `frontend/Dockerfile` for container configuration.
