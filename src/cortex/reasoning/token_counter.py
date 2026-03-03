"""Word-based token estimator for prompt budget calculation.

Uses ~1.3x word count as a conservative token estimate, matching the
pattern in sentence_detector.py. Good enough for budget estimation
on the AX8850 NPU with Qwen3 models.

The NPU processes prompts in p128 blocks (128-token blocks). The
aligned_tokens() helper rounds up to the next block boundary.
"""

from __future__ import annotations

# Empirical ratio: Qwen3 tokenizer produces ~1.3 tokens per whitespace word.
# Conservative (overestimates) to avoid exceeding the 2,047 hard limit.
TOKENS_PER_WORD = 1.3

# AX8850 processes prompts in blocks of this size
P128_BLOCK_SIZE = 128


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.

    Uses word count * 1.3 as a conservative approximation.
    Returns at least 1 for non-empty text.
    """
    if not text or not text.strip():
        return 0
    words = len(text.split())
    return max(1, int(words * TOKENS_PER_WORD + 0.5))


def aligned_tokens(token_count: int) -> int:
    """Round token count up to the next p128 block boundary.

    The AX8850 NPU evaluates prompts in 128-token blocks.
    This tells you the effective token cost of a prompt.
    """
    if token_count <= 0:
        return 0
    return ((token_count + P128_BLOCK_SIZE - 1) // P128_BLOCK_SIZE) * P128_BLOCK_SIZE
