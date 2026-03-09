"""Tool promotion tracker — tracks execution stats and manages tier promotion.

Records successful/failed executions per tool. After a configurable number of
consecutive successes, tools become eligible for promotion (Tier 2 → 1).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tool_promotion (
    tool_name TEXT PRIMARY KEY,
    total_executions INTEGER DEFAULT 0,
    successful_executions INTEGER DEFAULT 0,
    failed_executions INTEGER DEFAULT 0,
    consecutive_successes INTEGER DEFAULT 0,
    current_tier INTEGER DEFAULT 2,
    promoted_at REAL,
    last_execution_at REAL,
    created_at REAL NOT NULL
);
"""


class ToolPromotionTracker:
    """Tracks tool execution stats and manages tier promotion.

    Args:
        db_path: Path to SQLite database.
        promotion_threshold: Consecutive successes needed for promotion.
    """

    def __init__(
        self,
        db_path: str = "data/tool_promotion.db",
        promotion_threshold: int = 10,
    ) -> None:
        self._db_path = db_path
        self._promotion_threshold = promotion_threshold
        self._db: aiosqlite.Connection | None = None

    @property
    def promotion_threshold(self) -> int:
        return self._promotion_threshold

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
            msg = "ToolPromotionTracker not started"
            raise RuntimeError(msg)
        return self._db

    async def record_execution(self, tool_name: str, success: bool) -> None:
        """Record a tool execution result.

        Args:
            tool_name: Name of the tool.
            success: Whether execution was successful.
        """
        db = self._ensure_started()
        now = time.time()

        # Ensure row exists
        await db.execute(
            "INSERT OR IGNORE INTO tool_promotion (tool_name, created_at) VALUES (?, ?)",
            (tool_name, now),
        )

        if success:
            await db.execute(
                "UPDATE tool_promotion SET "
                "total_executions = total_executions + 1, "
                "successful_executions = successful_executions + 1, "
                "consecutive_successes = consecutive_successes + 1, "
                "last_execution_at = ? "
                "WHERE tool_name = ?",
                (now, tool_name),
            )
        else:
            await db.execute(
                "UPDATE tool_promotion SET "
                "total_executions = total_executions + 1, "
                "failed_executions = failed_executions + 1, "
                "consecutive_successes = 0, "
                "last_execution_at = ? "
                "WHERE tool_name = ?",
                (now, tool_name),
            )

        await db.commit()

    async def check_promotion_eligible(self, tool_name: str) -> bool:
        """Check if a tool is eligible for promotion.

        A tool is eligible when consecutive_successes >= promotion_threshold
        and current_tier > 1.
        """
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT consecutive_successes, current_tier FROM tool_promotion WHERE tool_name = ?",
            (tool_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return False

        consecutive = int(row[0])
        current_tier = int(row[1])
        return consecutive >= self._promotion_threshold and current_tier > 1

    async def promote(self, tool_name: str) -> bool:
        """Promote a tool to a lower tier (Tier 2 → 1).

        Returns True if promoted, False if not eligible.
        """
        if not await self.check_promotion_eligible(tool_name):
            return False

        db = self._ensure_started()
        now = time.time()
        await db.execute(
            "UPDATE tool_promotion SET "
            "current_tier = current_tier - 1, "
            "consecutive_successes = 0, "
            "promoted_at = ? "
            "WHERE tool_name = ?",
            (now, tool_name),
        )
        await db.commit()
        logger.info("Promoted tool '%s'", tool_name)
        return True

    async def demote(self, tool_name: str, tier: int = 2) -> None:
        """Demote a tool back to a higher tier."""
        db = self._ensure_started()
        await db.execute(
            "UPDATE tool_promotion SET "
            "current_tier = ?, "
            "consecutive_successes = 0 "
            "WHERE tool_name = ?",
            (tier, tool_name),
        )
        await db.commit()

    async def get_stats(self, tool_name: str) -> dict[str, Any] | None:
        """Get execution stats for a tool."""
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT tool_name, total_executions, successful_executions, "
            "failed_executions, consecutive_successes, current_tier, "
            "promoted_at, last_execution_at, created_at "
            "FROM tool_promotion WHERE tool_name = ?",
            (tool_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "tool_name": row[0],
            "total_executions": row[1],
            "successful_executions": row[2],
            "failed_executions": row[3],
            "consecutive_successes": row[4],
            "current_tier": row[5],
            "promoted_at": row[6],
            "last_execution_at": row[7],
            "created_at": row[8],
        }

    async def list_all(self) -> list[dict[str, Any]]:
        """List all tracked tools with their stats."""
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT tool_name, total_executions, successful_executions, "
            "failed_executions, consecutive_successes, current_tier "
            "FROM tool_promotion ORDER BY tool_name"
        )
        rows = await cursor.fetchall()
        return [
            {
                "tool_name": row[0],
                "total_executions": row[1],
                "successful_executions": row[2],
                "failed_executions": row[3],
                "consecutive_successes": row[4],
                "current_tier": row[5],
            }
            for row in rows
        ]
