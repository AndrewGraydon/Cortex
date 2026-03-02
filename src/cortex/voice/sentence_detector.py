"""Sentence boundary detector for streaming TTS.

Buffers LLM output tokens and flushes on sentence boundaries (DD-031).
Lightweight state machine — no NLP library, negligible CPU overhead.

Primary triggers: . ! ? followed by whitespace or end-of-generation
Secondary triggers: : ; — followed by whitespace
Minimum chunk: 8 tokens (avoids tiny fragments)
Maximum chunk: 96 tokens (Kokoro axmodel limit)
"""

from __future__ import annotations

# Thresholds
MIN_TOKENS = 8
MAX_TOKENS = 96

# Sentence-ending punctuation
PRIMARY_ENDINGS = {".": True, "!": True, "?": True}
SECONDARY_ENDINGS = {":": True, ";": True, "—": True, "\n": True}


class SentenceDetector:
    """Accumulates LLM output and detects sentence boundaries.

    Feed tokens via feed(). Returns list of complete sentences.
    Call flush() at end of generation to get any remaining text.
    """

    def __init__(
        self,
        min_tokens: int = MIN_TOKENS,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self._min_tokens = min_tokens
        self._max_tokens = max_tokens
        self._buffer = ""
        self._token_count = 0

    def reset(self) -> None:
        """Reset buffer for new generation."""
        self._buffer = ""
        self._token_count = 0

    def feed(self, text: str) -> list[str]:
        """Feed a token/chunk of text. Returns list of complete sentences."""
        self._buffer += text
        self._token_count += _count_tokens(text)

        sentences: list[str] = []

        while True:
            sentence = self._try_extract()
            if sentence is None:
                break
            sentences.append(sentence)

        return sentences

    def flush(self) -> str:
        """Flush remaining buffer (end of generation)."""
        text = self._buffer.strip()
        self._buffer = ""
        self._token_count = 0
        return text

    def _try_extract(self) -> str | None:
        """Try to extract a complete sentence from the buffer."""
        # Force flush if buffer exceeds max tokens
        if self._token_count >= self._max_tokens:
            return self._force_flush()

        # Don't try to split if below minimum
        if self._token_count < self._min_tokens:
            return None

        # Look for sentence boundaries
        best_pos = -1

        for i, char in enumerate(self._buffer):
            if char in PRIMARY_ENDINGS:
                # Check if followed by whitespace or end of buffer
                if i + 1 >= len(self._buffer) or self._buffer[i + 1] in " \n\t":
                    # Check minimum token count up to this point
                    prefix = self._buffer[: i + 1]
                    if _count_tokens(prefix) >= self._min_tokens:
                        best_pos = i + 1
                        break  # Take first valid boundary

            elif (
                char in SECONDARY_ENDINGS
                and i + 1 < len(self._buffer)
                and self._buffer[i + 1] in " \n\t"
            ):
                prefix = self._buffer[: i + 1]
                if _count_tokens(prefix) >= self._min_tokens:
                    best_pos = i + 1
                    break

        if best_pos > 0:
            sentence = self._buffer[:best_pos].strip()
            self._buffer = self._buffer[best_pos:].lstrip()
            self._token_count = _count_tokens(self._buffer)
            return sentence if sentence else None

        return None

    def _force_flush(self) -> str:
        """Force flush at max_tokens, trying to break at a word boundary."""
        # Find last space before max
        words = self._buffer.split()
        if len(words) <= 1:
            text = self._buffer.strip()
            self._buffer = ""
            self._token_count = 0
            return text

        # Take ~max_tokens worth of words
        taken: list[str] = []
        for idx, word in enumerate(words):
            if idx >= self._max_tokens:
                break
            taken.append(word)

        text = " ".join(taken)
        remaining = " ".join(words[len(taken) :])
        self._buffer = remaining
        self._token_count = _count_tokens(remaining)
        return text


def _count_tokens(text: str) -> int:
    """Approximate token count (words). Good enough for boundary detection."""
    return len(text.split())
