"""Text chunker — splits documents into overlapping segments for RAG.

Produces ~200-token chunks with 50-token overlap. Respects sentence
and markdown header boundaries where possible.
"""

from __future__ import annotations

import re


def _estimate_tokens(text: str) -> int:
    """Quick word-based token estimate (~1.3x word count)."""
    return max(1, int(len(text.split()) * 1.3))


def chunk_text(
    text: str,
    chunk_size_tokens: int = 200,
    overlap_tokens: int = 50,
) -> list[str]:
    """Split text into overlapping chunks.

    Strategy:
    1. Split on markdown headers (##) as hard boundaries
    2. Within each section, split into ~chunk_size_tokens segments
    3. Overlap by ~overlap_tokens to maintain context continuity

    Returns list of chunk strings (never empty for non-empty input).
    """
    if not text.strip():
        return []

    # Split on markdown headers (keep headers with their following content)
    sections = _split_on_headers(text)
    chunks: list[str] = []

    for section in sections:
        section_chunks = _chunk_section(section, chunk_size_tokens, overlap_tokens)
        chunks.extend(section_chunks)

    return chunks


def _split_on_headers(text: str) -> list[str]:
    """Split text at markdown header lines (## or ###)."""
    parts = re.split(r"(?=^#{2,}\s)", text, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def _chunk_section(
    section: str,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Chunk a single section into overlapping segments."""
    # Split into sentences for cleaner boundaries
    sentences = _split_sentences(section)
    if not sentences:
        return []

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = _estimate_tokens(sentence)

        # If adding this sentence would exceed the chunk size
        if current_tokens + sentence_tokens > chunk_size_tokens and current_sentences:
            chunks.append(" ".join(current_sentences))

            # Keep overlap: walk back from end keeping ~overlap_tokens
            overlap_sents: list[str] = []
            overlap_tok = 0
            for s in reversed(current_sentences):
                t = _estimate_tokens(s)
                if overlap_tok + t > overlap_tokens:
                    break
                overlap_sents.insert(0, s)
                overlap_tok += t

            current_sentences = overlap_sents
            current_tokens = overlap_tok

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    # Flush remaining
    if current_sentences:
        text = " ".join(current_sentences)
        # Avoid duplicate of last chunk
        if not chunks or text != chunks[-1]:
            chunks.append(text)

    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences (simple regex-based)."""
    # Split on sentence-ending punctuation followed by space or newline
    raw = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in raw if s.strip()]
