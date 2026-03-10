"""Tests for data retention enforcement."""

from __future__ import annotations

import time

import aiosqlite
import pytest

from cortex.maintenance.retention import (
    RetentionResult,
    enforce_audit_retention,
    enforce_episodic_retention,
    enforce_memory_retention,
    run_all_retention,
)


async def _create_audit_db(path: str, entries: list[tuple[str, float]]) -> None:
    """Create an audit_log table with test entries."""
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                action_type TEXT NOT NULL DEFAULT 'test',
                hmac TEXT NOT NULL DEFAULT ''
            )"""
        )
        for entry_id, ts in entries:
            await db.execute(
                "INSERT INTO audit_log (id, timestamp) VALUES (?, ?)",
                (entry_id, ts),
            )
        await db.commit()


async def _create_memory_db(path: str, convos: list[tuple[str, float]]) -> None:
    """Create a conversations table with test entries."""
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                summary TEXT DEFAULT ''
            )"""
        )
        for cid, ts in convos:
            await db.execute(
                "INSERT INTO conversations (id, created_at) VALUES (?, ?)",
                (cid, ts),
            )
        await db.commit()


async def _create_episodic_db(path: str, events: list[tuple[str, float]]) -> None:
    """Create an episodic_events table with test entries."""
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS episodic_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL DEFAULT 'test',
                content TEXT NOT NULL DEFAULT '',
                timestamp REAL NOT NULL
            )"""
        )
        for eid, ts in events:
            await db.execute(
                "INSERT INTO episodic_events (id, event_type, content, timestamp) "
                "VALUES (?, 'test', 'test', ?)",
                (eid, ts),
            )
        await db.commit()


async def _count_rows(path: str, table: str) -> int:
    async with (
        aiosqlite.connect(path) as db,
        db.execute(f"SELECT COUNT(*) FROM {table}") as cursor,  # noqa: S608
    ):
        row = await cursor.fetchone()
        return row[0] if row else 0


class TestAuditRetention:
    """enforce_audit_retention tests."""

    @pytest.mark.asyncio()
    async def test_delete_old_entries(self, tmp_path: object) -> None:
        db_path = f"{tmp_path}/audit.db"
        now = time.time()
        await _create_audit_db(db_path, [
            ("old-1", now - 100 * 86400),
            ("old-2", now - 200 * 86400),
            ("recent", now - 10 * 86400),
        ])
        deleted = await enforce_audit_retention(db_path, retention_days=90)
        assert deleted == 2
        assert await _count_rows(db_path, "audit_log") == 1

    @pytest.mark.asyncio()
    async def test_preserve_all_when_none_old(self, tmp_path: object) -> None:
        db_path = f"{tmp_path}/audit.db"
        now = time.time()
        await _create_audit_db(db_path, [("e1", now), ("e2", now)])
        deleted = await enforce_audit_retention(db_path, retention_days=90)
        assert deleted == 0
        assert await _count_rows(db_path, "audit_log") == 2

    @pytest.mark.asyncio()
    async def test_zero_retention_keeps_all(self, tmp_path: object) -> None:
        db_path = f"{tmp_path}/audit.db"
        now = time.time()
        await _create_audit_db(db_path, [("old", now - 999 * 86400)])
        deleted = await enforce_audit_retention(db_path, retention_days=0)
        assert deleted == 0
        assert await _count_rows(db_path, "audit_log") == 1


class TestMemoryRetention:
    """enforce_memory_retention tests."""

    @pytest.mark.asyncio()
    async def test_delete_old_conversations(self, tmp_path: object) -> None:
        db_path = f"{tmp_path}/memory.db"
        now = time.time()
        await _create_memory_db(db_path, [
            ("old", now - 60 * 86400),
            ("recent", now - 5 * 86400),
        ])
        deleted = await enforce_memory_retention(db_path, retention_days=30)
        assert deleted == 1
        assert await _count_rows(db_path, "conversations") == 1

    @pytest.mark.asyncio()
    async def test_zero_retention_keeps_all(self, tmp_path: object) -> None:
        db_path = f"{tmp_path}/memory.db"
        now = time.time()
        await _create_memory_db(db_path, [("old", now - 999 * 86400)])
        deleted = await enforce_memory_retention(db_path, retention_days=0)
        assert deleted == 0


class TestEpisodicRetention:
    """enforce_episodic_retention tests."""

    @pytest.mark.asyncio()
    async def test_delete_old_events(self, tmp_path: object) -> None:
        db_path = f"{tmp_path}/memory.db"
        now = time.time()
        await _create_episodic_db(db_path, [
            ("old", now - 400 * 86400),
            ("recent", now - 30 * 86400),
        ])
        deleted = await enforce_episodic_retention(db_path, retention_days=365)
        assert deleted == 1
        assert await _count_rows(db_path, "episodic_events") == 1

    @pytest.mark.asyncio()
    async def test_zero_retention_keeps_all(self, tmp_path: object) -> None:
        db_path = f"{tmp_path}/memory.db"
        now = time.time()
        await _create_episodic_db(db_path, [("old", now - 999 * 86400)])
        deleted = await enforce_episodic_retention(db_path, retention_days=0)
        assert deleted == 0


class TestRunAllRetention:
    """Combined retention run."""

    @pytest.mark.asyncio()
    async def test_run_all_with_existing_dbs(self, tmp_path: object) -> None:
        audit_path = f"{tmp_path}/audit.db"
        memory_path = f"{tmp_path}/memory.db"
        now = time.time()

        await _create_audit_db(audit_path, [("old-a", now - 100 * 86400)])
        await _create_memory_db(memory_path, [("old-m", now - 60 * 86400)])
        await _create_episodic_db(memory_path, [("old-e", now - 400 * 86400)])

        result = await run_all_retention(
            audit_db_path=audit_path,
            memory_db_path=memory_path,
            audit_retention_days=90,
            memory_retention_days=30,
            episodic_retention_days=365,
        )
        assert result.audit_deleted == 1
        assert result.conversations_deleted == 1
        assert result.episodic_deleted == 1
        assert result.total_deleted == 3

    @pytest.mark.asyncio()
    async def test_run_all_missing_dbs(self, tmp_path: object) -> None:
        """Should not crash when databases don't exist."""
        result = await run_all_retention(
            audit_db_path=f"{tmp_path}/nonexistent.db",
            memory_db_path=f"{tmp_path}/nonexistent2.db",
        )
        assert result.total_deleted == 0

    def test_retention_result_properties(self) -> None:
        result = RetentionResult(audit_deleted=5, conversations_deleted=3, episodic_deleted=2)
        assert result.total_deleted == 10
