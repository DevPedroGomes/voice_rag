"""Cohere cross-encoder reranker.

Sprint 2.1 — runs *after* hybrid search and *before* the grader. Takes the
prefetched candidates (top ~15 from RRF) and rescores them as (query, document)
pairs using Cohere's cross-encoder, which is much more precise than the
bi-encoder used at retrieval time.

Latency: ~150-200ms p50 for 15 documents. Acceptable for voice because we
already pay ~700-1500ms in TTS streaming downstream — reranking improves the
*content* of what gets spoken without dominating the wall-clock budget.

Vendor isolation:
- This is the only file that imports cohere. The router only sees the
  `rerank_documents()` function, so swapping vendors later (e.g., a local
  cross-encoder via sentence-transformers) is a one-file change.

Graceful degradation:
- No API key → return original order, log once at startup.
- API call fails → return original order, log warning, never raise.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton client. Lazy import keeps `cohere` an optional
# dependency: voice_rag still boots without it (just logs a warning).
_client: Any = None
_client_initialized = False
_warned_missing_key = False


def _get_client(api_key: str | None) -> Any | None:
    """Lazy-init Cohere client. Returns None if unavailable."""
    global _client, _client_initialized, _warned_missing_key

    if _client_initialized:
        return _client

    _client_initialized = True

    if not api_key:
        if not _warned_missing_key:
            logger.warning(
                "reranker: COHERE_API_KEY not set — reranking disabled, "
                "falling back to RRF order."
            )
            _warned_missing_key = True
        return None

    try:
        import cohere  # type: ignore

        _client = cohere.AsyncClient(api_key=api_key)
        logger.info("reranker: Cohere AsyncClient initialized")
        return _client
    except ImportError:
        logger.warning(
            "reranker: `cohere` package not installed — reranking disabled. "
            "Add `cohere>=5.0` to requirements.txt to enable."
        )
        return None
    except Exception as e:
        logger.warning("reranker: failed to initialize Cohere client: %s", e)
        return None


async def rerank_documents(
    query: str,
    documents: list[dict[str, Any]],
    top_n: int,
    model: str = "rerank-v3.5",
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Rerank documents using Cohere cross-encoder.

    Args:
        query: User query (or transformed query for self-correction loops).
        documents: Candidates from hybrid search. Each must have 'content';
            other fields are preserved as-is.
        top_n: Number of documents to return after reranking.
        model: Cohere rerank model. `rerank-v3.5` is GA and supported.
        api_key: Cohere API key (passed in to keep this module config-agnostic).

    Returns:
        Top-N documents reordered by Cohere relevance, with `score` updated to
        the Cohere score (in [0, 1]) and `rrf_score` preserved for debugging.
        On any failure, returns `documents[:top_n]` in original order.
    """
    if not documents:
        return []

    # Single-document case: nothing to rerank.
    if len(documents) <= 1:
        return documents[:top_n]

    client = _get_client(api_key)
    if client is None:
        return documents[:top_n]

    # Cohere caps requests; defensively limit to 1000 docs (we'll never
    # come close in voice_rag, but be explicit).
    candidates = documents[:1000]
    docs_text = [d.get("content", "") or "" for d in candidates]

    try:
        response = await client.rerank(
            model=model,
            query=query,
            documents=docs_text,
            top_n=min(top_n, len(candidates)),
            return_documents=False,
        )
    except Exception as e:
        # Never let a vendor outage break /query. Log and degrade.
        logger.warning(
            "reranker: Cohere call failed (%s) — falling back to RRF order",
            e,
        )
        return candidates[:top_n]

    # Cohere returns results sorted by relevance, each with .index into the
    # input list and .relevance_score in [0, 1].
    reranked: list[dict[str, Any]] = []
    for result in response.results:
        original = candidates[result.index]
        # Don't mutate the caller's dicts; shallow copy.
        new_doc = dict(original)
        # Preserve original RRF for observability/debug.
        new_doc["rrf_score"] = original.get("score", 0.0)
        new_doc["score"] = float(result.relevance_score)
        reranked.append(new_doc)

    return reranked
