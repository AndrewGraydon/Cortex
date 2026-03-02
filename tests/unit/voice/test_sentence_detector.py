"""Tests for sentence boundary detector."""

from __future__ import annotations

from cortex.voice.sentence_detector import SentenceDetector


class TestBasicSentences:
    def test_single_sentence(self) -> None:
        sd = SentenceDetector(min_tokens=3)
        # Feed word by word
        assert sd.feed("Hello, ") == []
        assert sd.feed("how ") == []
        assert sd.feed("are ") == []
        result = sd.feed("you? ")
        assert len(result) == 1
        assert result[0] == "Hello, how are you?"

    def test_two_sentences(self) -> None:
        sd = SentenceDetector(min_tokens=2)
        text = "Hello world. How are you? "
        sentences = sd.feed(text)
        # Should get at least the first sentence
        assert len(sentences) >= 1
        remaining = sd.flush()
        total = " ".join(sentences) + (" " + remaining if remaining else "")
        assert "Hello world." in total

    def test_period_triggers_flush(self) -> None:
        sd = SentenceDetector(min_tokens=2)
        sentences = sd.feed("This is a test. ")
        assert len(sentences) == 1
        assert sentences[0] == "This is a test."

    def test_exclamation_triggers_flush(self) -> None:
        sd = SentenceDetector(min_tokens=2)
        sentences = sd.feed("What a day! ")
        assert len(sentences) == 1
        assert sentences[0] == "What a day!"

    def test_question_triggers_flush(self) -> None:
        sd = SentenceDetector(min_tokens=2)
        sentences = sd.feed("How are you? ")
        assert len(sentences) == 1
        assert sentences[0] == "How are you?"


class TestMinimumTokens:
    def test_below_minimum_not_flushed(self) -> None:
        sd = SentenceDetector(min_tokens=8)
        # Short sentence below threshold
        sentences = sd.feed("Hi. ")
        assert sentences == []
        # Flush forces it out
        remaining = sd.flush()
        assert remaining == "Hi."

    def test_minimum_respected(self) -> None:
        sd = SentenceDetector(min_tokens=4)
        sentences = sd.feed("A. B. ")
        # These are too short individually
        assert sentences == []


class TestMaximumTokens:
    def test_max_forces_flush(self) -> None:
        sd = SentenceDetector(min_tokens=2, max_tokens=5)
        # Feed more than max_tokens without a sentence boundary
        long_text = "word " * 6
        sentences = sd.feed(long_text)
        assert len(sentences) >= 1
        # Should have broken the text up
        total_words = sum(len(s.split()) for s in sentences) + len(sd.flush().split())
        assert total_words == 6


class TestSecondaryBoundaries:
    def test_colon_triggers(self) -> None:
        sd = SentenceDetector(min_tokens=2)
        sentences = sd.feed("Here is the list: one two three. ")
        assert len(sentences) >= 1

    def test_semicolon_triggers(self) -> None:
        sd = SentenceDetector(min_tokens=2)
        sentences = sd.feed("First thing done; now the second. ")
        assert len(sentences) >= 1


class TestFlush:
    def test_flush_returns_remaining(self) -> None:
        sd = SentenceDetector(min_tokens=8)
        sd.feed("This is some text without")
        remaining = sd.flush()
        assert remaining == "This is some text without"

    def test_flush_clears_buffer(self) -> None:
        sd = SentenceDetector()
        sd.feed("some text")
        sd.flush()
        assert sd.flush() == ""

    def test_empty_flush(self) -> None:
        sd = SentenceDetector()
        assert sd.flush() == ""


class TestReset:
    def test_reset_clears_state(self) -> None:
        sd = SentenceDetector()
        sd.feed("some text")
        sd.reset()
        assert sd.flush() == ""


class TestStreamingTokens:
    def test_token_by_token_streaming(self) -> None:
        """Simulate LLM streaming one word at a time."""
        sd = SentenceDetector(min_tokens=3)
        words = "The weather is nice today. Would you like to go outside? "
        all_sentences: list[str] = []

        for word in words.split():
            sentences = sd.feed(word + " ")
            all_sentences.extend(sentences)

        remaining = sd.flush()
        if remaining:
            all_sentences.append(remaining)

        # Should have detected at least 2 sentences
        assert len(all_sentences) >= 2
        full = " ".join(all_sentences)
        assert "nice today." in full
        assert "outside?" in full
