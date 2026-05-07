"""Contextual Retrieval (Anthropic, 2024) — enriches each chunk with
document-level context via a fast LLM *before* embedding.

Reference: https://www.anthropic.com/news/contextual-retrieval

Why bother for voice_rag:
- Voice answers cite fewer chunks (top-5 → top-3 typical), so each chunk
  needs to be more self-contained. A bare "the deadline is March 15" is
  useless without "for the lease renewal in section 4". Contextual prefixing
  bakes the situation into the embedding.
- Anthropic measured +35% recall over plain BM25, +49% combined with hybrid,
  +67% with reranker on top — this stack mirrors what voice_rag already runs.

How costs stay low:
- Prompt caching: the document text is sent with `cache_control: ephemeral`
  on the first chunk; chunks 2..N pay ~90% less on those input tokens.
- Async + bounded concurrency: a 20-chunk PDF doesn't serialize 20 LLM
  round-trips — they fan out under a semaphore (default 5).

Graceful degradation:
- No ANTHROPIC_API_KEY → return chunks unchanged, log once at startup.
- Per-chunk failure → that chunk is embedded raw, the others still benefit.
- Total failure of the lazy import → return chunks unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Module-level singleton client. Lazy import keeps `anthropic` an optional
# dependency: voice_rag still boots without it (just logs a warning).
_client: Any = None
_client_initialized = False
_warned_missing_key = False


def _get_client(api_key: str | None) -> Any | None:
    """Lazy-init AsyncAnthropic client. Returns None when unavailable."""
    global _client, _client_initialized, _warned_missing_key

    if _client_initialized:
        return _client

    _client_initialized = True

    if not api_key:
        if not _warned_missing_key:
            logger.warning(
                "contextual_enrichment: ANTHROPIC_API_KEY not set — chunks "
                "will be embedded raw (no contextual prefix)."
            )
            _warned_missing_key = True
        return None

    try:
        from anthropic import AsyncAnthropic  # type: ignore[import-not-found]

        _client = AsyncAnthropic(api_key=api_key)
        logger.info("contextual_enrichment: AsyncAnthropic client initialized")
        return _client
    except ImportError:
        logger.warning(
            "contextual_enrichment: `anthropic` package not installed — "
            "contextual retrieval disabled. Add `anthropic>=0.40.0` to "
            "requirements.txt to enable."
        )
        return None
    except Exception as e:
        logger.warning(
            "contextual_enrichment: failed to init Anthropic client: %s", e
        )
        return None


async def _enrich_one(
    client: Any,
    model: str,
    doc_context: str,
    document_title: str,
    chunk_text: str,
    semaphore: asyncio.Semaphore,
) -> str:
    """Generate 2-3 sentences of context for a single chunk.

    Returns the context string alone — the caller prepends it to the chunk.
    Empty string on any failure (caller embeds the chunk raw).
    """
    async with semaphore:
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=150,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f'<document title="{document_title}">\n'
                                    f"{doc_context}\n</document>"
                                ),
                                # Cache the document — chunks 2..N pay ~90%
                                # less on these input tokens.
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Here is a chunk from this document:\n"
                                    f"<chunk>\n{chunk_text}\n</chunk>\n\n"
                                    "Give a short succinct context (2-3 "
                                    "sentences) to situate this chunk within "
                                    "the overall document. Answer ONLY with "
                                    "the context, no preamble."
                                ),
                            },
                        ],
                    }
                ],
            )
            # response.content is a list of content blocks; the first text
            # block is the answer.
            return (response.content[0].text or "").strip()
        except Exception as e:
            logger.warning(
                "contextual_enrichment: per-chunk call failed (%s) — chunk "
                "will be embedded raw",
                e,
            )
            return ""


async def enrich_chunks(
    chunks: list[dict[str, Any]],
    full_document_text: str,
    document_title: str,
    *,
    api_key: str | None = None,
    model: str = "claude-haiku-4-5",
    max_doc_chars: int = 50_000,
    concurrency: int = 5,
) -> list[dict[str, Any]]:
    """Enrich each chunk's `content` with document-level context.

    Args:
        chunks: List of chunk dicts. Each must have a `content` key; other
            keys (file_name, page_number, ...) are preserved.
        full_document_text: Concatenated document text used as the context
            window for the LLM. Truncated at `max_doc_chars` for cost.
        document_title: Filename / title shown in the LLM prompt.
        api_key: Anthropic API key. None disables enrichment.
        model: Claude model id. Haiku-class is the right choice for cost.
        max_doc_chars: Hard cap on document context size.
        concurrency: Max concurrent LLM calls (semaphore).

    Returns:
        New list of chunk dicts (shallow-copied) where `content` becomes
        `f"{context}\\n\\n{original_content}"`. On any global failure or
        missing key, returns the input list unchanged. Original chunk dicts
        are never mutated.
    """
    if not chunks:
        return []

    client = _get_client(api_key)
    if client is None:
        return chunks

    doc_context = (full_document_text or "")[:max_doc_chars]
    if not doc_context.strip():
        # No document text to anchor context — enrichment can't help.
        return chunks

    semaphore = asyncio.Semaphore(max(1, concurrency))

    tasks = [
        _enrich_one(
            client=client,
            model=model,
            doc_context=doc_context,
            document_title=document_title,
            chunk_text=chunk.get("content", "") or "",
            semaphore=semaphore,
        )
        for chunk in chunks
    ]

    contexts = await asyncio.gather(*tasks, return_exceptions=False)

    enriched: list[dict[str, Any]] = []
    enriched_count = 0
    for chunk, ctx in zip(chunks, contexts):
        new_chunk = dict(chunk)  # shallow copy — never mutate caller's data
        original_content = chunk.get("content", "") or ""
        if ctx:
            new_chunk["content"] = f"{ctx}\n\n{original_content}"
            enriched_count += 1
        else:
            new_chunk["content"] = original_content
        enriched.append(new_chunk)

    logger.info(
        "contextual_enrichment: enriched %d/%d chunks for '%s' (model=%s, "
        "concurrency=%d)",
        enriched_count,
        len(chunks),
        document_title,
        model,
        concurrency,
    )
    return enriched
