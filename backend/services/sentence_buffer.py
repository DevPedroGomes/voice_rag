"""Streaming-friendly sentence boundary detection.

Used by the /query/stream pipeline to feed TTS one sentence at a time as
the LLM streams text. Goal: emit a sentence as soon as it is *probably*
complete, accept that we'll occasionally split inside a quote or after an
abbreviation, and never drop characters.

Voice answers are 2-4 sentences long — false positives cost a slightly
wonky TTS pause; false negatives just mean a longer first-audible-word
delay. The bias here is toward emitting early.
"""

from __future__ import annotations

import re

# Punctuation we treat as a sentence terminator.
_TERMINATORS = ".!?"

# Characters that can legitimately start a new sentence (uppercase letters
# in EN/PT/ES/FR, digits, common opening quotes/brackets). If the char
# after a terminator+whitespace is lowercase, we keep accumulating —
# that's almost always an abbreviation ("Mr. Smith", "etc. or").
_NEW_SENTENCE_START = re.compile(
    r"[A-Z0-9ÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝ\"'(\[—–-]"
)


def split_complete_sentences(buffer: str) -> tuple[list[str], str]:
    """Pull complete sentences off the front of `buffer`.

    Args:
        buffer: Accumulated text from the LLM stream.

    Returns:
        (sentences, remainder)
        - sentences: list of *complete* sentences ready for TTS, in order.
          Each is stripped of leading/trailing whitespace.
        - remainder: text after the last detected boundary. Should be fed
          back into the next call (concatenated with new deltas).

    Behavior:
        - Splits on `.`, `!`, `?` followed by whitespace **and** an uppercase
          letter (or digit, opening quote, etc.). Lowercase next-char is
          treated as an abbreviation and not a boundary.
        - Trailing terminator at end of buffer (no whitespace yet) stays in
          remainder — wait for the next chunk to confirm boundary.
        - Empty / whitespace-only sentences are dropped silently.
    """
    if not buffer:
        return [], ""

    sentences: list[str] = []
    last_split = 0
    i = 0

    while i < len(buffer):
        ch = buffer[i]
        if ch in _TERMINATORS:
            # Find the end of any whitespace run after the terminator.
            j = i + 1
            while j < len(buffer) and buffer[j].isspace():
                j += 1

            # If we ran off the end of the buffer, this might be a real
            # boundary but we can't confirm yet — leave it in remainder.
            if j >= len(buffer):
                break

            # Confirm boundary: next non-space char looks like a sentence start.
            if _NEW_SENTENCE_START.match(buffer[j]):
                sentence = buffer[last_split:i + 1].strip()
                if sentence:
                    sentences.append(sentence)
                last_split = j
                i = j
                continue

        i += 1

    return sentences, buffer[last_split:]


def flush_remainder(remainder: str) -> str | None:
    """Return remainder as a final sentence if it's substantive, else None.

    Called once when the LLM stream ends. Strips whitespace and drops
    fragments that are too short to be worth TTSing on their own (single
    punctuation, stray spaces).
    """
    s = (remainder or "").strip()
    if not s:
        return None
    # Strip a trailing sentence terminator if present so TTS doesn't
    # over-emphasize it. Re-add a period if there was no terminator at all.
    if s[-1] not in _TERMINATORS:
        s = s + "."
    return s
