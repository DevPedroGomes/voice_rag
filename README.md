# Voice RAG

A voice-enabled Retrieval-Augmented Generation system. Upload PDF documents, ask questions by typing or by speaking into the microphone, and receive grounded answers streamed back as speech in real time. The full voice loop is implemented end-to-end: browser microphone capture, server-side speech-to-text, hybrid retrieval with cross-encoder reranking and multi-query expansion, contextual chunk enrichment, a voice-tuned LLM, and PCM audio streamed over Server-Sent Events directly into the Web Audio API.

Live deployment: https://voicerag.pgdev.com.br

---

## Overview

Three Docker services orchestrated with Compose behind Traefik:

- `voicerag-db` — PostgreSQL 17 with the `pgvector` extension. Stores chunk embeddings, sessions, the per-IP rate-limit log, and the TTS audio cache.
- `voicerag-backend` — FastAPI app exposing session, document, query, transcription, and streaming endpoints. Owns embeddings, retrieval, the OpenAI Agents-SDK processor, Whisper STT, gpt-4o-mini-tts streaming, and the new sentence-pipelined streaming endpoint.
- `voicerag-frontend` — Next.js 16 / React 19 app with a Web Audio API streaming player and a `MediaRecorder`-based microphone recorder. Marketing landing at `/`, the interactive app at `/app`.

Multi-tenancy is session-scoped: each browser gets a UUID stored in `localStorage`, every Postgres row carries that `session_id`, and a background task evicts inactive sessions together with their vectors. Embeddings run locally in the backend via FastEmbed (ONNX), so document ingestion does not require an external embedding API key.

## Architecture

```mermaid
flowchart TD
    %% ── Document ingestion path ────────────────────────────────────────
    subgraph INGEST["Document ingestion"]
        U1[User uploads PDF] --> R1[POST /api/session/&#123;id&#125;/documents]
        R1 --> P1[PyPDFLoader extracts page text]
        P1 --> P2["semantic_chunk_text<br/>(token-aware, sentence boundaries,<br/>~400 tok / 80 tok overlap, PT/EN)"]
        P2 --> P25{"ANTHROPIC_API_KEY<br/>set?"}
        P25 -->|yes| P26["Contextual Retrieval<br/>(Claude Haiku + prompt caching)<br/>2-3 sentences of doc context<br/>prepended per chunk"]
        P25 -->|no| P3
        P26 --> P3
        P3["FastEmbed<br/>BAAI/bge-small-en-v1.5<br/>384-dim, local ONNX"]
        P3 --> P4["pgvector + tsvector<br/>(HNSW + GIN, scoped by session_id)"]
    end

    %% ── Query path (sync /query) ──────────────────────────────────────
    subgraph QUERY["Query path"]
        Q1[User question] --> Q2{"ANTHROPIC_API_KEY<br/>set?"}
        Q2 -->|yes| Q2a["Multi-query expansion<br/>(Haiku → 3 variants,<br/>parallel with embed)"]
        Q2 -->|no| Q2b[Single query]
        Q2a --> Q3
        Q2b --> Q3
        Q3["FastEmbed query embeddings<br/>(LRU+TTL cache)"] --> Q4
        Q4["asyncio.gather<br/>hybrid_search per query"] --> Q5
        Q5["Merge by chunk id<br/>(best score wins)"] --> Q6
        Q6["Cohere rerank-v3.5<br/>(graceful degrade to RRF)"] --> Q7
        Q7["Score-threshold grader<br/>+ low_confidence flag"] --> Q8
        Q8["Processor Agent<br/>(gpt-4.1-mini or OpenRouter)"] --> Q9
        Q9[Text response] --> A1
    end

    %% ── Voice query path (POST /query/stream) ─────────────────────────
    subgraph VOICE["Streaming voice loop (/query/stream)"]
        M1[Browser microphone] -->|MediaRecorder| T1[Whisper STT]
        T1 --> Q1S[user query string]
        Q1S --> S1["Same retrieval pipeline<br/>(multi-query → hybrid → rerank → grade)"]
        S1 --> S2["agent_service.stream_response<br/>(AsyncOpenAI chat.completions stream=True)"]
        S2 --> S3["sentence_buffer.split_complete_sentences"]
        S3 --> S4{"sentence ready?"}
        S4 -->|yes| S5["Spawn TTS task<br/>(asyncio.Semaphore(4))"]
        S5 --> S6["gpt-4o-mini-tts streaming PCM"]
        S4 -->|no| S2
        S6 --> SSE["SSE: text_delta + audio_chunk<br/>interleaved on one stream"]
        S2 --> SSE
        SSE --> A1
    end

    %% ── Audio playback ────────────────────────────────────────────────
    subgraph AUDIO["Audio playback"]
        A1[Browser receives PCM chunks] --> A2[Web Audio API AudioBufferSource]
        A2 --> A3[Speaker]
    end

    classDef ingest fill:#e0f2fe,stroke:#0284c7
    classDef query fill:#dcfce7,stroke:#16a34a
    classDef voice fill:#fef3c7,stroke:#d97706
    classDef audio fill:#fce7f3,stroke:#db2777
    class U1,R1,P1,P2,P25,P26,P3,P4,Q2 ingest
    class Q1,Q2a,Q2b,Q3,Q4,Q5,Q6,Q7,Q8,Q9 query
    class M1,T1,Q1S,S1,S2,S3,S4,S5,S6,SSE voice
    class A1,A2,A3 audio
```

