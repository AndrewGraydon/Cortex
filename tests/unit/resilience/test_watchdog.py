"""Tests for systemd watchdog — no-op on non-systemd, heartbeat, lifecycle."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cortex.resilience.watchdog import SystemdWatchdog, _is_systemd, _sd_notify


class TestIsSystemd:
    """Detection of systemd environment."""

    def test_not_systemd_without_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert _is_systemd() is False

    def test_is_systemd_with_env(self) -> None:
        with patch.dict("os.environ", {"WATCHDOG_USEC": "30000000"}):
            assert _is_systemd() is True

    def test_empty_string_is_not_systemd(self) -> None:
        with patch.dict("os.environ", {"WATCHDOG_USEC": ""}):
            assert _is_systemd() is False


class TestSdNotify:
    """Low-level sd_notify function."""

    def test_no_op_without_notify_socket(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert _sd_notify("WATCHDOG=1") is False


class TestSystemdWatchdog:
    """Watchdog lifecycle tests."""

    def test_disabled_on_macos(self) -> None:
        """Without WATCHDOG_USEC, watchdog is disabled."""
        with patch.dict("os.environ", {}, clear=True):
            wd = SystemdWatchdog()
            assert wd.enabled is False
            assert wd.running is False

    def test_notify_noop_when_disabled(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            wd = SystemdWatchdog()
            assert wd.notify() is False
            assert wd.notify_ready() is False
            assert wd.notify_stopping() is False

    @pytest.mark.asyncio()
    async def test_start_stop_when_disabled(self) -> None:
        """Start/stop are no-ops when not under systemd."""
        with patch.dict("os.environ", {}, clear=True):
            wd = SystemdWatchdog()
            await wd.start()
            assert wd.running is True  # Flag set, but no task
            assert wd._task is None  # No heartbeat task created
            await wd.stop()
            assert wd.running is False

    @pytest.mark.asyncio()
    async def test_start_creates_task_when_enabled(self) -> None:
        with patch.dict(
            "os.environ",
            {"WATCHDOG_USEC": "30000000", "NOTIFY_SOCKET": "/tmp/test.sock"},
        ):
            wd = SystemdWatchdog(interval_s=0.1)
            # Re-check enabled since __init__ already ran
            wd._enabled = True
            await wd.start()
            assert wd._task is not None
            await wd.stop()

    @pytest.mark.asyncio()
    async def test_double_start_is_noop(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            wd = SystemdWatchdog()
            await wd.start()
            await wd.start()  # Should not error
            await wd.stop()

    def test_custom_interval(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            wd = SystemdWatchdog(interval_s=5.0)
            assert wd._interval_s == 5.0
