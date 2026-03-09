"""Tests for the document ingester."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from numpy.typing import NDArray

from cortex.knowledge.ingester import SUPPORTED_FORMATS, DocumentIngester, extract_text
from cortex.knowledge.store import KnowledgeStore


class MockEmbedder:
    """Minimal mock embedder for ingester tests."""

    @property
    def dimensions(self) -> int:
        return 384

    async def embed(self, text: str) -> NDArray[np.float32]:
        rng = np.random.default_rng(hash(text) % (2**31))
        vec = rng.standard_normal(384).astype(np.float32)
        return vec / np.linalg.norm(vec)

    async def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        return [await self.embed(t) for t in texts]


@pytest.fixture
async def store() -> KnowledgeStore:
    s = KnowledgeStore(db_path=":memory:")
    await s.start()
    yield s  # type: ignore[misc]
    await s.stop()


@pytest.fixture
def embedder() -> MockEmbedder:
    return MockEmbedder()


@pytest.fixture
def ingester(store: KnowledgeStore, embedder: MockEmbedder) -> DocumentIngester:
    return DocumentIngester(store=store, embedder=embedder)


class TestSupportedFormats:
    def test_txt_supported(self) -> None:
        assert "txt" in SUPPORTED_FORMATS

    def test_md_supported(self) -> None:
        assert "md" in SUPPORTED_FORMATS

    def test_pdf_supported(self) -> None:
        assert "pdf" in SUPPORTED_FORMATS

    def test_html_supported(self) -> None:
        assert "html" in SUPPORTED_FORMATS


class TestExtractText:
    async def test_extract_txt(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("Hello world")
        text = await extract_text(f)
        assert text == "Hello world"

    async def test_extract_md(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Title\nContent here.")
        text = await extract_text(f)
        assert "Title" in text
        assert "Content here." in text

    async def test_extract_html(self, tmp_path: Path) -> None:
        f = tmp_path / "test.html"
        f.write_text("<html><body><h1>Title</h1><p>Paragraph.</p></body></html>")
        text = await extract_text(f)
        assert "Title" in text
        assert "Paragraph." in text

    async def test_extract_html_strips_scripts(self, tmp_path: Path) -> None:
        f = tmp_path / "test.html"
        f.write_text("<html><script>var x=1;</script><body>Content</body></html>")
        text = await extract_text(f)
        assert "var x=1" not in text
        assert "Content" in text

    async def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_text("data")
        with pytest.raises(ValueError, match="Unsupported format"):
            await extract_text(f)

    async def test_extract_pdf_mocked(self, tmp_path: Path) -> None:
        f = tmp_path / "test.pdf"
        f.write_bytes(b"fake pdf data")

        mock_page = type("MockPage", (), {"extract_text": lambda self: "PDF content here"})()
        mock_reader = type("MockReader", (), {"pages": [mock_page]})()

        with patch("pypdf.PdfReader", return_value=mock_reader):
            text = await extract_text(f)
            assert "PDF content here" in text


class TestIngestText:
    async def test_ingest_text_creates_document(
        self, ingester: DocumentIngester, store: KnowledgeStore
    ) -> None:
        doc = await ingester.ingest_text("Some document content here.", title="Test")
        assert doc.title == "Test"
        assert doc.chunk_count >= 1
        assert await store.document_count() == 1

    async def test_ingest_text_creates_chunks(
        self, ingester: DocumentIngester, store: KnowledgeStore
    ) -> None:
        await ingester.ingest_text("A short document.", title="Short")
        assert await store.chunk_count() >= 1

    async def test_ingest_empty_text_raises(self, ingester: DocumentIngester) -> None:
        with pytest.raises(ValueError, match="empty"):
            await ingester.ingest_text("", title="Empty")

    async def test_ingest_whitespace_raises(self, ingester: DocumentIngester) -> None:
        with pytest.raises(ValueError, match="empty"):
            await ingester.ingest_text("   \n  ", title="Whitespace")

    async def test_ingest_preserves_format(self, ingester: DocumentIngester) -> None:
        doc = await ingester.ingest_text("Content", title="HTML Doc", format="html")
        assert doc.format == "html"


class TestIngestFile:
    async def test_ingest_txt_file(
        self, ingester: DocumentIngester, store: KnowledgeStore, tmp_path: Path
    ) -> None:
        f = tmp_path / "readme.txt"
        f.write_text("This is a readme file with some content.")
        doc = await ingester.ingest_file(f)
        assert doc.title == "readme"
        assert await store.document_count() == 1

    async def test_ingest_md_file(self, ingester: DocumentIngester, tmp_path: Path) -> None:
        f = tmp_path / "notes.md"
        f.write_text("# Notes\nSome notes here.")
        doc = await ingester.ingest_file(f)
        assert doc.title == "notes"
        assert doc.format == "md"

    async def test_ingest_custom_title(self, ingester: DocumentIngester, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("Data content here.")
        doc = await ingester.ingest_file(f, title="Custom Title")
        assert doc.title == "Custom Title"

    async def test_unsupported_format_raises(
        self, ingester: DocumentIngester, tmp_path: Path
    ) -> None:
        f = tmp_path / "data.xyz"
        f.write_text("data")
        with pytest.raises(ValueError, match="Unsupported format"):
            await ingester.ingest_file(f)


class TestIngestDirectory:
    async def test_ingest_empty_directory(self, ingester: DocumentIngester, tmp_path: Path) -> None:
        docs = await ingester.ingest_directory(tmp_path)
        assert docs == []

    async def test_ingest_nonexistent_directory(self, ingester: DocumentIngester) -> None:
        docs = await ingester.ingest_directory(Path("/nonexistent"))
        assert docs == []

    async def test_ingest_directory_with_files(
        self, ingester: DocumentIngester, store: KnowledgeStore, tmp_path: Path
    ) -> None:
        (tmp_path / "a.txt").write_text("File A content.")
        (tmp_path / "b.md").write_text("# File B\nContent.")
        (tmp_path / "c.xyz").write_text("Unsupported")  # Should be skipped
        docs = await ingester.ingest_directory(tmp_path)
        assert len(docs) == 2
        assert await store.document_count() == 2

    async def test_ingest_directory_skips_errors(
        self, ingester: DocumentIngester, tmp_path: Path
    ) -> None:
        (tmp_path / "good.txt").write_text("Good content.")
        (tmp_path / "empty.txt").write_text("")  # Will produce empty text
        # empty.txt will raise ValueError but should be caught
        docs = await ingester.ingest_directory(tmp_path)
        assert len(docs) == 1
