# CLAUDE.md

> ⛔ **ESTE PROJETO ESTÁ SENDO APOSENTADO COMO CARD DE PORTFÓLIO (06/09/2026).**
>
> **A engenharia de voz aqui está certa e não será jogada fora: ela migra para o
> `group-documents` (BrainHub).** O motivo não é técnico. Qualquer pessoa sobe um PDF no chat
> de um provedor, pergunta por voz, ouve a resposta e continua a conversa, então este projeto
> não tem uma linha em que vença. O que diferencia não é a voz, é o acervo, e o acervo está
> no BrainHub.
>
> 📄 **Antes de mexer em qualquer coisa aqui, leia `docs/EXTRACAO-PARA-BRAINHUB.md`.**
> Ele tem o inventário exato do que migra, o que muda no caminho, e a armadilha de CSP que já
> derrubou a conversa ao vivo uma vez.
>
> **Não construa feature nova neste repositório.** O único trabalho previsto aqui é subir o
> rerank de `rerank-v3.5` para `rerank-v4.0-fast` antes da migração, para não levar a
> defasagem junto.
>
> ⚠️ **Não derrube os containers `voicerag-*`** enquanto o card do Voice RAG ainda estiver no
> ar em `portfolio.pgdev.com.br`. Demo morta custa mais que demo ausente.


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
- `POST /api/session/{id}/documents` - Upload PDF (enforces document limit; runs Contextual Retrieval enrichment when ANTHROPIC_API_KEY is set)
- `POST /api/session/{id}/query` - Submit question, get JSON response with audio_stream_url (sync path)
- `POST /api/session/{id}/query/stream` - **Streaming variant** — SSE that interleaves `text_delta` and `audio_chunk` events. TTS is sentence-pipelined: audio for sentence #1 starts while LLM is still writing sentence #2. Cuts first-audible-word from ~1500ms to ~600ms.
- `GET /api/session/{id}/query/{qid}/audio/stream` - SSE audio stream (used by the sync /query path; the /query/stream path emits audio inline)

### `/query/stream` SSE event vocabulary

| event | when | data shape |
|---|---|---|
| `sources` | once, before any text | `{sources: [filename, ...]}` |
| `text_delta` | many | `{delta: "..."}` |
| `audio_chunk` | many, interleaved with text_delta | `{chunk: <base64 PCM>, sentence_idx, chunk_idx}` |
| `audio_error` | per-sentence TTS failure (non-fatal) | `{sentence_idx, error}` |
| `complete` | once, last event | `{query_id, total_sentences}` |
| `error` | terminal failure | `{error: "..."}` |

### Conversa ao vivo (WebRTC) — o que migra para o BrainHub

⚠️ **Esta seção não existia neste arquivo até 06/09/2026**, apesar de ser a parte mais
avançada do projeto e a única que sobrevive à aposentadoria. Documentada agora porque é
exatamente o que será extraído.

```
navegador ⟷ WebRTC ⟷ OpenAI Realtime (gpt-realtime-2.1)
                          ↓ function_call
                   backend: buscar_nos_documentos()
                   hibrido → rerank → grader
```

- `POST /api/realtime/session?session_id=...` — cunha a credencial efêmera (`ek_...`) já
  amarrada às instruções e à tool. **A chave real da OpenAI nunca chega ao cliente**, e o
  visitante não consegue reconfigurar a sessão para outra coisa. O teto diário é consumido
  **antes** de cunhar, porque conversa aberta é gasto aberto.
- `POST /api/realtime/tool/buscar?session_id=...` — executa a tool que o modelo chamou, com o
  **mesmo** `_retrieve_and_grade` do `/query`. Quem filtra continua sendo o grader, do lado do
  servidor: deliberadamente não é o navegador que decide o que é relevante.
- Lista vazia com `baixa_confianca` é **resposta válida, não erro**. É o que permite o agente
  dizer "não está nos documentos" em vez de inventar. Nunca vire isso em exceção.
- **O áudio não passa pelo backend.** Proxiar mídia em tempo real numa KVM de 2 vCPU seria o
  gargalo, e o WebRTC já resolve jitter, perda de pacote e eco. O backend entra só onde precisa
  mandar: cunhar a credencial e executar a busca.
- Cliente em `frontend/src/lib/realtime-session.ts`: `RTCPeerConnection`, `getUserMedia`,
  data channel `oai-events`, e o ciclo `function_call` → `function_call_output` →
  `response.create`.

> 🚨 **CSP.** O commit `21e3642` registra que o botão falhava para **100% dos visitantes**
> porque a CSP não listava `api.openai.com` em `connect-src`, e o WebRTC troca o SDP direto
> com a OpenAI. A regra vive em `docker-compose.yml`, nos labels do Traefik. Apertar essa CSP
> sem lembrar disto mata a conversa ao vivo em silêncio, sem erro no servidor.

### Advanced RAG features
- **Hybrid search** — pgvector HNSW + tsvector GIN, fused via Reciprocal Rank Fusion in a single SQL CTE round-trip.
- **Cross-encoder reranking** — Cohere `rerank-v3.5` (graceful degradation to RRF order without `COHERE_API_KEY`).
- **Contextual Retrieval** (Anthropic 2024) — Claude Haiku enriches each chunk with 2-3 sentences of document context before embedding. Async with bounded concurrency (`asyncio.Semaphore(5)`); prompt-cached document so chunks 2..N pay ~10%. Disabled when `ANTHROPIC_API_KEY` is unset.
- **Multi-query expansion** — Haiku generates 3 paraphrasings; original + variants are embedded and searched in parallel via `asyncio.gather`, then merged by chunk id (best score wins) before reranking.
- **Score-based grader** — RRF or rerank score thresholds with safety net + low_confidence flag the LLM is told about.

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
