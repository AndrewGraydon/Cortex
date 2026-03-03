"""Tests for SQLite audit log."""

from __future__ import annotations

import time

import aiosqlite
import pytest

from cortex.security.audit import SqliteAuditLog
from cortex.security.types import AuditEntry


@pytest.fixture
async def audit_log(tmp_path) -> SqliteAuditLog:
    db_path = str(tmp_path / "test_audit.db")
    log = SqliteAuditLog(db_path=db_path)
    await log.start()
    yield log
    await log.stop()


class TestAuditLogLifecycle:
    async def test_start_creates_table(self, audit_log: SqliteAuditLog) -> None:
        count = await audit_log.count()
        assert count == 0

    async def test_stop_closes_connection(self, tmp_path) -> None:
        log = SqliteAuditLog(db_path=str(tmp_path / "test.db"))
        await log.start()
        await log.stop()
        with pytest.raises(RuntimeError, match="not started"):
            await log.count()

    async def test_log_before_start_raises(self, tmp_path) -> None:
        log = SqliteAuditLog(db_path=str(tmp_path / "test.db"))
        entry = AuditEntry(id="x", timestamp=0.0, action_type="test")
        with pytest.raises(RuntimeError, match="not started"):
            await log.log(entry)


class TestAuditLogWrite:
    async def test_log_entry(self, audit_log: SqliteAuditLog) -> None:
        entry = AuditEntry(
            id="audit-001",
            timestamp=time.time(),
            action_type="tool_call",
            action_id="clock",
        )
        await audit_log.log(entry)
        assert await audit_log.count() == 1

    async def test_log_multiple_entries(self, audit_log: SqliteAuditLog) -> None:
        for i in range(5):
            entry = AuditEntry(
                id=f"audit-{i:03d}",
                timestamp=time.time(),
                action_type="tool_call",
                action_id=f"tool_{i}",
            )
            await audit_log.log(entry)
        assert await audit_log.count() == 5

    async def test_log_with_parameters(self, audit_log: SqliteAuditLog) -> None:
        entry = AuditEntry(
            id="audit-p01",
            timestamp=time.time(),
            action_type="tool_call",
            action_id="timer_set",
            parameters={"duration": 300, "label": "tea"},
            permission_tier=1,
        )
        await audit_log.log(entry)
        results = await audit_log.query()
        assert results[0].parameters == {"duration": 300, "label": "tea"}

    async def test_log_with_error(self, audit_log: SqliteAuditLog) -> None:
        entry = AuditEntry(
            id="audit-e01",
            timestamp=time.time(),
            action_type="tool_call",
            action_id="timer_set",
            result="error",
            error_message="Database locked",
        )
        await audit_log.log(entry)
        results = await audit_log.query()
        assert results[0].result == "error"
        assert results[0].error_message == "Database locked"

    async def test_duplicate_id_raises(self, audit_log: SqliteAuditLog) -> None:
        entry = AuditEntry(id="dup", timestamp=0.0, action_type="test")
        await audit_log.log(entry)
        with pytest.raises(aiosqlite.IntegrityError):
            await audit_log.log(entry)


class TestAuditLogQuery:
    async def test_query_all(self, audit_log: SqliteAuditLog) -> None:
        for i in range(3):
            await audit_log.log(
                AuditEntry(
                    id=f"q-{i:03d}",
                    timestamp=1000.0 + i,
                    action_type="tool_call",
                    action_id=f"tool_{i}",
                )
            )
        results = await audit_log.query()
        assert len(results) == 3
        # Ordered by timestamp DESC
        assert results[0].timestamp > results[-1].timestamp

    async def test_query_by_action_type(self, audit_log: SqliteAuditLog) -> None:
        await audit_log.log(
            AuditEntry(id="a1", timestamp=1.0, action_type="tool_call", action_id="clock")
        )
        await audit_log.log(
            AuditEntry(id="a2", timestamp=2.0, action_type="approval", action_id="timer_cancel")
        )
        await audit_log.log(
            AuditEntry(id="a3", timestamp=3.0, action_type="tool_call", action_id="timer_set")
        )

        results = await audit_log.query(action_type="tool_call")
        assert len(results) == 2
        assert all(r.action_type == "tool_call" for r in results)

    async def test_query_since_timestamp(self, audit_log: SqliteAuditLog) -> None:
        await audit_log.log(AuditEntry(id="s1", timestamp=100.0, action_type="test"))
        await audit_log.log(AuditEntry(id="s2", timestamp=200.0, action_type="test"))
        await audit_log.log(AuditEntry(id="s3", timestamp=300.0, action_type="test"))

        results = await audit_log.query(since=200.0)
        assert len(results) == 2

    async def test_query_with_limit(self, audit_log: SqliteAuditLog) -> None:
        for i in range(10):
            await audit_log.log(AuditEntry(id=f"l-{i:03d}", timestamp=float(i), action_type="test"))
        results = await audit_log.query(limit=3)
        assert len(results) == 3

    async def test_query_combined_filters(self, audit_log: SqliteAuditLog) -> None:
        await audit_log.log(AuditEntry(id="c1", timestamp=100.0, action_type="tool_call"))
        await audit_log.log(AuditEntry(id="c2", timestamp=200.0, action_type="approval"))
        await audit_log.log(AuditEntry(id="c3", timestamp=300.0, action_type="tool_call"))

        results = await audit_log.query(action_type="tool_call", since=200.0)
        assert len(results) == 1
        assert results[0].id == "c3"

    async def test_query_empty(self, audit_log: SqliteAuditLog) -> None:
        results = await audit_log.query()
        assert results == []

    async def test_null_parameters_round_trip(self, audit_log: SqliteAuditLog) -> None:
        await audit_log.log(AuditEntry(id="np", timestamp=1.0, action_type="test", parameters=None))
        results = await audit_log.query()
        assert results[0].parameters is None
