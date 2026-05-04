# Voice RAG

A voice-enabled Retrieval-Augmented Generation system. Upload PDF documents, ask questions by typing or by speaking into the microphone, and receive grounded answers streamed back as speech in real time.

The full voice loop is implemented end-to-end: browser microphone capture, server-side speech-to-text, hybrid retrieval with cross-encoder reranking, a voice-tuned LLM, and PCM audio streamed over Server-Sent Events directly into the Web Audio API.

## Overview

Three Docker services orchestrated with Compose behind Traefik:

- `voicerag-db` -- PostgreSQL 17 with the `pgvector` extension. Stores chunk embeddings, sessions, the per-IP rate-limit log, and the TTS audio cache.
- `voicerag-backend` -- FastAPI app exposing session, document, query, and transcription endpoints. Owns embeddings, retrieval, the OpenAI Agents-SDK processor, Whisper STT, and gpt-4o-mini-tts streaming.
- `voicerag-frontend` -- Next.js 16 / React 19 app with a Web Audio API streaming player and a `MediaRecorder`-based microphone recorder.

Multi-tenancy is session-scoped: each browser gets a UUID stored in `localStorage`, every Postgres row carries that `session_id`, and a background task evicts inactive sessions together with their vectors. Embeddings run locally in the backend via FastEmbed (ONNX), so document ingestion does not call any external embedding API.

## Architecture

```mermaid
flowchart TD
    %% ── Document ingestion path ────────────────────────────────────────
    subgraph INGEST["Document ingestion"]
        U1[User uploads PDF] --> R1[POST /api/session/&#123;id&#125;/documents]
        R1 --> P1[PyPDFLoader extracts page text]
        P1 --> P2["semantic_chunk_text<br/>(token-aware, sentence boundaries,<br/>~400 tok / 80 tok overlap, PT/EN)"]
        P2 --> P3["FastEmbed<br/>BAAI/bge-small-en-v1.5<br/>384-dim, local ONNX"]
        P3 --> P4["pgvector + tsvector<br/>(HNSW + GIN, scoped by session_id)"]
    end

    %% ── Voice query path ──────────────────────────────────────────────
    subgraph VOICE["Voice loop"]
        M1[Browser microphone] -->|MediaRecorder<br/>webm-opus or mp4-aac| M2[useAudioRecorder hook]
        M2 -->|multipart blob| T1[POST /api/session/&#123;id&#125;/transcribe]
        T1 --> T2{enable_stt?}
        T2 -->|no| T3[503]
        T2 -->|yes| T4["Whisper-1<br/>verbose_json + lang hint"]
        T4 --> T5[transcribe_count++<br/>quota: 15/session]
        T5 --> Q1[Textarea pre-filled<br/>user can edit]
        Q1 --> Q2[POST /api/session/&#123;id&#125;/query]

        Q2 --> EC{embedding<br/>cache hit?}
        EC -->|yes| HS
        EC -->|no| FE[FastEmbed query embedding]
        FE --> EC2[cache.set]
        EC2 --> HS

        HS["search_hybrid<br/>pgvector cosine + tsvector<br/>fused via RRF (k=60)<br/>top_k * multiplier candidates"]
        HS --> RR{enable_reranker?}
        RR -->|yes| RR1["Cohere rerank-v3.5<br/>cross-encoder, fails open"]
        RR -->|no| GR
        RR1 --> GR

        GR["grader<br/>threshold 0.30 (Cohere)<br/>or 0.01 (raw RRF)<br/>safety net top-2"]
        GR --> AG["Processor Agent<br/>gpt-4.1-mini (OpenAI)<br/>or OpenRouter LLM<br/>VOICE_INSTRUCTIONS<br/>max_tokens=220, ctx cap 6000 chars"]
        AG --> RESP[QueryResponse: text + sources]
        AG --> CACHE_KEY[query_id → in-memory result]

        RESP --> SSE[GET /api/session/&#123;id&#125;/query/&#123;qid&#125;/audio/stream]
        SSE --> TC{TTS cache hit?<br/>SHA256 model+voice+text}
        TC -->|hit, MP3 path only| AP
        TC -->|miss / streaming PCM| TTS["gpt-4o-mini-tts<br/>streaming PCM, 24 kHz"]
        TTS --> SSE2["SSE: base64 PCM chunks<br/>event: audio_chunk"]
        SSE2 --> AP["Web Audio API<br/>AudioStreamPlayer<br/>scheduled buffer playback"]
        AP --> SPK[Browser speakers]
    end

    P4 -.session_id filter.-> HS
```

## Voice loop

The full round trip from spoken question to spoken answer:

