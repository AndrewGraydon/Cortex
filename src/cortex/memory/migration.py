"""Schema migration runner for the memory database.

Checks current version, applies pending migrations. Each migration
is a simple SQL string run via executescript().
"""

from __future__ import annotations

import logging

import aiosqlite

logger = logging.getLogger(__name__)

# Migration v1 → v2: add episodic events table
MIGRATION_V2 = """
CREATE TABLE IF NOT EXISTS episodic_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp REAL NOT NULL,
    session_id TEXT,
    metadata_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_episodic_timestamp ON episodic_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_type ON episodic_events(event_type);
"""

# Ordered list of (version, sql) tuples
MIGRATIONS: list[tuple[int, str]] = [
    (2, MIGRATION_V2),
]


async def get_schema_version(db: aiosqlite.Connection) -> int:
    """Get the current schema version from the database."""
    cursor = await db.execute("SELECT MAX(version) FROM schema_version")
    row = await cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


async def run_migrations(db: aiosqlite.Connection, target_version: int) -> int:
    """Run pending migrations up to the target version.

    Returns the final schema version after migration.
    """
    current = await get_schema_version(db)
    if current >= target_version:
        return current

    for version, sql in MIGRATIONS:
        if version > current and version <= target_version:
            logger.info("Applying memory schema migration v%d → v%d", current, version)
            await db.executescript(sql)
            await db.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (version,),
            )
            await db.commit()
            current = version
            logger.info("Migration to v%d complete", version)

    return current
