"""SQLite-backed memory store — short-term conversation summaries + long-term facts.

Uses aiosqlite for async SQLite access. Embedding search uses brute-force
numpy cosine similarity (sufficient for <10K entries). sqlite-vec can be
added later for hardware-accelerated search if needed.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import aiosqlite
import numpy as np
from numpy.typing import NDArray

from cortex.memory.types import (
    ConversationSummary,
    MemoryCategory,
    MemoryEntry,
    SearchResult,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL,
    summary TEXT NOT NULL,
    turn_count INTEGER DEFAULT 0,
    topics TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_conversations_ended
    ON conversations(ended_at DESC);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    embedding BLOB,
    source_conversation TEXT,
    confidence REAL DEFAULT 1.0,
    created_at REAL NOT NULL,
    last_referenced REAL DEFAULT 0.0,
    superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_created ON facts(created_at DESC);
"""


class SqliteMemoryStore:
    """Persistent memory with SQLite — conversations + facts with embeddings."""

    def __init__(self, db_path: str = "data/memory.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def start(self) -> None:
        """Open database, create tables, and run migrations."""
        from cortex.memory.migration import run_migrations

        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(CREATE_TABLES)
        # Set schema version if not present
        cursor = await self._db.execute("SELECT COUNT(*) FROM schema_version")
        row = await cursor.fetchone()
        if row and row[0] == 0:
            await self._db.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (1,),
            )
            await self._db.commit()
        # Run any pending migrations (v1 → v2, etc.)
        await run_migrations(self._db, SCHEMA_VERSION)

    async def stop(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _ensure_started(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "MemoryStore not started"
            raise RuntimeError(msg)
        return self._db

    # --- Conversation summaries (short-term) ---

    async def save_conversation(self, summary: ConversationSummary) -> None:
        """Save a completed conversation summary."""
        db = self._ensure_started()
        await db.execute(
            """INSERT OR REPLACE INTO conversations
               (id, started_at, ended_at, summary, turn_count, topics)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                summary.id,
                summary.started_at,
                summary.ended_at,
                summary.summary,
                summary.turn_count,
                json.dumps(summary.topics),
            ),
        )
        await db.commit()

    async def get_recent_conversations(self, limit: int = 10) -> list[ConversationSummary]:
        """Retrieve recent conversation summaries, newest first."""
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT id, started_at, ended_at, summary, turn_count, topics "
            "FROM conversations ORDER BY ended_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            ConversationSummary(
                id=row[0],
                started_at=row[1],
                ended_at=row[2],
                summary=row[3],
                turn_count=row[4],
                topics=json.loads(row[5]) if row[5] else [],
            )
            for row in rows
        ]

    async def conversation_count(self) -> int:
        """Count stored conversations."""
        db = self._ensure_started()
        cursor = await db.execute("SELECT COUNT(*) FROM conversations")
        row = await cursor.fetchone()
        return row[0] if row else 0

    # --- Long-term facts ---

    async def save_fact(self, entry: MemoryEntry) -> None:
        """Save a fact to long-term memory."""
        db = self._ensure_started()
        embedding_blob = entry.embedding.tobytes() if entry.embedding is not None else None
        await db.execute(
            """INSERT OR REPLACE INTO facts
               (id, content, category, embedding, source_conversation,
                confidence, created_at, last_referenced, superseded_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id,
                entry.content,
                entry.category.value,
                embedding_blob,
                entry.source_conversation,
                entry.confidence,
                entry.created_at,
                entry.last_referenced,
                entry.superseded_by,
            ),
        )
        await db.commit()

    async def get_all_facts(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
        """Retrieve all facts, optionally filtered by category."""
        db = self._ensure_started()
        if category is not None:
            cursor = await db.execute(
                "SELECT id, content, category, embedding, source_conversation, "
                "confidence, created_at, last_referenced, superseded_by "
                "FROM facts WHERE category = ? AND superseded_by IS NULL "
                "ORDER BY created_at DESC",
                (category.value,),
            )
        else:
            cursor = await db.execute(
                "SELECT id, content, category, embedding, source_conversation, "
                "confidence, created_at, last_referenced, superseded_by "
                "FROM facts WHERE superseded_by IS NULL "
                "ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [self._row_to_entry(tuple(row)) for row in rows]

    async def fact_count(self) -> int:
        """Count stored facts."""
        db = self._ensure_started()
        cursor = await db.execute("SELECT COUNT(*) FROM facts WHERE superseded_by IS NULL")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def search(
        self,
        embedding: NDArray[np.float32],
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[SearchResult]:
        """Search facts by cosine similarity (brute-force numpy).

        Loads all embeddings into memory and computes cosine similarity.
        Efficient enough for <10K entries. For larger stores, use sqlite-vec.
        """
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT id, content, category, embedding, source_conversation, "
            "confidence, created_at, last_referenced, superseded_by "
            "FROM facts WHERE embedding IS NOT NULL AND superseded_by IS NULL"
        )
        rows = await cursor.fetchall()
        if not rows:
            return []

        results: list[SearchResult] = []
        query_norm = np.linalg.norm(embedding)
        if query_norm == 0:
            return []

        for row in rows:
            entry = self._row_to_entry(tuple(row))
            if entry.embedding is None:
                continue
            sim = float(
                np.dot(embedding, entry.embedding) / (query_norm * np.linalg.norm(entry.embedding))
            )
            if sim >= threshold:
                results.append(SearchResult(entry=entry, similarity=sim))

        # Sort by similarity descending, take top_k
        results.sort(key=lambda r: r.similarity, reverse=True)

        # Update last_referenced timestamp for retrieved entries
        now = time.time()
        for r in results[:top_k]:
            await db.execute(
                "UPDATE facts SET last_referenced = ? WHERE id = ?",
                (now, r.entry.id),
            )
        if results[:top_k]:
            await db.commit()

        return results[:top_k]

    async def find_duplicates(
        self,
        embedding: NDArray[np.float32],
        threshold: float = 0.85,
    ) -> list[SearchResult]:
        """Find near-duplicate facts (similarity > threshold)."""
        return await self.search(embedding, top_k=5, threshold=threshold)

    @staticmethod
    def _row_to_entry(row: tuple[Any, ...]) -> MemoryEntry:
        """Convert a database row to a MemoryEntry."""
        embedding_blob: bytes | None = row[3] if row[3] is not None else None
        embedding = (
            np.frombuffer(embedding_blob, dtype=np.float32).copy()
            if embedding_blob is not None
            else None
        )
        return MemoryEntry(
            id=str(row[0]),
            content=str(row[1]),
            category=MemoryCategory(str(row[2])),
            embedding=embedding,
            source_conversation=str(row[4]) if row[4] is not None else None,
            confidence=float(str(row[5])) if row[5] is not None else 1.0,
            created_at=float(str(row[6])) if row[6] is not None else 0.0,
            last_referenced=float(str(row[7])) if row[7] is not None else 0.0,
            superseded_by=str(row[8]) if row[8] is not None else None,
        )
