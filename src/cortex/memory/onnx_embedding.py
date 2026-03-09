"""ONNX embedding service — real all-MiniLM-L6-v2 on CPU.

Loads an ONNX model and HuggingFace tokenizer from disk, tokenizes input
text, runs inference via onnxruntime, and returns normalized 384-dim vectors.
Uses asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
MAX_SEQ_LENGTH = 128  # MiniLM max sequence length


class OnnxEmbeddingService:
    """Real embedding service using all-MiniLM-L6-v2 ONNX model.

    Loads the model lazily on first embed call. Falls back gracefully
    if model files are not available.
    """

    def __init__(self, model_dir: str | Path) -> None:
        self._model_dir = Path(model_dir)
        self._session: Any = None
        self._tokenizer: Any = None
        self._loaded = False

    @property
    def dimensions(self) -> int:
        return EMBEDDING_DIM

    def _load(self) -> None:
        """Load ONNX model and tokenizer from disk."""
        if self._loaded:
            return

        model_path = self._model_dir / "model.onnx"
        tokenizer_path = self._model_dir / "tokenizer.json"

        if not model_path.exists():
            msg = f"ONNX model not found: {model_path}"
            raise FileNotFoundError(msg)
        if not tokenizer_path.exists():
            msg = f"Tokenizer not found: {tokenizer_path}"
            raise FileNotFoundError(msg)

        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=MAX_SEQ_LENGTH)
        self._tokenizer.enable_padding(length=MAX_SEQ_LENGTH)
        self._loaded = True
        logger.info("Loaded ONNX embedding model from %s", self._model_dir)

    def _embed_sync(self, text: str) -> NDArray[np.float32]:
        """Synchronous embed — called via asyncio.to_thread()."""
        self._load()

        encoding = self._tokenizer.encode(text)
        input_ids = np.array([encoding.ids], dtype=np.int64)
        attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        # Mean pooling over token embeddings (masked)
        token_embeddings = outputs[0]  # (1, seq_len, hidden_size)
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
        sum_mask = np.sum(mask_expanded, axis=1)
        sum_mask = np.clip(sum_mask, a_min=1e-9, a_max=None)
        mean_pooled = sum_embeddings / sum_mask

        # Normalize to unit vector
        vec: NDArray[np.float32] = mean_pooled[0].astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def _embed_batch_sync(self, texts: list[str]) -> list[NDArray[np.float32]]:
        """Synchronous batch embed."""
        return [self._embed_sync(t) for t in texts]

    async def embed(self, text: str) -> NDArray[np.float32]:
        """Embed text into a 384-dim normalized vector."""
        return await asyncio.to_thread(self._embed_sync, text)

    async def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        """Embed multiple texts."""
        return await asyncio.to_thread(self._embed_batch_sync, texts)
