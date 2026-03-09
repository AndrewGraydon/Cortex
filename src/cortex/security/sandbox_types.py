"""Sandbox types — configuration and results for bubblewrap execution."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class SandboxPolicy(enum.Enum):
    """Sandbox strictness levels."""

    NONE = "none"  # No sandbox (Tier 0-1 tools)
    BASIC = "basic"  # Filesystem isolation, no network
    STRICT = "strict"  # Full isolation + resource limits


@dataclass
class SandboxConfig:
    """Configuration for the bubblewrap sandbox."""

    enabled: bool = True
    bwrap_path: str = "/usr/bin/bwrap"
    scratch_dir: str = "data/sandbox"
    max_memory_mb: int = 256
    max_cpu_seconds: int = 30
    network_default: bool = False


@dataclass
class SandboxResult:
    """Result from a sandboxed execution."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    duration_ms: float = 0.0
