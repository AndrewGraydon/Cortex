"""Tests for the text chunker."""

from __future__ import annotations

from cortex.knowledge.chunker import _estimate_tokens, _split_sentences, chunk_text


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert _estimate_tokens("") == 1  # max(1, ...)

    def test_single_word(self) -> None:
        assert _estimate_tokens("hello") >= 1

    def test_multiple_words(self) -> None:
        tokens = _estimate_tokens("the quick brown fox jumps")
        assert tokens >= 5  # at least word count


class TestSplitSentences:
    def test_single_sentence(self) -> None:
        result = _split_sentences("Hello world.")
        assert result == ["Hello world."]

    def test_multiple_sentences(self) -> None:
        result = _split_sentences("First sentence. Second sentence. Third one.")
        assert len(result) == 3

    def test_empty_string(self) -> None:
        result = _split_sentences("")
        assert result == []

    def test_no_punctuation(self) -> None:
        result = _split_sentences("no punctuation here")
        assert result == ["no punctuation here"]


class TestChunkText:
    def test_empty_text(self) -> None:
        assert chunk_text("") == []

    def test_whitespace_only(self) -> None:
        assert chunk_text("   \n  ") == []

    def test_short_text_single_chunk(self) -> None:
        text = "This is a short document."
        chunks = chunk_text(text, chunk_size_tokens=200)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_produces_multiple_chunks(self) -> None:
        # Generate text that exceeds one chunk
        sentences = [f"Sentence number {i} with some words." for i in range(50)]
        text = " ".join(sentences)
        chunks = chunk_text(text, chunk_size_tokens=50, overlap_tokens=10)
        assert len(chunks) > 1

    def test_overlap_maintains_context(self) -> None:
        sentences = [f"Sentence number {i} with extra words here." for i in range(30)]
        text = " ".join(sentences)
        chunks = chunk_text(text, chunk_size_tokens=30, overlap_tokens=10)
        if len(chunks) >= 2:
            # Last words of chunk N should appear in chunk N+1 (overlap)
            last_words_chunk0 = set(chunks[0].split()[-5:])
            first_words_chunk1 = set(chunks[1].split()[:10])
            assert last_words_chunk0 & first_words_chunk1  # Non-empty intersection

    def test_markdown_header_boundaries(self) -> None:
        text = "## Section One\nSome content here.\n## Section Two\nMore content here."
        chunks = chunk_text(text, chunk_size_tokens=200)
        # Should respect header boundaries (each section as separate chunk if small enough)
        assert len(chunks) >= 1
        # At least one chunk should contain "Section One"
        texts = " ".join(chunks)
        assert "Section One" in texts
        assert "Section Two" in texts

    def test_chunk_size_respected(self) -> None:
        sentences = [f"This is sentence {i} in the document." for i in range(100)]
        text = " ".join(sentences)
        chunks = chunk_text(text, chunk_size_tokens=50, overlap_tokens=10)
        for chunk in chunks:
            # Each chunk should be roughly within budget (allow some slack for sentence boundaries)
            tokens = _estimate_tokens(chunk)
            assert tokens <= 80  # generous upper bound (50 + overlap + sentence spillover)

    def test_no_duplicate_final_chunk(self) -> None:
        text = "Short text that fits in one chunk."
        chunks = chunk_text(text, chunk_size_tokens=200)
        assert len(chunks) == 1

    def test_preserves_all_content(self) -> None:
        words = [f"word{i}" for i in range(20)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size_tokens=200)
        combined = " ".join(chunks)
        for word in words:
            assert word in combined

    def test_custom_overlap(self) -> None:
        sentences = [f"Sentence {i} in the doc." for i in range(40)]
        text = " ".join(sentences)
        chunks_small_overlap = chunk_text(text, chunk_size_tokens=40, overlap_tokens=5)
        chunks_large_overlap = chunk_text(text, chunk_size_tokens=40, overlap_tokens=20)
        # Larger overlap should produce more chunks (more repeated content)
        assert len(chunks_large_overlap) >= len(chunks_small_overlap)
