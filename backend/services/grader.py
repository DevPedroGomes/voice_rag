"""Score-based document grader.

Filters retrieval results by relevance score, with a safety net to never return
an empty list when documents exist. Uses zero LLM calls (decision is based on
the score returned by the retriever / future reranker).

Critical for voice: a low-confidence flag lets the agent say "I'm not sure"
out loud instead of hallucinating an answer the user will hear.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def grade_documents(
    documents: list[dict[str, Any]],
    threshold: float,
    safety_net_size: int = 2,
) -> tuple[list[dict[str, Any]], bool]:
    """Filter documents by relevance score.

    Args:
        documents: Retrieved documents (must contain a 'score' key).
        threshold: Minimum acceptable score [0, 1]. Docs below are dropped.
        safety_net_size: If everything is filtered out, keep this many top docs
            anyway (so the LLM still has *something* to work with) and signal
            low confidence.

    Returns:
        (filtered_documents, low_confidence)
        - filtered_documents: docs with score >= threshold, or top-N safety net.
        - low_confidence: True when most docs were filtered or when we fell back
          to the safety net. The router/agent should adapt the response tone
          (e.g., "I'm not sure but..." or refuse to answer in voice mode).
    """
    if not documents:
        return [], True

    sorted_docs = sorted(
        documents, key=lambda d: d.get("score", 0.0), reverse=True
    )

    filtered = [d for d in sorted_docs if d.get("score", 0.0) >= threshold]

    # Safety net: never return empty when we have *something*.
    if not filtered:
        logger.info(
            "grader: all %d docs below threshold %.2f (top score=%.3f); "
            "falling back to top-%d with low_confidence=True",
            len(sorted_docs),
            threshold,
            sorted_docs[0].get("score", 0.0),
            safety_net_size,
        )
        return sorted_docs[:safety_net_size], True

    # If more than half were filtered, we still trust the survivors but flag
    # the result as not-fully-confident. The agent can still answer normally,
    # but downstream consumers may decide to phrase more cautiously.
    low_confidence = len(filtered) < len(sorted_docs) / 2

    return filtered, low_confidence
