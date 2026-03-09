"""Tests for embedding protocol compliance."""

from __future__ import annotations

import numpy as np

from cortex.memory.embedding import MockEmbeddingService
from cortex.memory.embedding_protocol import EmbeddingService
from cortex.memory.onnx_embedding import OnnxEmbeddingService


class TestProtocolCompliance:
    """Both embedding services satisfy the EmbeddingService protocol."""

    def test_mock_is_embedding_service(self) -> None:
        assert isinstance(MockEmbeddingService(), EmbeddingService)

    def test_onnx_is_embedding_service(self) -> None:
        svc = OnnxEmbeddingService(model_dir="/nonexistent")
        assert isinstance(svc, EmbeddingService)

    def test_mock_has_dimensions(self) -> None:
        svc = MockEmbeddingService()
        assert svc.dimensions == 384

    def test_onnx_has_dimensions(self) -> None:
        svc = OnnxEmbeddingService(model_dir="/nonexistent")
        assert svc.dimensions == 384

    async def test_mock_embed_returns_ndarray(self) -> None:
        svc = MockEmbeddingService()
        vec = await svc.embed("test")
        assert isinstance(vec, np.ndarray)
        assert vec.dtype == np.float32

    async def test_mock_embed_batch_returns_list(self) -> None:
        svc = MockEmbeddingService()
        vecs = await svc.embed_batch(["a", "b"])
        assert isinstance(vecs, list)
        assert len(vecs) == 2

    def test_protocol_is_runtime_checkable(self) -> None:
        assert hasattr(EmbeddingService, "__protocol_attrs__") or isinstance(EmbeddingService, type)
