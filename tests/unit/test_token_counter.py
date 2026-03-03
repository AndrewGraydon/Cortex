"""Tests for word-based token estimator."""

from __future__ import annotations

from cortex.reasoning.token_counter import (
    P128_BLOCK_SIZE,
    aligned_tokens,
    estimate_tokens,
)


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_whitespace_only(self) -> None:
        assert estimate_tokens("   ") == 0

    def test_single_word(self) -> None:
        assert estimate_tokens("hello") >= 1

    def test_short_sentence(self) -> None:
        tokens = estimate_tokens("Hello world")
        # 2 words * 1.3 = 2.6, rounded = 3
        assert tokens == 3

    def test_medium_sentence(self) -> None:
        tokens = estimate_tokens("The quick brown fox jumps over the lazy dog")
        # 9 words * 1.3 = 11.7, rounded = 12
        assert tokens == 12

    def test_system_prompt_estimate(self) -> None:
        prompt = (
            "You are Cortex, a helpful voice assistant running locally "
            "on a Raspberry Pi.\n\nGuidelines:\n- Be concise and friendly\n"
            "- Keep responses under 50 words when possible"
        )
        tokens = estimate_tokens(prompt)
        # Should be roughly 25-35 tokens (conservative)
        assert 20 <= tokens <= 40

    def test_conservative_overestimate(self) -> None:
        # The estimator should overestimate to stay safe
        text = "set a timer for five minutes"
        tokens = estimate_tokens(text)
        # 6 words * 1.3 = 7.8 → 8
        assert tokens >= 6  # At least word count

    def test_tool_call_markup(self) -> None:
        text = '<tool_call>{"name": "clock", "arguments": {}}</tool_call>'
        tokens = estimate_tokens(text)
        # Even though this is 4 "words", the markup counts
        assert tokens >= 1


class TestAlignedTokens:
    def test_zero(self) -> None:
        assert aligned_tokens(0) == 0

    def test_exact_block(self) -> None:
        assert aligned_tokens(128) == 128

    def test_round_up(self) -> None:
        assert aligned_tokens(1) == 128
        assert aligned_tokens(100) == 128
        assert aligned_tokens(129) == 256

    def test_large_value(self) -> None:
        assert aligned_tokens(800) == 896  # 7 * 128

    def test_max_context(self) -> None:
        # 2047 tokens → 16 * 128 = 2048
        assert aligned_tokens(2047) == 2048

    def test_block_size_constant(self) -> None:
        assert P128_BLOCK_SIZE == 128
