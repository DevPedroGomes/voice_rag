import json
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str

    # PostgreSQL with pgvector
    database_url: str

    # Session - inactivity-based expiration
    session_inactivity_minutes: int = 5  # Sessions expire after 5 min of inactivity
    cleanup_interval_minutes: int = 1    # Check for expired sessions every 1 min

    # CORS - accepts JSON array or comma-separated origins via CORS_ORIGINS env var
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # File upload
    max_file_size_mb: int = 10

    # Rate limiting (showcase protection)
    max_queries_per_session: int = 5
    max_documents_per_session: int = 3
    max_sessions_per_minute: int = 10
    # Onda 3 — Whisper transcription quota (3x query budget; bad recordings
    # are already a UX cost, so only successful transcriptions are counted).
    max_transcribes_per_session: int = 15
    # Onda 3 — sliding window per-IP session-creation rate limit.
    max_sessions_per_minute_per_ip: int = 10

    # AI models — split intentionally:
    # • llm_provider/llm_model decide o LLM do RAG (pode rodar em OpenRouter,
    #   barato; veja services/agent_service.py).
    # • tts_model e whisper_model continuam OpenAI direto (OpenRouter não
    #   hospeda áudio APIs). Sempre usa openai_api_key.
    llm_provider: str = "openai"  # "openrouter" | "openai"
    llm_model: str = "deepseek/deepseek-chat"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # OpenAI-direct path (when llm_provider="openai") + always for TTS/Whisper.
    processor_model: str = "gpt-4.1-mini"
    tts_model: str = "gpt-4o-mini-tts"

    # ── Sprint 1: Retrieval pipeline ────────────────────────────────────────
    # Feature flag: enable hybrid search (semantic + keyword via RRF).
    # When False, falls back to legacy `search()` (cosine only) — useful for
    # rollback if hybrid causes regressions.
    enable_hybrid_search: bool = True

    # Number of final documents passed to the LLM after grading.
    search_top_k: int = 5

    # Each ranker (semantic, keyword) fetches top_k * multiplier candidates
    # before RRF fusion. Higher = better recall, slightly slower.
    search_candidates_multiplier: int = 3

    # RRF k constant (Cormack et al. 2009). 60 is standard.
    rrf_k: int = 60

    # Minimum RRF score to consider a chunk relevant. Below this, the grader
    # filters it out (with a safety net of top-2 if everything is filtered).
    # RRF scores are typically in [0.0, 0.05] range — much smaller than
    # cosine similarity. Threshold of 0.01 ≈ doc must rank top-100 in at
    # least one ranker to survive.
    relevance_threshold: float = 0.01

    # Embedding cache (in-memory LRU+TTL). Reduces FastEmbed work for
    # repeated queries (e.g., FAQs). See services/embedding_cache.py.
    enable_embedding_cache: bool = True
    embedding_cache_max_entries: int = 512
    embedding_cache_ttl_seconds: int = 3600

    # ── Sprint 2: Quality boost ─────────────────────────────────────────────
    # Cohere reranker (cross-encoder). Reorders the top hybrid candidates
    # before grading. ~150-200ms p50 added latency, +35% precision.
    enable_reranker: bool = True
    cohere_api_key: str | None = None
    cohere_rerank_model: str = "rerank-v3.5"

    # Threshold applied AFTER the reranker. Cohere returns calibrated scores
    # in [0, 1] (much higher than raw RRF), so the bar is much higher too.
    # 0.30 ≈ "Cohere thinks this chunk has at least moderate relevance".
    # Tune up for stricter answers, down for higher recall.
    relevance_threshold_reranked: float = 0.30

    # Voice-tuned answer cap. ~220 tokens ≈ 30 seconds of TTS audio, which
    # is about the limit before users disengage from a spoken answer.
    llm_max_tokens: int = 220

    # Semantic chunking defaults (tokens, not chars). Smaller than docmind's
    # 500 because voice answers cite fewer chunks — each must be tighter.
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 80

    # ── Sprint 5: Multi-query expansion ─────────────────────────────────────
    # Generate N alternative phrasings of the user query via Claude Haiku,
    # then run hybrid retrieval against each variant in parallel and merge
    # by chunk id (best score wins) before reranking. Improves recall on
    # terse voice queries — the spoken phrasing rarely matches document
    # vocabulary, and variants bridge that gap.
    #
    # Latency posture: the LLM call (~300-500ms) runs concurrently with the
    # original query's embedding; the N extra hybrid searches run in
    # parallel via asyncio.gather. Net wall-clock add ≈ 200-400ms.
    #
    # Falls back to original-query-only when ANTHROPIC_API_KEY is missing.
    enable_multi_query: bool = True
    multi_query_count: int = 3
    # Cap on the expansion LLM response. ≈ 150 words = plenty for 3-4 variants.
    multi_query_max_tokens: int = 200

    # ── Sprint 4: Contextual Retrieval (Anthropic, 2024) ────────────────────
    # Pre-pend 2-3 sentences of document-level context to each chunk *before*
    # embedding. Implemented via Claude Haiku with prompt caching: the
    # document is sent with `cache_control=ephemeral` on the first call, so
    # chunks 2..N pay ~90% less on those input tokens.
    #
    # Anthropic measured +35% recall over plain BM25, +49% combined with
    # hybrid search, +67% with reranker on top — exactly the stack we run.
    # https://www.anthropic.com/news/contextual-retrieval
    #
    # Falls back gracefully to raw chunks when ANTHROPIC_API_KEY is missing.
    enable_contextual_retrieval: bool = True
    anthropic_api_key: str | None = None
    contextual_model: str = "claude-haiku-4-5"
    # Document text is truncated to this length before being sent as context
    # — bounds cost on huge PDFs while still giving the LLM enough surface
    # to situate any chunk. ~50K chars ≈ 12K tokens, well under Haiku's window.
    contextual_max_doc_chars: int = 50_000
    # Max concurrent enrichment calls. 5 keeps a 20-chunk PDF under ~3s of
    # ingest latency p50 (Haiku is ~500-700ms per call).
    contextual_max_chunks_concurrent: int = 5

    # ── Sprint 3: Voice loop closure ────────────────────────────────────────
    # Speech-to-Text via OpenAI Whisper. When False, the /transcribe endpoint
    # returns 503 — useful for cost control or to disable the mic button
    # without redeploying the frontend.
    enable_stt: bool = True
    whisper_model: str = "whisper-1"

    # TTS audio cache (PostgreSQL BYTEA). Caches the full MP3 by
    # SHA256(model + voice + text). 24h TTL by default; the periodic cleanup
    # task evicts stale rows.
    enable_tts_cache: bool = True
    tts_cache_ttl_seconds: int = 86400  # 24h

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