## Advanced RAG techniques (state in May 2026)

| Technique | Status | Implementation |
|---|---|---|
| **Hybrid search** (vector + keyword + RRF) | active | Single PostgreSQL CTE round-trip — semantic (pgvector HNSW cosine) and keyword (tsvector GIN with `ts_rank_cd`) rankings fused via Reciprocal Rank Fusion (k=60). One DB call instead of two. |
| **Cross-encoder reranking** | active | Cohere `rerank-v3.5`. Graceful degradation to RRF order when `COHERE_API_KEY` is missing or the call fails. |
| **Contextual Retrieval** (Anthropic, 2024) | active | Claude Haiku enriches each chunk with 2-3 sentences of document-level context before embedding. **Prompt caching** (`cache_control: ephemeral`) on the document so chunks 2..N pay ~10% on the cached document tokens. Async with bounded concurrency (`asyncio.Semaphore(5)`) — a 20-chunk PDF stays under ~3s of additional ingest latency. |
| **Multi-query expansion** | active | Haiku generates 3 paraphrasings of the user query. The expansion call runs in parallel with the original query's embedding (`asyncio.create_task`); variant embeddings are computed via `asyncio.gather`; hybrid searches fan out via `asyncio.gather` so the four queries don't serialize on the database. Results merged by chunk id (best score wins) before reranking. |
| **Score-based grader** | active | RRF or Cohere relevance scores compared against tier-specific thresholds. Safety net keeps top-2 when everything is filtered out, plus a `low_confidence` flag the LLM is told about so it acknowledges uncertainty in voice. No LLM call. |
| **Sentence-pipelined TTS** | active | The streaming endpoint detects sentence boundaries on the LLM's text deltas and spawns per-sentence TTS tasks via `asyncio.Semaphore(4)`. Audio for sentence #1 starts while the LLM is still writing sentence #2 — first-audible-word drops from ~1500 ms to ~600 ms. |
| **Voice-mode prompting** | active | System prompt is voice-tuned: short answers, no markdown, no URLs read aloud, language matching. Untrusted retrieved chunks wrapped in `<document source="…">` tags with `</document>` escape neutralization (prompt-injection mitigation). |
| **TTS cache** | active | PostgreSQL BYTEA cache keyed by `(model, voice, text)` so identical answers don't re-synthesize. 24h TTL by default. |

Each LLM-using technique gracefully degrades when its API key is missing — voice_rag still boots and answers questions without `ANTHROPIC_API_KEY` or `COHERE_API_KEY`, just with reduced retrieval precision.

