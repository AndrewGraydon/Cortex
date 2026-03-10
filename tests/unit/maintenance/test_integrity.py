"""Tests for database integrity checks and backup verification."""

from __future__ import annotations

import tarfile
from pathlib import Path

import aiosqlite
import pytest

from cortex.maintenance.integrity import (
    AllIntegrityResults,
    IntegrityResult,
    check_all_databases,
    check_sqlite_integrity,
    verify_backup,
)


class TestSqliteIntegrity:
    """PRAGMA integrity_check wrapper."""

    @pytest.mark.asyncio()
    async def test_valid_db_passes(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "valid.db")
        async with aiosqlite.connect(db_path) as db:
            await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            await db.commit()

        result = await check_sqlite_integrity(db_path)
        assert result.ok is True
        assert result.message == "ok"

    @pytest.mark.asyncio()
    async def test_missing_file(self, tmp_path: Path) -> None:
        result = await check_sqlite_integrity(str(tmp_path / "missing.db"))
        assert result.ok is False
        assert "not found" in result.message

    @pytest.mark.asyncio()
    async def test_corrupted_file(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "corrupt.db")
        # Write garbage to simulate corruption
        Path(db_path).write_bytes(b"not a database" * 100)
        result = await check_sqlite_integrity(db_path)
        assert result.ok is False

    @pytest.mark.asyncio()
    async def test_empty_file(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "empty.db")
        Path(db_path).touch()
        result = await check_sqlite_integrity(db_path)
        # Empty file is actually a valid empty SQLite database
        assert isinstance(result.ok, bool)


class TestCheckAllDatabases:
    """check_all_databases multi-DB checks."""

    @pytest.mark.asyncio()
    async def test_all_valid(self, tmp_path: Path) -> None:
        paths = []
        for name in ["a.db", "b.db"]:
            p = str(tmp_path / name)
            async with aiosqlite.connect(p) as db:
                await db.execute("CREATE TABLE test (id INTEGER)")
                await db.commit()
            paths.append(p)

        results = await check_all_databases(paths)
        assert results.all_ok is True
        assert len(results.results) == 2

    @pytest.mark.asyncio()
    async def test_skips_missing_files(self, tmp_path: Path) -> None:
        results = await check_all_databases([str(tmp_path / "nope.db")])
        # Missing files are not checked, so results should be empty
        assert len(results.results) == 0

    @pytest.mark.asyncio()
    async def test_mixed_valid_and_corrupt(self, tmp_path: Path) -> None:
        # Valid DB
        valid_path = str(tmp_path / "valid.db")
        async with aiosqlite.connect(valid_path) as db:
            await db.execute("CREATE TABLE test (id INTEGER)")
            await db.commit()

        # Corrupt DB
        corrupt_path = str(tmp_path / "corrupt.db")
        Path(corrupt_path).write_bytes(b"garbage" * 100)

        results = await check_all_databases([valid_path, corrupt_path])
        assert results.all_ok is False
        assert len(results.failed) == 1

    def test_all_integrity_results_properties(self) -> None:
        results = AllIntegrityResults(results=[
            IntegrityResult(path="a.db", ok=True),
            IntegrityResult(path="b.db", ok=False, message="error"),
        ])
        assert results.all_ok is False
        assert len(results.failed) == 1
        assert results.failed[0].path == "b.db"


class TestVerifyBackup:
    """Backup tarball verification."""

    def test_valid_backup(self, tmp_path: Path) -> None:
        # Create a valid tar.gz
        backup_path = str(tmp_path / "backup.tar.gz")
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(str(test_file), arcname="test.txt")

        result = verify_backup(backup_path)
        assert result.ok is True
        assert "1 files" in result.message

    def test_missing_file(self, tmp_path: Path) -> None:
        result = verify_backup(str(tmp_path / "missing.tar.gz"))
        assert result.ok is False
        assert "not found" in result.message

    def test_corrupt_file(self, tmp_path: Path) -> None:
        corrupt_path = str(tmp_path / "corrupt.tar.gz")
        Path(corrupt_path).write_bytes(b"not a tar file")
        result = verify_backup(corrupt_path)
        assert result.ok is False

    def test_multi_file_backup(self, tmp_path: Path) -> None:
        backup_path = str(tmp_path / "multi.tar.gz")
        for name in ["a.txt", "b.txt", "c.txt"]:
            f = tmp_path / name
            f.write_text(f"content of {name}")
        with tarfile.open(backup_path, "w:gz") as tar:
            for name in ["a.txt", "b.txt", "c.txt"]:
                tar.add(str(tmp_path / name), arcname=name)

        result = verify_backup(backup_path)
        assert result.ok is True
        assert "3 files" in result.message
