"""Database integrity checks — PRAGMA integrity_check, backup verification.

Used by restore scripts and periodic maintenance.
"""

from __future__ import annotations

import logging
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# All known database files
DEFAULT_DB_PATHS = [
    "data/audit.db",
    "data/memory.db",
    "data/knowledge.db",
    "data/schedules.db",
    "data/devices.db",
    "data/automations.db",
    "data/cortex.db",
]


@dataclass
class IntegrityResult:
    """Result of an integrity check."""

    path: str
    ok: bool
    message: str = ""


@dataclass
class AllIntegrityResults:
    """Combined results for all database checks."""

    results: list[IntegrityResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def failed(self) -> list[IntegrityResult]:
        return [r for r in self.results if not r.ok]


async def check_sqlite_integrity(db_path: str) -> IntegrityResult:
    """Run PRAGMA integrity_check on a SQLite database.

    Returns IntegrityResult with ok=True if the database passes.
    """
    path = Path(db_path)
    if not path.exists():
        return IntegrityResult(path=db_path, ok=False, message="file not found")

    try:
        async with aiosqlite.connect(db_path) as db, db.execute("PRAGMA integrity_check") as cursor:
            row = await cursor.fetchone()
            if row and row[0] == "ok":
                return IntegrityResult(path=db_path, ok=True, message="ok")
            msg = row[0] if row else "unknown error"
            return IntegrityResult(path=db_path, ok=False, message=str(msg))
    except Exception as e:
        return IntegrityResult(path=db_path, ok=False, message=str(e))


async def check_all_databases(
    db_paths: list[str] | None = None,
) -> AllIntegrityResults:
    """Check integrity of all known databases.

    Skips databases that don't exist. Returns combined results.
    """
    paths = db_paths or DEFAULT_DB_PATHS
    results = AllIntegrityResults()

    for db_path in paths:
        if Path(db_path).exists():
            result = await check_sqlite_integrity(db_path)
            results.results.append(result)
            if result.ok:
                logger.debug("Integrity OK: %s", db_path)
            else:
                logger.warning("Integrity FAILED: %s — %s", db_path, result.message)

    return results


def verify_backup(backup_path: str) -> IntegrityResult:
    """Verify that a backup tarball is valid and readable.

    Checks that the tar file can be opened and lists its contents.
    Returns IntegrityResult with ok=True if the backup is valid.
    """
    path = Path(backup_path)
    if not path.exists():
        return IntegrityResult(path=backup_path, ok=False, message="file not found")

    try:
        with tarfile.open(backup_path, "r:gz") as tar:
            members = tar.getnames()
            if not members:
                return IntegrityResult(
                    path=backup_path, ok=False, message="empty archive",
                )
            return IntegrityResult(
                path=backup_path,
                ok=True,
                message=f"{len(members)} files",
            )
    except tarfile.TarError as e:
        return IntegrityResult(path=backup_path, ok=False, message=str(e))
    except Exception as e:
        return IntegrityResult(path=backup_path, ok=False, message=str(e))