1. **Capture.** `useAudioRecorder` opens `getUserMedia` (mono, 16 kHz, EC/NS/AGC on) and a `MediaRecorder` with the first supported MIME (`audio/webm;codecs=opus` on Chromium, `audio/mp4;codecs=mp4a.40.2` on Safari). A live peak meter is driven by an `AnalyserNode`. Hard cap: 60 s.
2. **STT.** The blob is posted as multipart to `POST /api/session/{id}/transcribe`. `transcription_service.py` validates extension and size (24 MB cap, below Whisper's 25 MB), forwards to Whisper-1 with optional ISO-639-1 language hint, and returns `{text, language, duration_ms}`. Successful transcriptions bump `transcribe_count` (quota: `max_transcribes_per_session = 15`). The endpoint is gated by `enable_stt` and 503s cleanly when disabled.
3. **Edit.** The text is appended to the textarea so the user can fix typos before submitting -- this is intentional, since voice typos cost more UX than text typos.
4. **Retrieve.** `POST /api/session/{id}/query` runs the RAG pipeline (see below) and stores the answer in an in-memory `_query_results` map keyed by `query_id` (5 min TTL, 100 entries max).
5. **Stream.** The browser opens `EventSource` against `GET /api/session/{id}/query/{qid}/audio/stream`. The server feeds the answer text to `gpt-4o-mini-tts` with `response_format="pcm"`, base64-encodes 4 KB chunks, and emits them as `audio_chunk` SSE events. A 5-minute hard limit protects against runaway streams.
6. **Play.** `AudioStreamPlayer` decodes each base64 PCM chunk to `Int16Array` -> `Float32Array`, builds an `AudioBuffer` at 24 kHz mono, and schedules it on a continuous `nextPlayTime` timeline so playback is gapless. Pause/resume is implemented by suspending the `AudioContext`.

For the MP3 download path (`/audio/download`), `audio_service.generate_mp3` consults the **TTS audio cache** keyed on `SHA256(model + voice + text)`. On cache hit (24 h TTL), the blob is served from Postgres BYTEA in a single indexed lookup. Streaming PCM is intentionally not cached -- chunk framing is too tied to the live SSE handler to cache meaningfully.

## RAG pipeline

### Ingestion

`utils/pdf_processor.py`:

- `PyPDFLoader` produces one document per page, preserving page numbers for source citation.
- `semantic_chunk_text` replaces the previous `RecursiveCharacterTextSplitter`. It is **token-aware** (cheap `len/4` heuristic, no `tiktoken` dep), splits on a sentence-boundary regex tolerant of Portuguese punctuation, and accumulates sentences until the next would exceed `chunk_size_tokens = 400`. Overlap is rebuilt from trailing sentences up to `chunk_overlap_tokens = 80`, so chunks never break mid-sentence.
- Chunks are embedded by `EmbeddingService` (FastEmbed, `BAAI/bge-small-en-v1.5`, 384 dims, local ONNX, pre-downloaded at Docker build time).
- Vectors land in `embeddings(session_id, document_id, content, file_name, page_number, embedding vector(384), search_vector tsvector GENERATED)`. Indexes: `HNSW (vector_cosine_ops, m=16, ef_construction=64)` for semantic, `GIN(search_vector)` for keyword. Filters: `session_id`, `document_id`.

### Retrieval

`backend/services/vector_service.py` -> `routers/query.py`:

1. **Query embedding** via `embed_single`, hitting an in-memory LRU+TTL cache (`embedding_cache.py`, 512 entries / 1 h TTL) before paying the ONNX cost.
2. **Hybrid search** (`enable_hybrid_search=True`). A single SQL round trip runs two CTEs in parallel and fuses them via Reciprocal Rank Fusion:
   - `semantic`: `ORDER BY embedding <=> $query::vector` -> HNSW cosine
   - `keyword`: `plainto_tsquery('simple', $query)` ranked by `ts_rank_cd`
   - `fused`: `1.0/(rrf_k + sem.rank) + 1.0/(rrf_k + kw.rank)` with `rrf_k=60`
   The legacy cosine-only `search()` remains as a fallback when the flag is off.
3. **Candidate pool sizing.** With the reranker enabled we fetch `search_top_k * search_candidates_multiplier = 5 * 3 = 15` candidates so the cross-encoder has room to promote initially low-ranked chunks. Without reranker, exactly `search_top_k = 5`.
4. **Cohere reranker** (`services/reranker.py`, `enable_reranker=True`). `rerank-v3.5` cross-encoder rescores `(query, document)` pairs in one batched call, overwriting `score` with a calibrated `[0, 1]` value and preserving `rrf_score` for observability. Adds ~150-200 ms p50. **Fails open**: missing API key or vendor outage falls back to RRF order; `cohere` is an optional import.
5. **Grader** (`services/grader.py`). Drops candidates below the active threshold:
   - `relevance_threshold_reranked = 0.30` when reranker is on (Cohere `[0, 1]` scale).
   - `relevance_threshold = 0.01` for raw RRF (typical RRF scores live in `[0, 0.05]`).
   - Safety net: if every candidate is filtered out, keep the top 2 anyway and return `low_confidence=True`. The agent then prefaces its answer with explicit uncertainty instead of asserting facts.
6. **Processor Agent** (`services/agent_service.py`). Voice-first system prompt: 2-4 short sentences, no bullets, no markdown, no URLs, language matches the question. Context is wrapped in `<document source="...">` tags and the question in `<user_question>` tags so the model treats retrieved content as untrusted data (prompt-injection mitigation). Hard cap `MAX_CONTEXT_CHARS = 6000`; chunks over the cap are dropped wholesale. Output capped at `llm_max_tokens = 220` (~30 s of TTS, the limit before listeners disengage).

### LLM provider abstraction

`agent_service._build_processor_model` resolves the LLM that the Processor Agent runs on:

- `LLM_PROVIDER=openai` (default) -> Agents SDK uses the model id directly (`processor_model = gpt-4.1-mini`) with `OPENAI_API_KEY`.
- `LLM_PROVIDER=openrouter` -> wraps an `AsyncOpenAI` client pointed at `openrouter_base_url` with `HTTP-Referer` and `X-Title` headers, fed to `OpenAIChatCompletionsModel(model=llm_model, ...)`. Lets the RAG processor run on cheaper providers (`deepseek/deepseek-chat`, etc.) without touching the rest of the stack.

TTS (`gpt-4o-mini-tts`) and STT (`whisper-1`) **always** call OpenAI directly -- OpenRouter does not host audio APIs.

## Tech stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | Next.js 16.0.10, React 19.2, Tailwind v4, shadcn/ui (Radix), `lucide-react`, `sonner` | Standalone build, `poweredByHeader: false` |
| Audio capture | Native `MediaRecorder` + `getUserMedia` + `AnalyserNode` | Custom `useAudioRecorder` hook, no extra deps |
| Audio playback | Native `Web Audio API` + `EventSource` | Custom `AudioStreamPlayer`, gapless scheduling at 24 kHz |
| Backend | FastAPI 0.115, Uvicorn 0.34, Python 3.12 | `lifespan`-managed startup, eager service init |
| Agents | `openai-agents >= 0.0.10` | Single Processor Agent with `ModelSettings(max_tokens=220)`, tracing disabled |
| LLM (RAG) | `gpt-4.1-mini` via OpenAI, or any OpenRouter model | `LLM_PROVIDER` switch |
| Embeddings | `fastembed 0.4.2` (`BAAI/bge-small-en-v1.5`, 384 d) | Local ONNX, pre-downloaded at build time |
| Reranker | `cohere >= 5.13` (`rerank-v3.5`) | Optional, fails open |
| STT | OpenAI `whisper-1` (`AsyncOpenAI`, `verbose_json`) | Quota-gated, language whitelist |
| TTS | OpenAI `gpt-4o-mini-tts`, streaming PCM + MP3 | Postgres BYTEA cache for MP3 (24 h TTL) |
| Vector DB | PostgreSQL 17 + `pgvector` 0.3.6, `pgvector/pgvector:pg17` image | `HNSW` for cosine, `GIN` for `tsvector` |
| DB driver | `asyncpg 0.30` | Single shared pool: vectors, sessions, TTS cache |
| PDF | `langchain-community 0.3` + `pypdf 5.1` | Page-aware loading, custom semantic chunker |
| Reverse proxy | Traefik v3 | HTTPS via Let's Encrypt, security headers, `global-ratelimit@file`, `strip-server-header@file` |
| Container runtime | Docker + Docker Compose | Health checks gate startup order |

## Sessions and quotas

`backend/services/session_service.py` implements a **Postgres-backed** session store (replacing the previous in-memory variant). It reuses the `asyncpg` pool owned by `VectorService` to avoid a second connection set.

Tables (created idempotently at startup):

- `sessions(session_id UUID PK, created_at, last_activity, expires_at, transcribe_count, query_count, documents JSONB, creator_ip)` + index on `expires_at`.
- `session_create_log(id BIGSERIAL, ip TEXT, created_at)` + index on `(ip, created_at)` -- the sliding-window rate-limit log.

Lifecycle:

- Sessions expire after `session_inactivity_minutes = 5` of no activity. Every write (`add_document`, `add_query`, `increment_transcribe_count`) bumps `last_activity` and pushes `expires_at` forward.
- A background task (`cleanup_expired_sessions`, every `cleanup_interval_minutes = 1`) runs `DELETE FROM sessions WHERE expires_at < now() RETURNING session_id`, then for each removed row calls `vector_service.delete_session_data(session_id)` to drop the vectors. It also evicts `session_create_log` rows older than 1 day.
- `cleanup_expired_tts_cache` runs hourly and is **decoupled** from session cleanup so a stuck TTS-cache eviction can never block session lifecycle.

Quotas enforced per session:

| Limit | Default | Source |
|---|---|---|
| Queries per session | 5 | `max_queries_per_session` (persisted as `query_count`) |
| Documents per session | 3 | `max_documents_per_session` |
| Whisper transcriptions per session | 15 | `max_transcribes_per_session` (3x query budget; only successful calls counted) |

Rate limit on session creation:

- **Per-IP sliding window.** On `POST /api/session`, the server inserts into `session_create_log`, then `SELECT count(*) WHERE ip = $1 AND created_at > now() - interval '1 minute'`. If above `max_sessions_per_minute_per_ip = 10`, the transaction rolls back and the client gets `429`. The originating IP comes from `X-Forwarded-For` (Traefik is the only ingress).
- **Global sliding window** is checked in the same transaction against `max_sessions_per_minute = 10` for parity with the old in-memory limiter.

Datetime hygiene: every timestamp uses timezone-aware `datetime.now(timezone.utc)` (deprecated `datetime.utcnow()` is gone everywhere).

Errors: `/query` and `/documents` log the full traceback server-side (`logger.exception`) and return a generic `500 Error processing query` / `500 Error processing document` to the client. SSE errors emit `{"error": "stream_failed"}` rather than echoing the raw exception.

## Local development

### Prerequisites

- Docker + Docker Compose (recommended) **or** Python 3.12 + Node 20 + a local Postgres 17 with `pgvector`.
- `OPENAI_API_KEY` with access to `gpt-4.1-mini`, `gpt-4o-mini-tts`, and `whisper-1`.
- Optional: `COHERE_API_KEY` for the reranker. Without it the pipeline falls back to RRF order and logs a warning once.
- Optional: `OPENROUTER_API_KEY` if you want the RAG LLM to run through OpenRouter instead of OpenAI.

### Run the stack

```bash
cd /opt/showcase/voice_rag
cp backend/.env.example .env   # then fill in OPENAI_API_KEY etc.
docker compose up -d
docker compose logs -f backend
```

The compose file starts three containers, with `depends_on: condition: service_healthy` so the frontend only boots after the backend health check (`GET /health`) passes. First boot pulls FastEmbed model weights -- they are baked into the backend image to keep cold start fast.

### Run pieces individually

Backend:

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in OPENAI_API_KEY + DATABASE_URL
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

A reachable Postgres 17 with `CREATE EXTENSION vector` is required.

## Deployment

The deployment pattern follows the VPS standard (`pgdev.com.br`):

- Traefik v3 on the external `proxy` Docker network terminates HTTPS with Let's Encrypt and routes:
  - `voicerag.pgdev.com.br` -> frontend (port 3000)
  - `voicerag-api.pgdev.com.br` -> backend (port 8000)
- Both routers chain `*-security@docker` middlewares (HSTS preload, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, etc.) **plus** the global `global-ratelimit@file` and `strip-server-header@file` middlewares from the Traefik dynamic config.
- Health checks use `127.0.0.1` (not `localhost`) because BusyBox/Alpine resolves `localhost` to IPv6 only.
- The backend container reads `DATABASE_URL`, `OPENAI_API_KEY`, `CORS_ORIGINS`, and the `LLM_PROVIDER` / `LLM_MODEL` / `OPENROUTER_API_KEY` triple from the host env. The Postgres password and database name come from `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`.
- The frontend bakes `NEXT_PUBLIC_API_URL` at build time (Next.js public env) -- changing it requires a rebuild.

Standard ops:

```bash
cd /opt/showcase/voice_rag
docker compose up -d
docker compose ps
docker compose logs -f backend
echo | openssl s_client -connect voicerag.pgdev.com.br:443 2>/dev/null | openssl x509 -noout -subject -issuer
curl -sI https://voicerag.pgdev.com.br | grep -iE "strict-transport|x-frame|x-content"
```

## Environment variables

### Backend

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | required | Whisper, gpt-4o-mini-tts, and OpenAI-direct LLM path |
| `DATABASE_URL` | required | `postgresql://user:pass@host:5432/db` |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON array or comma-separated origins |
| `SESSION_INACTIVITY_MINUTES` | `5` | Session TTL |
| `CLEANUP_INTERVAL_MINUTES` | `1` | Session GC cadence |
| `MAX_QUERIES_PER_SESSION` | `5` | Per-session quota |
| `MAX_DOCUMENTS_PER_SESSION` | `3` | Per-session quota |
| `MAX_TRANSCRIBES_PER_SESSION` | `15` | Per-session Whisper quota |
| `MAX_SESSIONS_PER_MINUTE` | `10` | Global session-creation sliding window |
| `MAX_SESSIONS_PER_MINUTE_PER_IP` | `10` | Per-IP session-creation sliding window |
| `MAX_FILE_SIZE_MB` | `10` | PDF upload cap |
| `LLM_PROVIDER` | `openai` | `openai` or `openrouter` (RAG processor only) |
| `LLM_MODEL` | `deepseek/deepseek-chat` | Used when `LLM_PROVIDER=openrouter` |
| `OPENROUTER_API_KEY` | unset | Required when `LLM_PROVIDER=openrouter` |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override for self-hosted gateways |
| `PROCESSOR_MODEL` | `gpt-4.1-mini` | OpenAI-direct LLM model id |
| `LLM_MAX_TOKENS` | `220` | Hard cap on spoken answer (~30 s TTS) |
| `TTS_MODEL` | `gpt-4o-mini-tts` | Always OpenAI direct |
| `WHISPER_MODEL` | `whisper-1` | Always OpenAI direct |
| `ENABLE_STT` | `true` | Toggle the `/transcribe` endpoint |
| `ENABLE_HYBRID_SEARCH` | `true` | Falls back to cosine-only `search()` when off |
| `ENABLE_RERANKER` | `true` | Cohere cross-encoder rerank |
| `COHERE_API_KEY` | unset | Required when reranker is enabled |
| `COHERE_RERANK_MODEL` | `rerank-v3.5` | Cohere model id |
| `RELEVANCE_THRESHOLD` | `0.01` | Grader threshold on raw RRF scores |
| `RELEVANCE_THRESHOLD_RERANKED` | `0.30` | Grader threshold on Cohere `[0, 1]` scores |
| `SEARCH_TOP_K` | `5` | Documents passed to the LLM |
| `SEARCH_CANDIDATES_MULTIPLIER` | `3` | Reranker pool = `top_k * multiplier` |
| `RRF_K` | `60` | Cormack et al. RRF constant |
| `CHUNK_SIZE_TOKENS` | `400` | Semantic chunker target size |
| `CHUNK_OVERLAP_TOKENS` | `80` | Sentence-boundary overlap |
| `ENABLE_EMBEDDING_CACHE` | `true` | In-memory LRU+TTL on query embeddings |
| `EMBEDDING_CACHE_MAX_ENTRIES` | `512` | LRU capacity |
| `EMBEDDING_CACHE_TTL_SECONDS` | `3600` | Per-entry TTL |
| `ENABLE_TTS_CACHE` | `true` | Postgres-backed MP3 cache |
| `TTS_CACHE_TTL_SECONDS` | `86400` | 24 h |
| `DEBUG` | `false` | When `true`, exposes `/docs`, `/redoc`, `/openapi.json` |

### Frontend

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL, baked at build time |

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/session` | Create a session. Returns quotas. Rate-limited per IP and globally. |
| `GET` | `/api/session/{id}` | Session status, remaining quotas, uploaded documents. |
| `DELETE` | `/api/session/{id}` | Delete a session and all of its vectors. |
| `POST` | `/api/session/{id}/documents` | Upload a PDF. Validates magic bytes, chunks, embeds, stores. |
| `GET` | `/api/session/{id}/documents` | List uploaded documents in the session. |
| `DELETE` | `/api/session/{id}/documents/{doc_id}` | Delete a document and its vectors. |
| `POST` | `/api/session/{id}/transcribe` | Whisper STT for a recorded audio blob. |
| `POST` | `/api/session/{id}/query` | Submit a question. Runs the RAG pipeline. Returns text + audio URLs. |
| `GET` | `/api/session/{id}/queries` | (Stubbed -- query history is intentionally ephemeral.) |
| `GET` | `/api/session/{id}/query/{qid}/audio/stream` | SSE stream of base64 PCM chunks. |
| `GET` | `/api/session/{id}/query/{qid}/audio/download` | One-shot MP3 (TTS-cache aware). |
| `GET` | `/api/voices` | Available TTS voices. |
| `GET` | `/api/health` / `/health` | Database health + active session count. |
