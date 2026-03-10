"""SQLite append-only audit log for all action executions.

Supports HMAC chain integrity verification and data retention enforcement.
"""

from __future__ import annotations

import json
import logging

import aiosqlite

from cortex.security.audit_integrity import compute_entry_hmac
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
    error_message TEXT,
    hmac TEXT NOT NULL DEFAULT ''
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
        self._last_hmac: str = ""

    async def start(self) -> None:
        """Open database and create schema."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        # Migrate existing databases: add hmac column if missing
        await self._ensure_hmac_column()
        # Load last HMAC for chain continuity
        await self._load_last_hmac()
        logger.info("Audit log opened: %s", self._db_path)

    async def _ensure_hmac_column(self) -> None:
        """Add hmac column to existing audit_log tables that lack it."""
        if self._db is None:
            return
        async with self._db.execute("PRAGMA table_info(audit_log)") as cursor:
            columns = {row[1] async for row in cursor}
        if "hmac" not in columns:
            await self._db.execute(
                "ALTER TABLE audit_log ADD COLUMN hmac TEXT NOT NULL DEFAULT ''"
            )
            await self._db.commit()
            logger.info("Added hmac column to audit_log")

    async def _load_last_hmac(self) -> None:
        """Load the HMAC of the last entry for chain continuity."""
        if self._db is None:
            return
        async with self._db.execute(
            "SELECT hmac FROM audit_log ORDER BY timestamp DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            self._last_hmac = row[0] if row and row[0] else ""

    async def stop(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Audit log closed")

    async def log(self, entry: AuditEntry) -> None:
        """Write an audit entry with HMAC chain. Raises if database is not open."""
        if self._db is None:
            msg = "Audit log not started"
            raise RuntimeError(msg)

        params_json = json.dumps(entry.parameters) if entry.parameters else None

        # Compute HMAC chained to previous entry
        entry_data = {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "action_type": entry.action_type,
            "action_id": entry.action_id,
            "parameters": params_json,
            "permission_tier": entry.permission_tier,
            "approval_status": entry.approval_status,
            "result": entry.result,
            "source": entry.source,
            "duration_ms": entry.duration_ms,
            "error_message": entry.error_message,
        }
        entry_hmac = compute_entry_hmac(entry_data, self._last_hmac)

        await self._db.execute(
            """INSERT INTO audit_log
               (id, timestamp, action_type, action_id, parameters,
                permission_tier, approval_status, result, source,
                duration_ms, error_message, hmac)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                entry_hmac,
            ),
        )
        await self._db.commit()
        self._last_hmac = entry_hmac
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

    async def delete_before(self, timestamp: float) -> int:
        """Delete audit entries older than timestamp. Returns count deleted."""
        if self._db is None:
            msg = "Audit log not started"
            raise RuntimeError(msg)
        cursor = await self._db.execute(
            "DELETE FROM audit_log WHERE timestamp < ?", (timestamp,)
        )
        await self._db.commit()
        count = cursor.rowcount
        if count > 0:
            logger.info("Deleted %d audit entries before timestamp %.1f", count, timestamp)
        return count

    async def verify_integrity(self) -> tuple[bool, int]:
        """Verify the HMAC chain of all audit entries.

        Returns (valid, bad_index). If valid, bad_index is -1.
        """
        if self._db is None:
            msg = "Audit log not started"
            raise RuntimeError(msg)

        from cortex.security.audit_integrity import verify_chain

        entries: list[dict[str, object]] = []
        async with self._db.execute(
            "SELECT id, timestamp, action_type, action_id, parameters, "
            "permission_tier, approval_status, result, source, "
            "duration_ms, error_message, hmac FROM audit_log ORDER BY timestamp ASC"
        ) as cursor:
            async for row in cursor:
                entries.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "action_type": row[2],
                    "action_id": row[3],
                    "parameters": row[4],
                    "permission_tier": row[5],
                    "approval_status": row[6],
                    "result": row[7],
                    "source": row[8],
                    "duration_ms": row[9],
                    "error_message": row[10],
                    "hmac": row[11],
                })

        if not entries:
            return True, -1

        return verify_chain(entries)
