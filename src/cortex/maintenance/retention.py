"""Data retention enforcement — deletes entries older than configured thresholds.

Handles audit log, memory conversations, and episodic events.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    """Result of a retention enforcement run."""

    audit_deleted: int = 0
    conversations_deleted: int = 0
    episodic_deleted: int = 0

    @property
    def total_deleted(self) -> int:
        return self.audit_deleted + self.conversations_deleted + self.episodic_deleted


async def enforce_audit_retention(
    db_path: str,
    retention_days: int,
) -> int:
    """Delete audit entries older than retention_days. Returns count deleted.

    If retention_days is 0, keeps all entries.
    """
    if retention_days <= 0:
        return 0
    cutoff = time.time() - (retention_days * 86400)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "DELETE FROM audit_log WHERE timestamp < ?", (cutoff,)
        )
        await db.commit()
        count = cursor.rowcount
    if count > 0:
        logger.info("Audit retention: deleted %d entries older than %d days", count, retention_days)
    return count


async def enforce_memory_retention(
    db_path: str,
    retention_days: int,
) -> int:
    """Delete conversation summaries older than retention_days. Returns count deleted.

    If retention_days is 0, keeps all entries.
    """
    if retention_days <= 0:
        return 0
    cutoff = time.time() - (retention_days * 86400)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE created_at < ?", (cutoff,)
        )
        await db.commit()
        count = cursor.rowcount
    if count > 0:
        logger.info(
            "Memory retention: deleted %d conversations older than %d days",
            count, retention_days,
        )
    return count


async def enforce_episodic_retention(
    db_path: str,
    retention_days: int,
) -> int:
    """Delete episodic events older than retention_days. Returns count deleted.

    If retention_days is 0, keeps all entries.
    """
    if retention_days <= 0:
        return 0
    cutoff = time.time() - (retention_days * 86400)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "DELETE FROM episodic_events WHERE timestamp < ?", (cutoff,)
        )
        await db.commit()
        count = cursor.rowcount
    if count > 0:
        logger.info(
            "Episodic retention: deleted %d events older than %d days",
            count, retention_days,
        )
    return count


async def run_all_retention(
    audit_db_path: str = "data/audit.db",
    memory_db_path: str = "data/memory.db",
    audit_retention_days: int = 90,
    memory_retention_days: int = 30,
    episodic_retention_days: int = 365,
) -> RetentionResult:
    """Run all retention policies. Returns combined result.

    Silently skips databases that don't exist or lack the expected tables.
    """
    result = RetentionResult()
    try:
        result.audit_deleted = await enforce_audit_retention(
            audit_db_path, audit_retention_days,
        )
    except Exception:
        logger.debug("Skipping audit retention (table may not exist)")
    try:
        result.conversations_deleted = await enforce_memory_retention(
            memory_db_path, memory_retention_days,
        )
    except Exception:
        logger.debug("Skipping memory retention (table may not exist)")
    try:
        result.episodic_deleted = await enforce_episodic_retention(
            memory_db_path, episodic_retention_days,
        )
    except Exception:
        logger.debug("Skipping episodic retention (table may not exist)")

    if result.total_deleted > 0:
        logger.info("Retention complete: %d total entries deleted", result.total_deleted)
    return result
