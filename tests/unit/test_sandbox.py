"""Tests for bubblewrap sandbox — command construction and execution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cortex.security.sandbox import BubblewrapSandbox
from cortex.security.sandbox_types import SandboxConfig, SandboxPolicy, SandboxResult


@pytest.fixture
def config() -> SandboxConfig:
    return SandboxConfig(
        enabled=True,
        bwrap_path="/usr/bin/bwrap",
        scratch_dir="/tmp/test-sandbox",
        max_memory_mb=256,
        max_cpu_seconds=30,
    )


@pytest.fixture
def sandbox(config: SandboxConfig) -> BubblewrapSandbox:
    return BubblewrapSandbox(config)


class TestSandboxProperties:
    def test_enabled(self, sandbox: BubblewrapSandbox) -> None:
        assert sandbox.enabled is True

    def test_disabled(self) -> None:
        config = SandboxConfig(enabled=False)
        sandbox = BubblewrapSandbox(config)
        assert sandbox.enabled is False

    def test_bwrap_available_missing(self, sandbox: BubblewrapSandbox) -> None:
        # /usr/bin/bwrap unlikely to exist on macOS
        # This test just verifies the property works
        result = sandbox.bwrap_available
        assert isinstance(result, bool)


class TestBuildCommand:
    def test_basic_command(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            scratch_dir=scratch,
        )
        assert cmd[0] == "/usr/bin/bwrap"
        assert "--die-with-parent" in cmd
        assert "--unshare-all" in cmd
        assert "python" in cmd
        assert "script.py" in cmd

    def test_network_blocked_by_default(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            scratch_dir=scratch,
        )
        assert "--share-net" not in cmd

    def test_network_allowed(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            allow_network=True,
            scratch_dir=scratch,
        )
        assert "--share-net" in cmd

    def test_working_directory(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cwd = str(tmp_path / "tooldir")
        Path(cwd).mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            cwd=cwd,
            scratch_dir=scratch,
        )
        chdir_idx = cmd.index("--chdir")
        assert cmd[chdir_idx + 1] == cwd

    def test_strict_policy(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            policy=SandboxPolicy.STRICT,
            scratch_dir=scratch,
        )
        # Strict should unset HOME and USER
        assert "--unsetenv" in cmd

    def test_scratch_dir_mount(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            scratch_dir=scratch,
        )
        # Should bind scratch to /tmp
        bind_idx = [i for i, x in enumerate(cmd) if x == "--bind"]
        assert len(bind_idx) >= 1

    def test_ro_bind_system_paths(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            scratch_dir=scratch,
        )
        assert "--ro-bind" in cmd

    def test_command_separator(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            scratch_dir=scratch,
        )
        assert "--" in cmd
        sep_idx = cmd.index("--")
        assert cmd[sep_idx + 1] == "python"
        assert cmd[sep_idx + 2] == "script.py"

    def test_python_prefix_mounted(self, sandbox: BubblewrapSandbox, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        cmd = sandbox.build_command(
            ["python", "script.py"],
            scratch_dir=scratch,
        )
        # sys.prefix should be in an --ro-bind
        cmd_str = " ".join(cmd)
        assert sys.prefix in cmd_str


class TestSandboxTypes:
    def test_sandbox_config_defaults(self) -> None:
        config = SandboxConfig()
        assert config.enabled is True
        assert config.bwrap_path == "/usr/bin/bwrap"
        assert config.max_memory_mb == 256
        assert config.max_cpu_seconds == 30
        assert config.network_default is False

    def test_sandbox_result_defaults(self) -> None:
        result = SandboxResult()
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.duration_ms == 0.0

    def test_sandbox_policy_values(self) -> None:
        assert SandboxPolicy.NONE.value == "none"
        assert SandboxPolicy.BASIC.value == "basic"
        assert SandboxPolicy.STRICT.value == "strict"

    def test_sandbox_result_populated(self) -> None:
        result = SandboxResult(
            stdout="hello",
            stderr="warning",
            exit_code=1,
            timed_out=True,
            duration_ms=150.5,
        )
        assert result.stdout == "hello"
        assert result.exit_code == 1
        assert result.timed_out is True
