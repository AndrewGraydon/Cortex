"""System info tool — CPU, memory, uptime. Tier 0 (safe)."""

from __future__ import annotations

import os
import time
from typing import Any

from cortex.agent.types import ToolResult

_BOOT_TIME = time.monotonic()


class SystemInfoTool:
    """Returns basic system information."""

    @property
    def name(self) -> str:
        return "system_info"

    @property
    def description(self) -> str:
        return "Get system status (CPU, memory, uptime)"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "system_info",
            "description": "Get system status (CPU, memory, uptime)",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        uptime_s = time.monotonic() - _BOOT_TIME
        hours = int(uptime_s // 3600)
        minutes = int((uptime_s % 3600) // 60)

        info: dict[str, Any] = {
            "uptime_seconds": int(uptime_s),
        }

        # CPU load (available on Linux/macOS)
        try:
            load = os.getloadavg()
            info["load_1m"] = round(load[0], 2)
            info["load_5m"] = round(load[1], 2)
        except OSError:
            pass

        # Format display text
        parts = [f"Uptime: {hours}h {minutes}m"]
        if "load_1m" in info:
            parts.append(f"Load: {info['load_1m']}")

        display = ". ".join(parts) + "."

        return ToolResult(
            tool_name="system_info",
            success=True,
            data=info,
            display_text=display,
        )
