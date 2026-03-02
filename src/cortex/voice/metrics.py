"""Voice pipeline metrics — logging and tracking."""

from __future__ import annotations

import logging

from cortex.voice.types import LatencyMetrics

logger = logging.getLogger(__name__)


def log_metrics(metrics: LatencyMetrics) -> None:
    """Log latency metrics for a voice interaction."""
    logger.info(
        "Voice metrics | ASR: %.0fms | Prefill: %.0fms | TTS: %.0fms | TTFA: %.0fms",
        metrics.asr_latency_ms,
        metrics.llm_prefill_ms,
        metrics.tts_chunk_ms,
        metrics.ttfa_ms,
    )
