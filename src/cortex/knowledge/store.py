"""Knowledge store — SQLite-backed document chunk storage with cosine search.

Stores document metadata and embedded chunks. Search uses brute-force
numpy cosine similarity (same pattern as SqliteMemoryStore).
"""

from __future__ import annotations

import logging

import aiosqlite
import numpy as np
from numpy.typing import NDArray

from cortex.knowledge.types import Document, DocumentChunk, KnowledgeSearchResult

logger = logging.getLogger(__name__)

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_path TEXT DEFAULT '',
    format TEXT DEFAULT 'txt',
    ingested_at REAL NOT NULL,
    chunk_count INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,
    token_count INTEGER DEFAULT 0,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
"""


class KnowledgeStore:
    """SQLite-backed knowledge store for document chunks."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def start(self) -> None:
        """Open the database and create tables."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(CREATE_TABLES)
        await self._db.commit()

    async def stop(self) -> None:
        """Close the database."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _ensure_started(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "KnowledgeStore not started — call start() first"
            raise RuntimeError(msg)
        return self._db

    async def add_document(self, doc: Document, chunks: list[DocumentChunk]) -> None:
        """Store a document and its chunks."""
        db = self._ensure_started()
        import json

        await db.execute(
            "INSERT OR REPLACE INTO documents "
            "(id, title, source_path, format, ingested_at, chunk_count, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                doc.id,
                doc.title,
                doc.source_path,
                doc.format,
                doc.ingested_at,
                len(chunks),
                json.dumps(doc.metadata),
            ),
        )

        for chunk in chunks:
            embedding_blob = chunk.embedding.tobytes() if chunk.embedding is not None else None
            await db.execute(
                "INSERT OR REPLACE INTO chunks "
                "(id, document_id, chunk_index, content, embedding, token_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    chunk.id,
                    doc.id,
                    chunk.chunk_index,
                    chunk.content,
                    embedding_blob,
                    chunk.token_count,
                ),
            )

        await db.commit()
        logger.info("Stored document '%s' with %d chunks", doc.title, len(chunks))

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document and its chunks. Returns True if found."""
        db = self._ensure_started()
        cursor = await db.execute("SELECT id FROM documents WHERE id = ?", (doc_id,))
        if await cursor.fetchone() is None:
            return False
        # Foreign key cascade deletes chunks
        await db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        await db.commit()
        return True

    async def list_documents(self) -> list[Document]:
        """List all stored documents."""
        db = self._ensure_started()
        import json

        cursor = await db.execute(
            "SELECT id, title, source_path, format, ingested_at, chunk_count, "
            "metadata_json FROM documents ORDER BY ingested_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            Document(
                id=str(row[0]),
                title=str(row[1]),
                source_path=str(row[2]),
                format=str(row[3]),
                ingested_at=float(str(row[4])),
                chunk_count=int(str(row[5])),
                metadata=json.loads(str(row[6])) if row[6] else {},
            )
            for row in rows
        ]

    async def document_count(self) -> int:
        """Count stored documents."""
        db = self._ensure_started()
        cursor = await db.execute("SELECT COUNT(*) FROM documents")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def chunk_count(self) -> int:
        """Count stored chunks across all documents."""
        db = self._ensure_started()
        cursor = await db.execute("SELECT COUNT(*) FROM chunks")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def search(
        self,
        embedding: NDArray[np.float32],
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[KnowledgeSearchResult]:
        """Search chunks by cosine similarity (brute-force numpy).

        Loads all chunk embeddings and computes cosine similarity.
        Efficient enough for <50K chunks.
        """
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT c.id, c.document_id, c.chunk_index, c.content, c.embedding, "
            "c.token_count, d.title "
            "FROM chunks c JOIN documents d ON c.document_id = d.id "
            "WHERE c.embedding IS NOT NULL"
        )
        rows = await cursor.fetchall()
        if not rows:
            return []

        query_norm = float(np.linalg.norm(embedding))
        if query_norm == 0:
            return []

        results: list[KnowledgeSearchResult] = []
        for row in rows:
            embedding_blob: bytes = row[4]
            chunk_embedding = np.frombuffer(embedding_blob, dtype=np.float32).copy()
            chunk_norm = float(np.linalg.norm(chunk_embedding))
            if chunk_norm == 0:
                continue
            sim = float(np.dot(embedding, chunk_embedding) / (query_norm * chunk_norm))
            if sim >= threshold:
                chunk = DocumentChunk(
                    id=str(row[0]),
                    document_id=str(row[1]),
                    chunk_index=int(str(row[2])),
                    content=str(row[3]),
                    embedding=chunk_embedding,
                    token_count=int(str(row[5])),
                )
                results.append(
                    KnowledgeSearchResult(
                        chunk=chunk,
                        similarity=sim,
                        document_title=str(row[6]),
                    )
                )

        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_k]

    async def get_document(self, doc_id: str) -> Document | None:
        """Get a single document by ID."""
        db = self._ensure_started()
        import json

        cursor = await db.execute(
            "SELECT id, title, source_path, format, ingested_at, chunk_count, "
            "metadata_json FROM documents WHERE id = ?",
            (doc_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Document(
            id=str(row[0]),
            title=str(row[1]),
            source_path=str(row[2]),
            format=str(row[3]),
            ingested_at=float(str(row[4])),
            chunk_count=int(str(row[5])),
            metadata=json.loads(str(row[6])) if row[6] else {},
        )
