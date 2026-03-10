"""Tests for backup script behavior — tar creation, exclusions, rotation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


class TestBackupScript:
    """Integration tests for scripts/backup.sh."""

    @pytest.fixture()
    def work_dir(self, tmp_path: Path) -> Path:
        """Create a fake Cortex directory structure for backup testing."""
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "audit.db").write_text("audit data")
        (tmp_path / "data" / "memory.db").write_text("memory data")
        (tmp_path / "data" / "sandbox").mkdir()
        (tmp_path / "data" / "sandbox" / "temp.txt").write_text("sandbox")
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "cortex.yaml").write_text("test: true")
        (tmp_path / ".env").write_text("SECRET=test")
        return tmp_path

    def _run_backup(self, work_dir: Path, **env: str) -> subprocess.CompletedProcess[str]:
        """Run the backup script in the test work_dir."""
        script = Path("scripts/backup.sh").resolve()
        base_env = {
            "CORTEX_BACKUP_DIR": str(work_dir / "backups"),
            "CORTEX_DATA_DIR": str(work_dir / "data"),
            "CORTEX_CONFIG_DIR": str(work_dir / "config"),
            "CORTEX_MAX_BACKUPS": "3",
            "PATH": os.environ.get("PATH", ""),
        }
        base_env.update(env)
        return subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            cwd=str(work_dir),
            env=base_env,
        )

    def test_creates_backup(self, work_dir: Path) -> None:
        result = self._run_backup(work_dir)
        assert result.returncode == 0
        assert "Backup complete" in result.stdout
        backups = list((work_dir / "backups").glob("cortex-*.tar.gz"))
        assert len(backups) == 1

    def test_backup_contains_data(self, work_dir: Path) -> None:
        result = self._run_backup(work_dir)
        assert result.returncode == 0
        import tarfile

        backups = list((work_dir / "backups").glob("cortex-*.tar.gz"))
        with tarfile.open(str(backups[0]), "r:gz") as tar:
            names = tar.getnames()
            # Should contain data and config files
            assert any("audit.db" in n for n in names)
            assert any("cortex.yaml" in n for n in names)

    def test_excludes_sandbox(self, work_dir: Path) -> None:
        result = self._run_backup(work_dir)
        assert result.returncode == 0
        import tarfile

        backups = list((work_dir / "backups").glob("cortex-*.tar.gz"))
        with tarfile.open(str(backups[0]), "r:gz") as tar:
            names = tar.getnames()
            # Check path components, not substring (test dir name contains "sandbox")
            assert not any("/sandbox/" in n or n.endswith("/sandbox") for n in names)

    def test_includes_env(self, work_dir: Path) -> None:
        result = self._run_backup(work_dir)
        assert result.returncode == 0
        import tarfile

        backups = list((work_dir / "backups").glob("cortex-*.tar.gz"))
        with tarfile.open(str(backups[0]), "r:gz") as tar:
            names = tar.getnames()
            assert any(".env" in n for n in names)

    def test_rotation_removes_old_backups(self, work_dir: Path) -> None:
        """After MAX_BACKUPS, old ones are removed."""
        import time

        for _ in range(5):
            result = self._run_backup(work_dir)
            assert result.returncode == 0
            time.sleep(0.1)  # Ensure different timestamps

        backups = list((work_dir / "backups").glob("cortex-*.tar.gz"))
        assert len(backups) <= 3  # MAX_BACKUPS=3

    def test_no_files_error(self, tmp_path: Path) -> None:
        """Error when nothing to back up."""
        result = self._run_backup(
            tmp_path,
            CORTEX_DATA_DIR=str(tmp_path / "nonexistent"),
            CORTEX_CONFIG_DIR=str(tmp_path / "nonexistent2"),
        )
        assert result.returncode != 0
