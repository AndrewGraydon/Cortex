"""Tests for ONNX embedding service.

Unit tests use mock patterns since the real 22MB model file
is not available in CI. Tests validate construction, error handling,
and the sync/async wrapper pattern.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from cortex.memory.onnx_embedding import EMBEDDING_DIM, OnnxEmbeddingService


class TestConstruction:
    def test_create_with_string_path(self) -> None:
        svc = OnnxEmbeddingService(model_dir="/some/path")
        assert svc.dimensions == EMBEDDING_DIM

    def test_create_with_path_object(self) -> None:
        svc = OnnxEmbeddingService(model_dir=Path("/some/path"))
        assert svc.dimensions == EMBEDDING_DIM

    def test_not_loaded_initially(self) -> None:
        svc = OnnxEmbeddingService(model_dir="/nonexistent")
        assert svc._loaded is False

    def test_dimensions_constant(self) -> None:
        assert EMBEDDING_DIM == 384


class TestMissingModel:
    async def test_embed_raises_on_missing_model(self) -> None:
        svc = OnnxEmbeddingService(model_dir="/nonexistent/path")
        with pytest.raises(FileNotFoundError, match="ONNX model not found"):
            await svc.embed("hello")

    async def test_embed_raises_on_missing_tokenizer(self, tmp_path: Path) -> None:
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake")
        svc = OnnxEmbeddingService(model_dir=tmp_path)
        with pytest.raises(FileNotFoundError, match="Tokenizer not found"):
            await svc.embed("hello")


class TestWithMockedOnnx:
    """Tests using mocked onnxruntime and tokenizers."""

    def _make_mock_session(self) -> MagicMock:
        session = MagicMock()
        # Simulate (1, seq_len, hidden_size) output
        output = (
            np.random.default_rng(42).standard_normal((1, 128, EMBEDDING_DIM)).astype(np.float32)
        )
        session.run.return_value = [output]
        return session

    def _make_mock_tokenizer(self) -> MagicMock:
        tokenizer = MagicMock()
        encoding = MagicMock()
        encoding.ids = list(range(128))
        encoding.attention_mask = [1] * 10 + [0] * 118
        tokenizer.encode.return_value = encoding
        return tokenizer

    @patch("cortex.memory.onnx_embedding.OnnxEmbeddingService._load")
    async def test_embed_returns_correct_shape(self, mock_load: MagicMock) -> None:
        svc = OnnxEmbeddingService(model_dir="/fake")
        svc._loaded = True
        svc._session = self._make_mock_session()
        svc._tokenizer = self._make_mock_tokenizer()

        vec = await svc.embed("test text")
        assert vec.shape == (EMBEDDING_DIM,)
        assert vec.dtype == np.float32

    @patch("cortex.memory.onnx_embedding.OnnxEmbeddingService._load")
    async def test_embed_is_normalized(self, mock_load: MagicMock) -> None:
        svc = OnnxEmbeddingService(model_dir="/fake")
        svc._loaded = True
        svc._session = self._make_mock_session()
        svc._tokenizer = self._make_mock_tokenizer()

        vec = await svc.embed("test")
        norm = float(np.linalg.norm(vec))
        assert abs(norm - 1.0) < 1e-5

    @patch("cortex.memory.onnx_embedding.OnnxEmbeddingService._load")
    async def test_embed_batch(self, mock_load: MagicMock) -> None:
        svc = OnnxEmbeddingService(model_dir="/fake")
        svc._loaded = True
        svc._session = self._make_mock_session()
        svc._tokenizer = self._make_mock_tokenizer()

        vecs = await svc.embed_batch(["hello", "world", "test"])
        assert len(vecs) == 3
        for v in vecs:
            assert v.shape == (EMBEDDING_DIM,)

    @patch("cortex.memory.onnx_embedding.OnnxEmbeddingService._load")
    async def test_embed_deterministic_given_same_model(self, mock_load: MagicMock) -> None:
        svc = OnnxEmbeddingService(model_dir="/fake")
        svc._loaded = True
        svc._session = self._make_mock_session()
        svc._tokenizer = self._make_mock_tokenizer()

        v1 = await svc.embed("same text")
        v2 = await svc.embed("same text")
        np.testing.assert_array_almost_equal(v1, v2, decimal=5)

    @patch("cortex.memory.onnx_embedding.OnnxEmbeddingService._load")
    async def test_mean_pooling_uses_attention_mask(self, mock_load: MagicMock) -> None:
        """Verify mean pooling respects the attention mask."""
        svc = OnnxEmbeddingService(model_dir="/fake")
        svc._loaded = True

        session = MagicMock()
        # Create output where padding tokens have distinct values
        output = np.zeros((1, 128, EMBEDDING_DIM), dtype=np.float32)
        output[0, :10, :] = 1.0  # Real tokens
        output[0, 10:, :] = 999.0  # Padding (should be masked)
        session.run.return_value = [output]

        tokenizer = MagicMock()
        encoding = MagicMock()
        encoding.ids = list(range(128))
        encoding.attention_mask = [1] * 10 + [0] * 118
        tokenizer.encode.return_value = encoding

        svc._session = session
        svc._tokenizer = tokenizer

        vec = await svc.embed("test")
        # Mean of 10 tokens of value 1.0 should give ~1.0 before normalization
        # After normalization, each dim should be ~1/sqrt(384)
        expected_component = 1.0 / np.sqrt(EMBEDDING_DIM)
        assert abs(float(vec[0]) - expected_component) < 1e-4


class TestLoadBehavior:
    def test_load_is_lazy(self) -> None:
        svc = OnnxEmbeddingService(model_dir="/nonexistent")
        assert svc._loaded is False
        assert svc._session is None
        assert svc._tokenizer is None

    def test_load_sets_loaded_flag(self, tmp_path: Path) -> None:
        """Verify _load() would set the flag (we can't fully test without real model)."""
        svc = OnnxEmbeddingService(model_dir=tmp_path)
        # Without model files, _load() raises
        with pytest.raises(FileNotFoundError):
            svc._load()
        assert svc._loaded is False

    def test_load_idempotent_when_loaded(self) -> None:
        svc = OnnxEmbeddingService(model_dir="/fake")
        svc._loaded = True
        svc._session = MagicMock()
        svc._tokenizer = MagicMock()
        # Should return immediately without error
        svc._load()
        assert svc._loaded is True
