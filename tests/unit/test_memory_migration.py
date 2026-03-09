"""Tests for memory schema migration."""

from __future__ import annotations

import aiosqlite
import pytest

from cortex.memory.migration import MIGRATIONS, get_schema_version, run_migrations
from cortex.memory.store import CREATE_TABLES, SCHEMA_VERSION, SqliteMemoryStore


@pytest.fixture
async def fresh_db(tmp_path: object) -> str:
    """Create a fresh v1 database."""
    db_path = str(tmp_path) + "/test_migration.db"  # type: ignore[operator]
    db = await aiosqlite.connect(db_path)
    await db.executescript(CREATE_TABLES)
    await db.execute("INSERT INTO schema_version (version) VALUES (1)")
    await db.commit()
    await db.close()
    return db_path


class TestGetSchemaVersion:
    async def test_fresh_db(self, fresh_db: str) -> None:
        db = await aiosqlite.connect(fresh_db)
        version = await get_schema_version(db)
        assert version == 1
        await db.close()


class TestRunMigrations:
    async def test_migrate_v1_to_v2(self, fresh_db: str) -> None:
        db = await aiosqlite.connect(fresh_db)
        assert await get_schema_version(db) == 1

        final = await run_migrations(db, 2)
        assert final == 2
        assert await get_schema_version(db) == 2

        # Verify episodic_events table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='episodic_events'"
        )
        row = await cursor.fetchone()
        assert row is not None
        await db.close()

    async def test_idempotent_migration(self, fresh_db: str) -> None:
        db = await aiosqlite.connect(fresh_db)
        await run_migrations(db, 2)
        # Running again should be a no-op
        final = await run_migrations(db, 2)
        assert final == 2
        await db.close()

    async def test_already_at_target(self, fresh_db: str) -> None:
        db = await aiosqlite.connect(fresh_db)
        await run_migrations(db, 2)
        # Now run targeting v2 again
        final = await run_migrations(db, 2)
        assert final == 2
        await db.close()

    async def test_no_migration_needed(self, fresh_db: str) -> None:
        db = await aiosqlite.connect(fresh_db)
        # Target is v1, already at v1
        final = await run_migrations(db, 1)
        assert final == 1
        await db.close()


class TestMigrationsConstant:
    def test_migrations_ordered(self) -> None:
        versions = [v for v, _ in MIGRATIONS]
        assert versions == sorted(versions)

    def test_current_version_matches(self) -> None:
        # The store's SCHEMA_VERSION should match the highest migration
        max_migration = max(v for v, _ in MIGRATIONS)
        assert max_migration == SCHEMA_VERSION


class TestStoreStartMigrates:
    async def test_start_runs_migration(self, fresh_db: str) -> None:
        """SqliteMemoryStore.start() should auto-migrate from v1 to v2."""
        store = SqliteMemoryStore(db_path=fresh_db)
        await store.start()

        # Verify we're at v2
        db = store._ensure_started()
        version = await get_schema_version(db)
        assert version == 2

        # Verify episodic_events table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='episodic_events'"
        )
        row = await cursor.fetchone()
        assert row is not None
        await store.stop()

    async def test_start_fresh_db(self, tmp_path: object) -> None:
        """Starting with a completely fresh DB should result in v2."""
        db_path = str(tmp_path) + "/fresh.db"  # type: ignore[operator]
        store = SqliteMemoryStore(db_path=db_path)
        await store.start()

        db = store._ensure_started()
        version = await get_schema_version(db)
        assert version == 2
        await store.stop()