## Endpoints

```
POST   /api/session                                  Create session, returns quota info
POST   /api/session/{id}/documents                   Upload PDF (runs Contextual Retrieval enrichment when key present)
DELETE /api/session/{id}/documents/{document_id}     Remove a document and its embeddings
POST   /api/session/{id}/transcribe                  Whisper STT for audio blob
POST   /api/session/{id}/query                       Sync — JSON response + audio_stream_url
POST   /api/session/{id}/query/stream                SSE — interleaved text_delta + audio_chunk events
GET    /api/session/{id}/queries                     Query history
GET    /api/session/{id}/query/{qid}/audio/stream    SSE PCM audio (used by /query path)
GET    /api/session/{id}/query/{qid}/audio/download  MP3 download
GET    /health                                       Health probe
```

### `/query/stream` SSE event vocabulary

| event | when | data shape |
|---|---|---|
| `sources` | once, before any text | `{sources: [filename, ...]}` |
| `text_delta` | many | `{delta: "..."}` |
| `audio_chunk` | many, interleaved with text_delta | `{chunk: <base64 PCM>, sentence_idx, chunk_idx}` |
| `audio_error` | per-sentence TTS failure (non-fatal) | `{sentence_idx, error}` |
| `complete` | once, last event | `{query_id, total_sentences}` |
| `error` | terminal failure | `{error: "..."}` |

Audio chunks are PCM (same format as `/audio/stream`), base64-encoded. The frontend can render text deltas live, queue audio_chunk bytes into a single Web Audio AudioBufferSourceNode, or both.

## Stack

**Backend** — FastAPI 0.115, asyncpg, pgvector, FastEmbed (ONNX, BAAI/bge-small-en-v1.5), Anthropic SDK (>=0.40, async), Cohere SDK (>=5.13), OpenAI Agents SDK, OpenAI client (TTS + Whisper + chat completions), in-memory rate limiting per IP and per session, `python-multipart`.

**Frontend** — Next.js 16, React 19, Tailwind v4, shadcn/ui, MediaRecorder + Web Audio API for the voice loop.

**Database** — PostgreSQL 17 with pgvector (HNSW vector index, GIN tsvector index, generated `search_vector` column).

**Infrastructure** — Docker Compose, Traefik v3 (TLS via Let's Encrypt, HSTS, security headers, request size limits, internal Docker network so the backend is never publicly addressable), in-memory + PostgreSQL caches, hardened multi-stage Dockerfiles running as non-root.

## Showcase rate limits

```
MAX_QUERIES_PER_SESSION        = 5
MAX_DOCUMENTS_PER_SESSION      = 3
MAX_TRANSCRIBES_PER_SESSION    = 15
MAX_SESSIONS_PER_MINUTE        = 10
MAX_SESSIONS_PER_MINUTE_PER_IP = 10
SESSION_INACTIVITY_MINUTES     = 5
```

Sessions auto-expire after 5 minutes of inactivity; expired sessions and their vectors are evicted by a background task running every 1 minute.

## Local development

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Required env vars (backend `.env`):

```env
OPENAI_API_KEY=sk-...                                      # required (TTS + Whisper, optionally Agents)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/voicerag

# Optional — each missing key disables one technique gracefully
ANTHROPIC_API_KEY=sk-ant-...                               # Contextual Retrieval + Multi-query
COHERE_API_KEY=...                                         # Cross-encoder reranker
OPENROUTER_API_KEY=sk-or-v1-...                            # Use OpenRouter as the RAG processor LLM

LLM_PROVIDER=openai                                        # or "openrouter"
LLM_MODEL=deepseek/deepseek-chat                           # OpenRouter model id when provider=openrouter
PROCESSOR_MODEL=gpt-4.1-mini                               # OpenAI direct model id
TTS_MODEL=gpt-4o-mini-tts
WHISPER_MODEL=whisper-1
```

## License

MIT.
