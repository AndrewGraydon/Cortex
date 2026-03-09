"""Tool catalog — persistent catalog of all tools with lifecycle tracking.

Tracks built-in, script, and user-created tools with stage, version, usage.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiosqlite

from cortex.agent.tools.pipeline.types import PipelineStage

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tool_catalog (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'user',
    stage TEXT NOT NULL DEFAULT 'draft',
    version INTEGER NOT NULL DEFAULT 1,
    permission_tier INTEGER NOT NULL DEFAULT 2,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


class ToolCatalog:
    """Persistent catalog of tools with lifecycle tracking.

    Args:
        db_path: Path to SQLite database.
    """

    def __init__(self, db_path: str = "data/tool_catalog.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def start(self) -> None:
        """Open database and ensure schema exists."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(CREATE_TABLE_SQL)
        await self._db.commit()

    async def stop(self) -> None:
        """Close database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _ensure_started(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "ToolCatalog not started"
            raise RuntimeError(msg)
        return self._db

    async def add(
        self,
        name: str,
        description: str = "",
        source: str = "user",
        stage: PipelineStage = PipelineStage.DRAFT,
        permission_tier: int = 2,
    ) -> None:
        """Add a tool to the catalog."""
        db = self._ensure_started()
        now = time.time()
        await db.execute(
            "INSERT OR REPLACE INTO tool_catalog "
            "(name, description, source, stage, permission_tier, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, description, source, stage.value, permission_tier, now, now),
        )
        await db.commit()

    async def update_stage(self, name: str, stage: PipelineStage) -> bool:
        """Update a tool's pipeline stage."""
        db = self._ensure_started()
        now = time.time()
        cursor = await db.execute(
            "UPDATE tool_catalog SET stage = ?, updated_at = ? WHERE name = ?",
            (stage.value, now, name),
        )
        await db.commit()
        return cursor.rowcount > 0

    async def increment_usage(self, name: str) -> None:
        """Increment a tool's usage count."""
        db = self._ensure_started()
        now = time.time()
        await db.execute(
            "UPDATE tool_catalog SET usage_count = usage_count + 1, updated_at = ? WHERE name = ?",
            (now, name),
        )
        await db.commit()

    async def get(self, name: str) -> dict[str, Any] | None:
        """Get a tool's catalog entry."""
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT name, description, source, stage, version, permission_tier, "
            "usage_count, created_at, updated_at FROM tool_catalog WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    async def list_all(
        self,
        source: str | None = None,
        stage: PipelineStage | None = None,
    ) -> list[dict[str, Any]]:
        """List all catalog entries with optional filters."""
        db = self._ensure_started()
        conditions: list[str] = []
        params: list[Any] = []

        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        if stage is not None:
            conditions.append("stage = ?")
            params.append(stage.value)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        cursor = await db.execute(
            "SELECT name, description, source, stage, version, permission_tier, "
            f"usage_count, created_at, updated_at FROM tool_catalog{where} ORDER BY name",
            params,
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    async def remove(self, name: str) -> bool:
        """Remove a tool from the catalog."""
        db = self._ensure_started()
        cursor = await db.execute("DELETE FROM tool_catalog WHERE name = ?", (name,))
        await db.commit()
        return cursor.rowcount > 0

    async def count(self, source: str | None = None) -> int:
        """Count catalog entries."""
        db = self._ensure_started()
        if source is not None:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM tool_catalog WHERE source = ?", (source,)
            )
        else:
            cursor = await db.execute("SELECT COUNT(*) FROM tool_catalog")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a database row to a dict."""
    return {
        "name": row[0],
        "description": row[1],
        "source": row[2],
        "stage": row[3],
        "version": row[4],
        "permission_tier": row[5],
        "usage_count": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }
