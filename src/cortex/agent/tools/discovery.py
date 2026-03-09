"""Tool discovery — scans directories for TOOL.yaml script tools.

Discovers script-based tools and registers them with the ToolRegistry.
Supports hot-reload via SIGHUP or explicit scan.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cortex.agent.tools.script_loader import ScriptTool, load_script_tool

logger = logging.getLogger(__name__)


def discover_script_tools(
    tools_dir: Path,
    user_tools_dir: Path | None = None,
) -> list[ScriptTool]:
    """Scan directories for script tools.

    Looks for subdirectories containing TOOL.yaml files.
    Scans both the built-in tools_dir and optional user_tools_dir.
    Returns a list of successfully loaded ScriptTool instances.
    """
    tools: list[ScriptTool] = []

    for scan_dir in [tools_dir, user_tools_dir]:
        if scan_dir is None or not scan_dir.is_dir():
            if scan_dir is not None:
                logger.debug("Tools directory does not exist: %s", scan_dir)
            continue

        for entry in sorted(scan_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name.startswith("_"):
                continue

            tool = load_script_tool(entry)
            if tool is not None:
                tools.append(tool)
                logger.info(
                    "Discovered script tool: %s (tier %d, %s)",
                    tool.name,
                    tool.permission_tier,
                    entry.name,
                )

    logger.info("Discovered %d script tool(s)", len(tools))
    return tools
