"""Bubblewrap sandbox — filesystem isolation for script tool execution.

Wraps subprocess execution in a `bwrap` container with:
- Read-only bind mounts for Python and system libs
- Writable scratch directory for tool output
- Network blocking (unshare-net)
- CPU and memory resource limits (via timeout)
- --die-with-parent to prevent orphan processes
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
import time
from pathlib import Path

from cortex.security.sandbox_types import SandboxConfig, SandboxPolicy, SandboxResult

logger = logging.getLogger(__name__)


class BubblewrapSandbox:
    """Executes commands inside a bubblewrap sandbox.

    Usage:
        sandbox = BubblewrapSandbox(config)
        result = await sandbox.execute(
            ["python", "scripts/run.py"],
            cwd="/path/to/tool",
            stdin_data=b'{"arg": "value"}',
        )
    """

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()
        self._scratch_base = Path(self._config.scratch_dir)

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def bwrap_available(self) -> bool:
        """Check if bwrap binary exists."""
        return Path(self._config.bwrap_path).exists()

    def build_command(
        self,
        cmd: list[str],
        cwd: str | None = None,
        policy: SandboxPolicy = SandboxPolicy.BASIC,
        allow_network: bool = False,
        extra_ro_binds: list[str] | None = None,
        scratch_dir: Path | None = None,
    ) -> list[str]:
        """Build the bwrap command line.

        Returns the full command list including bwrap and all flags.
        """
        scratch = scratch_dir or self._scratch_base / "run"
        bwrap = [self._config.bwrap_path]

        # Die with parent process
        bwrap.append("--die-with-parent")

        # Unshare all namespaces
        bwrap.append("--unshare-all")

        # Re-share network if explicitly allowed
        if allow_network:
            bwrap.append("--share-net")

        # Read-only bind mounts for system essentials
        ro_binds = [
            "/usr",
            "/lib",
            "/lib64",
            "/etc/alternatives",
            "/etc/ld.so.cache",
        ]

        # Python path
        python_prefix = sys.prefix
        if python_prefix not in ro_binds:
            ro_binds.append(python_prefix)

        # Tool working directory (read-only)
        if cwd:
            ro_binds.append(cwd)

        # Extra read-only binds
        if extra_ro_binds:
            ro_binds.extend(extra_ro_binds)

        for path in ro_binds:
            if Path(path).exists():
                bwrap.extend(["--ro-bind", path, path])

        # Writable scratch directory
        bwrap.extend(["--bind", str(scratch), "/tmp"])

        # proc filesystem (needed by Python)
        bwrap.extend(["--proc", "/proc"])

        # devtmpfs (minimal)
        bwrap.extend(["--dev", "/dev"])

        if policy == SandboxPolicy.STRICT:
            # Additional restrictions for strict mode
            bwrap.extend(["--unsetenv", "HOME"])
            bwrap.extend(["--unsetenv", "USER"])

        # Working directory
        if cwd:
            bwrap.extend(["--chdir", cwd])

        # The actual command
        bwrap.extend(["--"])
        bwrap.extend(cmd)

        return bwrap

    async def execute(
        self,
        cmd: list[str],
        cwd: str | None = None,
        stdin_data: bytes | None = None,
        timeout: float | None = None,
        policy: SandboxPolicy = SandboxPolicy.BASIC,
        allow_network: bool = False,
    ) -> SandboxResult:
        """Execute a command inside the bubblewrap sandbox.

        Args:
            cmd: Command and arguments to execute.
            cwd: Working directory inside the sandbox.
            stdin_data: Data to pipe to stdin.
            timeout: Execution timeout in seconds.
            policy: Sandbox strictness level.
            allow_network: Whether to allow network access.

        Returns:
            SandboxResult with stdout, stderr, exit_code, timing.
        """
        if timeout is None:
            timeout = float(self._config.max_cpu_seconds)

        # Create scratch directory
        scratch = self._scratch_base / f"run-{int(time.time() * 1000)}"
        scratch.mkdir(parents=True, exist_ok=True)

        try:
            bwrap_cmd = self.build_command(
                cmd,
                cwd=cwd,
                policy=policy,
                allow_network=allow_network,
                scratch_dir=scratch,
            )

            start_time = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *bwrap_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            timed_out = False
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=stdin_data),
                    timeout=timeout,
                )
            except TimeoutError:
                proc.kill()
                stdout, stderr = await proc.communicate()
                timed_out = True

            elapsed = (time.monotonic() - start_time) * 1000

            return SandboxResult(
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode or 0,
                timed_out=timed_out,
                duration_ms=elapsed,
            )
        finally:
            # Clean up scratch directory
            if scratch.exists():
                shutil.rmtree(scratch, ignore_errors=True)
