"""Multi-query expansion via Claude Haiku.

Generate N alternative phrasings of the user query so that hybrid retrieval
runs across multiple angles (synonyms, related concepts, sub-questions).
Variants are embedded + searched in parallel, then merged by chunk id
(best score wins) before reranking. This improves recall — especially for
short voice queries where the user's exact wording may miss the relevant
chunk.

Why this matters for voice:
  Voice queries tend to be terse and conversational ("what's the deadline?")
  while the relevant document chunk may use formal language ("the final
  submission must be received by...". Multi-query bridges that gap by
  generating variants that look more like the document's vocabulary.

Latency posture:
  - The expansion LLM call is the slowest single step (~300-500ms with Haiku).
  - The caller starts the original query's embedding *concurrently* with
    expansion, so wall-clock cost ≈ max(LLM, embed) - embed ≈ 200-400ms.
  - All N+1 hybrid searches run in parallel via asyncio.gather; the
    incremental DB load is N extra round-trips, each ~30-50ms.

Graceful degradation:
  - No ANTHROPIC_API_KEY → return empty variants list, log once at startup.
  - LLM call fails → return empty list, log warning, never raise.
  - The caller treats an empty list as "use the original query only".
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Module-level singleton client. Lazy import keeps `anthropic` optional.
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
                "query_expansion: ANTHROPIC_API_KEY not set — multi-query "
                "expansion disabled, retrieval will use original query only."
            )
            _warned_missing_key = True
        return None

    try:
        from anthropic import AsyncAnthropic  # type: ignore[import-not-found]

        _client = AsyncAnthropic(api_key=api_key)
        logger.info("query_expansion: AsyncAnthropic client initialized")
        return _client
    except ImportError:
        logger.warning(
            "query_expansion: `anthropic` package not installed — "
            "multi-query expansion disabled."
        )
        return None
    except Exception as e:
        logger.warning(
            "query_expansion: failed to init Anthropic client: %s", e
        )
        return None


async def expand_query(
    query: str,
    *,
    api_key: str | None = None,
    model: str = "claude-haiku-4-5",
    count: int = 3,
    max_tokens: int = 200,
) -> list[str]:
    """Generate `count` alternative phrasings of `query`.

    Args:
        query: User's original question.
        api_key: Anthropic API key. None disables expansion.
        model: Claude model id. Haiku-class is the right tradeoff (fast,
            cheap) — we don't need flagship reasoning for paraphrasing.
        count: Number of variants to generate.
        max_tokens: Cap on the LLM response. Variants are short, so 200
            tokens is plenty (≈ 150 words = 7-8 variant lines).

    Returns:
        List of variant strings (length up to `count`). Returns `[]` on any
        failure or when expansion is disabled — the caller should treat
        an empty list as "use the original query only".
    """
    if count <= 0 or not query.strip():
        return []

    client = _get_client(api_key)
    if client is None:
        return []

    prompt = (
        f"Generate exactly {count} different search queries that would help "
        f"find information answering this question:\n\n"
        f'"{query}"\n\n'
        "Each query should approach the topic from a different angle "
        "(synonyms, related concepts, more specific or more general "
        "phrasings). Match the language of the original question.\n\n"
        "Return ONLY the queries, one per line, with no numbering, no "
        "bullets, no preamble, no explanation."
    )

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        logger.warning(
            "query_expansion: LLM call failed (%s) — falling back to "
            "original query only",
            e,
        )
        return []

    raw = (response.content[0].text or "").strip()
    if not raw:
        return []

    # Take non-empty lines, strip leading bullets/numbers defensively
    # (the prompt forbids them but cheap to be tolerant).
    variants: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip "1. ", "1) ", "- ", "* " prefixes if the model adds them.
        for prefix_char in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
            if line.startswith(f"{prefix_char}. ") or line.startswith(f"{prefix_char}) "):
                line = line[3:].strip()
                break
        if line.startswith("- ") or line.startswith("* "):
            line = line[2:].strip()
        # Drop variants that exactly match the original (no point searching twice).
        if line and line.lower() != query.lower():
            variants.append(line)

    logger.info(
        "query_expansion: generated %d/%d variants for query '%s...' (model=%s)",
        len(variants[:count]),
        count,
        query[:50],
        model,
    )
    return variants[:count]
