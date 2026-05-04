import logging
import os
import re
import tempfile
from typing import Any

from langchain_community.document_loaders import PyPDFLoader

logger = logging.getLogger(__name__)


# Sentence boundary regex: split after . ! ? when followed by whitespace.
# Includes Portuguese-friendly punctuation (?, !, .) and handles common
# abbreviations conservatively (no special-casing — favors recall over a
# perfect split, which is fine because the LLM tolerates small misalignments).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9])")


def _approx_token_count(text: str) -> int:
    """Cheap token estimate without tiktoken dependency.

    Heuristic: ~1 token per 4 characters for English/Romance languages.
    Slightly over-counts (good — keeps chunks on the small side), no model
    download, no extra dependency. The caller doesn't need cryptographic
    accuracy here, just a stable signal for chunk boundaries.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def _split_into_sentences(text: str) -> list[str]:
    """Sentence-boundary split. Falls back to whole text if no boundary found."""
    if not text or not text.strip():
        return []
    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def semantic_chunk_text(
    text: str,
    max_tokens: int = 400,
    overlap_tokens: int = 80,
) -> list[str]:
    """Sentence-boundary chunking with token-aware accumulation.

    Strategy:
    1. Split the text into sentences (regex on . ! ? + whitespace).
    2. Accumulate sentences into a chunk until adding the next would
       exceed `max_tokens`. Emit the chunk.
    3. Start the next chunk with the *trailing sentences* of the previous
       chunk that fit in `overlap_tokens`. This keeps cross-chunk context
       (a definition followed by an example don't get separated mid-way).

    Why this beats RecursiveCharacterTextSplitter for voice_rag:
    - Never splits inside a sentence — the LLM never sees half-thoughts.
    - Overlap is *semantic* (sentence boundaries), not character-level.
    - Smaller default `max_tokens` (400 vs 1000) — voice answers cite
      fewer chunks, so the relevance bar per chunk needs to be higher.
    """
    sentences = _split_into_sentences(text)
    if not sentences:
        return []

    # Edge case: a single sentence longer than max_tokens. We still emit it
    # as one chunk (don't break it) — the LLM handles oversized chunks fine,
    # and breaking a sentence here would defeat the whole point.

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = _approx_token_count(sent)

        # If adding this sentence would overflow AND we already have content,
        # flush the current chunk and start a new one with overlap.
        if current and current_tokens + sent_tokens > max_tokens:
            chunks.append(" ".join(current))

            # Build overlap: walk backwards from end of `current`, taking
            # whole sentences until we hit `overlap_tokens`.
            overlap: list[str] = []
            ov_tokens = 0
            for prev_sent in reversed(current):
                t = _approx_token_count(prev_sent)
                if ov_tokens + t > overlap_tokens:
                    break
                overlap.insert(0, prev_sent)
                ov_tokens += t

            current = overlap + [sent]
            current_tokens = ov_tokens + sent_tokens
        else:
            current.append(sent)
            current_tokens += sent_tokens

    # Flush trailing chunk
    if current:
        chunks.append(" ".join(current))

    return chunks


def process_pdf(
    file_content: bytes,
    file_name: str,
    chunk_size: int = 400,
    chunk_overlap: int = 80,
) -> tuple[list[dict[str, Any]], int]:
    """
    Process a PDF file and split into chunks with metadata.

    Sprint 2.2: chunking is now sentence-aware (semantic_chunk_text), with
    smaller defaults (~400 tokens) tuned for voice answers. The function
    signature is preserved for backwards compatibility — `chunk_size` /
    `chunk_overlap` are now interpreted as *token* counts, not characters.

    Args:
        file_content: PDF file content as bytes.
        file_name: Original file name.
        chunk_size: Max tokens per chunk (≈ chars/4).
        chunk_overlap: Tokens of sentence overlap between adjacent chunks.

    Returns:
        Tuple of (list of chunks with metadata, page count). Each chunk dict
        has content/file_name/page_number.
    """
    tmp_file_path = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(file_content)
            tmp_file.flush()
            tmp_file_path = tmp_file.name

        # Process PDF page-by-page (LangChain's PyPDFLoader gives one Document
        # per page with .metadata['page']). We chunk *within* each page so
        # citations remain page-accurate — critical for voice (the user can
        # ask "what page is that on?").
        loader = PyPDFLoader(tmp_file_path)
        pages = loader.load()
        page_count = len(pages)

        result: list[dict[str, Any]] = []
        for page_doc in pages:
            page_text = page_doc.page_content
            page_num = page_doc.metadata.get("page", None)

            page_chunks = semantic_chunk_text(
                page_text,
                max_tokens=chunk_size,
                overlap_tokens=chunk_overlap,
            )

            for chunk_text in page_chunks:
                result.append({
                    "content": chunk_text,
                    "file_name": file_name,
                    "page_number": page_num,
                })

        return result, page_count

    finally:
        # Always cleanup temporary file
        if tmp_file_path and os.path.exists(tmp_file_path):
            try:
                os.unlink(tmp_file_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp PDF file: {e}")
