"""SQLite append-only audit log for all action executions."""

from __future__ import annotations

import json
import logging

import aiosqlite

from cortex.security.types import AuditEntry

logger = logging.getLogger(__name__)

SCHEMA = """\
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    action_type TEXT NOT NULL,
    action_id TEXT,
    parameters TEXT,
    permission_tier INTEGER NOT NULL DEFAULT 0,
    approval_status TEXT NOT NULL DEFAULT 'auto',
    result TEXT NOT NULL DEFAULT 'success',
    source TEXT NOT NULL DEFAULT 'voice',
    duration_ms REAL NOT NULL DEFAULT 0.0,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action_type ON audit_log(action_type);
"""


class SqliteAuditLog:
    """Append-only SQLite audit log.

    Thread-safe via aiosqlite. All writes are immediate (no batching)
    to ensure audit integrity.
    """

    def __init__(self, db_path: str = "data/audit.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def start(self) -> None:
        """Open database and create schema."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info("Audit log opened: %s", self._db_path)

    async def stop(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Audit log closed")

    async def log(self, entry: AuditEntry) -> None:
        """Write an audit entry. Raises if database is not open."""
        if self._db is None:
            msg = "Audit log not started"
            raise RuntimeError(msg)

        params_json = json.dumps(entry.parameters) if entry.parameters else None
        await self._db.execute(
            """INSERT INTO audit_log
               (id, timestamp, action_type, action_id, parameters,
                permission_tier, approval_status, result, source,
                duration_ms, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id,
                entry.timestamp,
                entry.action_type,
                entry.action_id,
                params_json,
                entry.permission_tier,
                entry.approval_status,
                entry.result,
                entry.source,
                entry.duration_ms,
                entry.error_message,
            ),
        )
        await self._db.commit()
        logger.debug("Audit: %s %s → %s", entry.action_type, entry.action_id, entry.result)

    async def query(
        self,
        action_type: str | None = None,
        since: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filters."""
        if self._db is None:
            msg = "Audit log not started"
            raise RuntimeError(msg)

        conditions: list[str] = []
        params: list[object] = []

        if action_type is not None:
            conditions.append("action_type = ?")
            params.append(action_type)
        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(since)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM audit_log{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

        rows: list[AuditEntry] = []
        async with self._db.execute(sql, params) as cursor:
            async for row in cursor:
                params_dict = json.loads(row[4]) if row[4] else None
                rows.append(
                    AuditEntry(
                        id=row[0],
                        timestamp=row[1],
                        action_type=row[2],
                        action_id=row[3],
                        parameters=params_dict,
                        permission_tier=row[5],
                        approval_status=row[6],
                        result=row[7],
                        source=row[8],
                        duration_ms=row[9],
                        error_message=row[10],
                    )
                )
        return rows

    async def count(self) -> int:
        """Return total number of audit entries."""
        if self._db is None:
            msg = "Audit log not started"
            raise RuntimeError(msg)
        async with self._db.execute("SELECT COUNT(*) FROM audit_log") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
