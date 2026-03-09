"""Document ingester — reads files, chunks, embeds, and stores in knowledge base."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cortex.knowledge.chunker import chunk_text
from cortex.knowledge.types import Document, DocumentChunk

logger = logging.getLogger(__name__)

# Supported formats and their text extractors
SUPPORTED_FORMATS = {"txt", "md", "pdf", "html"}


async def extract_text(path: Path) -> str:
    """Extract plain text from a file based on its extension."""
    suffix = path.suffix.lower().lstrip(".")

    if suffix in ("txt", "md"):
        return path.read_text(encoding="utf-8", errors="replace")

    if suffix == "html":
        return _extract_html(path)

    if suffix == "pdf":
        return _extract_pdf(path)

    msg = f"Unsupported format: {suffix}"
    raise ValueError(msg)


def _extract_html(path: Path) -> str:
    """Extract text from HTML using BeautifulSoup."""
    from bs4 import BeautifulSoup

    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style elements
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _extract_pdf(path: Path) -> str:
    """Extract text from PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


class DocumentIngester:
    """Ingests documents: extract text → chunk → embed → store."""

    def __init__(
        self,
        store: Any,  # KnowledgeStore
        embedder: Any,  # EmbeddingService
        chunk_size_tokens: int = 200,
        chunk_overlap_tokens: int = 50,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._chunk_size = chunk_size_tokens
        self._overlap = chunk_overlap_tokens

    async def ingest_file(
        self,
        path: Path,
        title: str | None = None,
    ) -> Document:
        """Ingest a file into the knowledge store."""
        suffix = path.suffix.lower().lstrip(".")
        if suffix not in SUPPORTED_FORMATS:
            msg = f"Unsupported format: {suffix}"
            raise ValueError(msg)

        text = await extract_text(path)
        doc_title = title or path.stem
        return await self.ingest_text(text, title=doc_title, format=suffix, source_path=str(path))

    async def ingest_text(
        self,
        text: str,
        title: str,
        format: str = "txt",
        source_path: str = "",
    ) -> Document:
        """Ingest raw text into the knowledge store."""
        if not text.strip():
            msg = "Cannot ingest empty text"
            raise ValueError(msg)

        # Chunk
        chunk_texts = chunk_text(text, self._chunk_size, self._overlap)
        if not chunk_texts:
            msg = "Text produced no chunks"
            raise ValueError(msg)

        # Embed
        embeddings = await self._embedder.embed_batch(chunk_texts)

        # Build document and chunks
        doc = Document(
            title=title,
            source_path=source_path,
            format=format,
            chunk_count=len(chunk_texts),
        )

        chunks: list[DocumentChunk] = []
        for i, (ct, emb) in enumerate(zip(chunk_texts, embeddings, strict=True)):
            chunks.append(
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    content=ct,
                    embedding=emb,
                    token_count=max(1, int(len(ct.split()) * 1.3)),
                )
            )

        # Store
        await self._store.add_document(doc, chunks)
        logger.info("Ingested '%s' (%s): %d chunks", title, format, len(chunks))
        return doc

    async def ingest_directory(self, directory: Path) -> list[Document]:
        """Ingest all supported files from a directory."""
        docs: list[Document] = []
        if not directory.exists():
            return docs
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower().lstrip(".") in SUPPORTED_FORMATS:
                try:
                    doc = await self.ingest_file(path)
                    docs.append(doc)
                except Exception:
                    logger.exception("Failed to ingest %s", path)
        return docs
