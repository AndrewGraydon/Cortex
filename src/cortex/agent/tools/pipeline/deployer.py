"""Tool deployer — writes approved tools to the filesystem and registers them.

Deploys tools to tools/user-created/<name>/ with TOOL.yaml + scripts/run.py.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import yaml

from cortex.agent.tools.pipeline.types import PipelineStage, ToolDraft

logger = logging.getLogger(__name__)


class ToolDeployer:
    """Deploys approved tool drafts to the filesystem.

    Args:
        user_tools_dir: Base directory for user-created tools.
        max_tools: Maximum number of deployed tools.
    """

    def __init__(
        self,
        user_tools_dir: Path,
        max_tools: int = 50,
    ) -> None:
        self._user_tools_dir = user_tools_dir
        self._max_tools = max_tools

    @property
    def user_tools_dir(self) -> Path:
        return self._user_tools_dir

    def deploy(self, draft: ToolDraft) -> Path:
        """Deploy an approved tool draft to the filesystem.

        Args:
            draft: Approved tool draft.

        Returns:
            Path to the deployed tool directory.

        Raises:
            ValueError: If draft is not approved or limits exceeded.
        """
        if draft.stage != PipelineStage.APPROVED:
            msg = f"Tool must be approved before deployment (current: {draft.stage.value})"
            raise ValueError(msg)

        # Check tool limit
        existing = self.list_deployed()
        if len(existing) >= self._max_tools:
            msg = f"Maximum tool limit ({self._max_tools}) reached"
            raise ValueError(msg)

        # Check for name collision
        tool_dir = self._user_tools_dir / draft.spec.name
        if tool_dir.exists():
            msg = f"Tool '{draft.spec.name}' already exists at {tool_dir}"
            raise ValueError(msg)

        # Create directory structure
        tool_dir.mkdir(parents=True)
        scripts_dir = tool_dir / "scripts"
        scripts_dir.mkdir()

        # Write TOOL.yaml
        (tool_dir / "TOOL.yaml").write_text(draft.manifest_yaml)

        # Write entry point script
        (scripts_dir / "run.py").write_text(draft.script_code)

        # Update draft stage
        draft.stage = PipelineStage.DEPLOYED
        draft.updated_at = time.time()

        logger.info("Deployed tool '%s' to %s", draft.spec.name, tool_dir)
        return tool_dir

    def remove(self, name: str) -> bool:
        """Remove a deployed tool.

        Args:
            name: Tool name to remove.

        Returns:
            True if removed, False if not found.
        """
        import shutil

        tool_dir = self._user_tools_dir / name
        if not tool_dir.exists():
            return False

        shutil.rmtree(tool_dir)
        logger.info("Removed tool '%s' from %s", name, tool_dir)
        return True

    def list_deployed(self) -> list[dict[str, Any]]:
        """List all deployed user-created tools.

        Returns:
            List of tool info dicts with name, path, manifest data.
        """
        if not self._user_tools_dir.exists():
            return []

        tools: list[dict[str, Any]] = []
        for entry in sorted(self._user_tools_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "TOOL.yaml"
            if not manifest_path.exists():
                continue
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)
                tools.append(
                    {
                        "name": manifest.get("name", entry.name),
                        "path": str(entry),
                        "description": manifest.get("description", ""),
                        "permission_tier": manifest.get("permission_tier", 2),
                    }
                )
            except Exception:
                logger.warning("Failed to read manifest at %s", manifest_path)
        return tools
