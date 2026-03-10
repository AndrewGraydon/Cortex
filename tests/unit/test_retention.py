"""Tests for audit retention — delete old entries, preserve recent."""

from __future__ import annotations

import time

import pytest

from cortex.security.audit import SqliteAuditLog
from cortex.security.types import AuditEntry


def _make_entry(entry_id: str, timestamp: float) -> AuditEntry:
    return AuditEntry(
        id=entry_id,
        timestamp=timestamp,
        action_type="test",
        action_id="test_action",
        permission_tier=0,
        approval_status="auto",
        result="success",
        source="test",
        duration_ms=0.0,
    )


class TestAuditRetention:
    """delete_before() retention enforcement."""

    @pytest.mark.asyncio()
    async def test_delete_old_entries(self) -> None:
        audit = SqliteAuditLog(db_path=":memory:")
        await audit.start()

        now = time.time()
        await audit.log(_make_entry("old-1", now - 100))
        await audit.log(_make_entry("old-2", now - 200))
        await audit.log(_make_entry("recent", now))

        deleted = await audit.delete_before(now - 50)
        assert deleted == 2
        assert await audit.count() == 1
        await audit.stop()

    @pytest.mark.asyncio()
    async def test_preserve_all_when_none_old(self) -> None:
        audit = SqliteAuditLog(db_path=":memory:")
        await audit.start()

        now = time.time()
        await audit.log(_make_entry("e1", now))
        await audit.log(_make_entry("e2", now + 1))

        deleted = await audit.delete_before(now - 100)
        assert deleted == 0
        assert await audit.count() == 2
        await audit.stop()

    @pytest.mark.asyncio()
    async def test_delete_all(self) -> None:
        audit = SqliteAuditLog(db_path=":memory:")
        await audit.start()

        now = time.time()
        await audit.log(_make_entry("e1", now - 100))
        await audit.log(_make_entry("e2", now - 200))

        deleted = await audit.delete_before(now)
        assert deleted == 2
        assert await audit.count() == 0
        await audit.stop()

    @pytest.mark.asyncio()
    async def test_boundary_exact_timestamp(self) -> None:
        audit = SqliteAuditLog(db_path=":memory:")
        await audit.start()

        now = time.time()
        await audit.log(_make_entry("at-boundary", now))
        await audit.log(_make_entry("before", now - 1))

        # Delete strictly before 'now' — 'at-boundary' should survive
        deleted = await audit.delete_before(now)
        assert deleted == 1
        assert await audit.count() == 1
        await audit.stop()

    @pytest.mark.asyncio()
    async def test_empty_db(self) -> None:
        audit = SqliteAuditLog(db_path=":memory:")
        await audit.start()
        deleted = await audit.delete_before(time.time())
        assert deleted == 0
        await audit.stop()

    @pytest.mark.asyncio()
    async def test_hmac_chain_after_log(self) -> None:
        """Verify that HMAC is stored and chain is valid after logging."""
        audit = SqliteAuditLog(db_path=":memory:")
        await audit.start()

        now = time.time()
        await audit.log(_make_entry("e1", now))
        await audit.log(_make_entry("e2", now + 1))
        await audit.log(_make_entry("e3", now + 2))

        valid, idx = await audit.verify_integrity()
        assert valid is True
        assert idx == -1
        await audit.stop()

    @pytest.mark.asyncio()
    async def test_verify_empty_db(self) -> None:
        audit = SqliteAuditLog(db_path=":memory:")
        await audit.start()
        valid, idx = await audit.verify_integrity()
        assert valid is True
        assert idx == -1
        await audit.stop()

    @pytest.mark.asyncio()
    async def test_tamper_detection(self) -> None:
        """Manually tamper with an entry and verify chain breaks."""
        audit = SqliteAuditLog(db_path=":memory:")
        await audit.start()

        now = time.time()
        await audit.log(_make_entry("e1", now))
        await audit.log(_make_entry("e2", now + 1))

        # Tamper with e1
        assert audit._db is not None
        await audit._db.execute(
            "UPDATE audit_log SET action_type = 'HACKED' WHERE id = 'e1'"
        )
        await audit._db.commit()

        valid, idx = await audit.verify_integrity()
        assert valid is False
        assert idx == 0
        await audit.stop()
