"""Script-based tool loader — wraps TOOL.yaml + scripts/ as Tool protocol impl.

Executes script tools via subprocess with JSON stdin/stdout protocol.
Per DD-050, script tools are restricted to Tier 0-1 in Phase 3.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from cortex.agent.types import ToolResult

logger = logging.getLogger(__name__)


class ScriptTool:
    """A tool backed by a TOOL.yaml descriptor and an entry-point script.

    Execution protocol:
    - Arguments passed as JSON on stdin
    - Script writes JSON result to stdout: {"display_text": "...", "data": ...}
    - Exit code 0 = success, non-zero = failure
    """

    def __init__(
        self,
        tool_dir: Path,
        manifest: dict[str, Any],
    ) -> None:
        self._tool_dir = tool_dir
        self._manifest = manifest
        self._name: str = manifest["name"]
        self._description: str = manifest.get("description", "")
        self._permission_tier: int = manifest.get("permission_tier", 0)
        self._entry_point = tool_dir / manifest.get("entry_point", "scripts/run.py")
        self._timeout: float = float(manifest.get("timeout_seconds", 10))
        self._triggers: list[str] = manifest.get("triggers", [])
        self._keywords: list[str] = manifest.get("keywords", [])
        self._parameters: dict[str, Any] = manifest.get("parameters", {})
        self._enabled: bool = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def permission_tier(self) -> int:
        return self._permission_tier

    @property
    def triggers(self) -> list[str]:
        return self._triggers

    @property
    def keywords(self) -> list[str]:
        return self._keywords

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def tool_dir(self) -> Path:
        return self._tool_dir

    def get_schema(self) -> dict[str, Any]:
        """Return tool schema in OpenAI function calling format."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param_name, param_def in self._parameters.items():
            properties[param_name] = {"type": param_def.get("type", "string")}
            if param_def.get("description"):
                properties[param_name]["description"] = param_def["description"]
            if param_def.get("required", False):
                required.append(param_name)

        return {
            "name": self._name,
            "description": self._description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the script tool via subprocess."""
        if not self._enabled:
            return ToolResult(
                tool_name=self._name,
                success=False,
                error="Tool is disabled",
            )

        if not self._entry_point.exists():
            return ToolResult(
                tool_name=self._name,
                success=False,
                error=f"Entry point not found: {self._entry_point}",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(self._entry_point),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._tool_dir),
            )

            input_data = json.dumps(arguments).encode()
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=input_data),
                timeout=self._timeout,
            )

            if proc.returncode != 0:
                error_text = stderr.decode().strip() or f"Exit code {proc.returncode}"
                return ToolResult(
                    tool_name=self._name,
                    success=False,
                    error=error_text,
                )

            # Parse JSON output
            output = stdout.decode().strip()
            if output:
                result_data = json.loads(output)
                return ToolResult(
                    tool_name=self._name,
                    success=True,
                    data=result_data.get("data"),
                    display_text=result_data.get("display_text", ""),
                )
            return ToolResult(tool_name=self._name, success=True)

        except TimeoutError:
            return ToolResult(
                tool_name=self._name,
                success=False,
                error=f"Script timed out after {self._timeout}s",
            )
        except json.JSONDecodeError as e:
            return ToolResult(
                tool_name=self._name,
                success=False,
                error=f"Invalid JSON output: {e}",
            )
        except Exception as e:
            logger.exception("Script tool %s failed", self._name)
            return ToolResult(
                tool_name=self._name,
                success=False,
                error=str(e),
            )


def load_script_tool(tool_dir: Path) -> ScriptTool | None:
    """Load a single script tool from a directory containing TOOL.yaml."""
    manifest_path = tool_dir / "TOOL.yaml"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        if not isinstance(manifest, dict) or "name" not in manifest:
            logger.warning("Invalid TOOL.yaml in %s — missing 'name'", tool_dir)
            return None

        return ScriptTool(tool_dir, manifest)
    except Exception:
        logger.exception("Failed to load script tool from %s", tool_dir)
        return None
