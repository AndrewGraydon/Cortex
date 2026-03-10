"""Episodic memory — timestamped events for pattern detection.

Records tool usage, query topics, routine actions, and session lifecycle.
Provides routine pattern detection by grouping events by (type, hour, day_of_week).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from cortex.memory.types import EpisodicEvent, EventType

logger = logging.getLogger(__name__)


class EpisodicMemoryStore:
    """Records and queries episodic events for pattern detection.

    Shares a database file with SqliteMemoryStore (uses the episodic_events
    table created by migration v2).
    """

    def __init__(self, db_path: str = "data/memory.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def start(self) -> None:
        """Open the database connection."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")

    async def stop(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _ensure_started(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "EpisodicMemoryStore not started"
            raise RuntimeError(msg)
        return self._db

    async def record_event(
        self,
        event_type: EventType,
        content: str,
        session_id: str | None = None,
        metadata: dict[str, str] | None = None,
        timestamp: float | None = None,
    ) -> EpisodicEvent:
        """Record a new episodic event."""
        db = self._ensure_started()
        event = EpisodicEvent(
            id=uuid.uuid4().hex[:16],
            event_type=event_type,
            content=content,
            timestamp=timestamp or time.time(),
            session_id=session_id,
            metadata=metadata or {},
        )
        await db.execute(
            "INSERT INTO episodic_events "
            "(id, event_type, content, timestamp, session_id, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.event_type.value,
                event.content,
                event.timestamp,
                event.session_id,
                json.dumps(event.metadata),
            ),
        )
        await db.commit()
        return event

    async def query_events(
        self,
        event_type: EventType | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 100,
    ) -> list[EpisodicEvent]:
        """Query episodic events with optional filters."""
        db = self._ensure_started()
        conditions: list[str] = []
        params: list[Any] = []

        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type.value)
        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            conditions.append("timestamp <= ?")
            params.append(until)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = (
            f"SELECT id, event_type, content, timestamp, session_id, metadata_json "
            f"FROM episodic_events{where} ORDER BY timestamp DESC LIMIT ?"
        )
        params.append(limit)

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [
            EpisodicEvent(
                id=str(row[0]),
                event_type=EventType(str(row[1])),
                content=str(row[2]),
                timestamp=float(str(row[3])),
                session_id=str(row[4]) if row[4] else None,
                metadata=json.loads(str(row[5])) if row[5] else {},
            )
            for row in rows
        ]

    async def event_count(self, event_type: EventType | None = None) -> int:
        """Count episodic events, optionally filtered by type."""
        db = self._ensure_started()
        if event_type is not None:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM episodic_events WHERE event_type = ?",
                (event_type.value,),
            )
        else:
            cursor = await db.execute("SELECT COUNT(*) FROM episodic_events")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_routine_patterns(
        self,
        min_occurrences: int = 5,
        days_back: int = 30,
    ) -> list[dict[str, Any]]:
        """Detect routine patterns by grouping events by (type, hour, day_of_week).

        Returns a list of pattern dicts:
        {
            "event_type": "tool_use",
            "content": "clock",
            "hour": 8,
            "day_of_week": 1,  # 0=Monday
            "count": 12,
        }
        """
        since = time.time() - (days_back * 86400)
        events = await self.query_events(since=since, limit=10000)
        if not events:
            return []

        # Group by (event_type, content, hour, day_of_week)
        counter: Counter[tuple[str, str, int, int]] = Counter()
        for event in events:
            dt = datetime.fromtimestamp(event.timestamp, tz=UTC)
            key = (event.event_type.value, event.content, dt.hour, dt.weekday())
            counter[key] += 1

        patterns: list[dict[str, Any]] = []
        for (etype, content, hour, dow), count in counter.most_common():
            if count >= min_occurrences:
                patterns.append(
                    {
                        "event_type": etype,
                        "content": content,
                        "hour": hour,
                        "day_of_week": dow,
                        "count": count,
                    }
                )

        return patterns

    async def get_recent_events(
        self, hours_back: int = 24, limit: int = 200,
    ) -> list[EpisodicEvent]:
        """Get recent events for memory consolidation.

        Args:
            hours_back: How many hours of history to retrieve.
            limit: Maximum events to return.
        """
        since = time.time() - (hours_back * 3600)
        return await self.query_events(since=since, limit=limit)

    async def get_event_clusters(
        self, hours_back: int = 24, min_count: int = 3,
    ) -> list[dict[str, Any]]:
        """Group recent events by (type, content) for consolidation.

        Returns dicts with event_type, content, count, first_seen, last_seen.
        """
        events = await self.get_recent_events(hours_back)
        clusters: dict[tuple[str, str], list[float]] = {}
        for event in events:
            key = (event.event_type.value, event.content)
            clusters.setdefault(key, []).append(event.timestamp)

        result: list[dict[str, Any]] = []
        for (etype, content), timestamps in clusters.items():
            if len(timestamps) >= min_count:
                result.append({
                    "event_type": etype,
                    "content": content,
                    "count": len(timestamps),
                    "first_seen": min(timestamps),
                    "last_seen": max(timestamps),
                })
        result.sort(key=lambda c: c["count"], reverse=True)
        return result

    async def prune_old_events(self, max_age_days: int = 365) -> int:
        """Delete events older than max_age_days. Returns count deleted."""
        db = self._ensure_started()
        cutoff = time.time() - (max_age_days * 86400)
        cursor = await db.execute("DELETE FROM episodic_events WHERE timestamp < ?", (cutoff,))
        await db.commit()
        return cursor.rowcount
