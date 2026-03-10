"""Automation tools — query, create, and delete smart home automations.

Wired to AutomationEngine. Falls back to stub responses if not configured.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.types import ToolResult

logger = logging.getLogger(__name__)

_engine: Any = None


def set_automation_backend(engine: Any) -> None:
    """Wire the automation tools to an AutomationEngine."""
    global _engine  # noqa: PLW0603
    _engine = engine


def get_automation_backend() -> Any:
    """Get the current automation backend (for testing)."""
    return _engine


class AutomationQueryTool:
    """List automation rules. Tier 0 (safe, read-only)."""

    @property
    def name(self) -> str:
        return "automation_query"

    @property
    def description(self) -> str:
        return "List smart home automation rules"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "automation_query",
            "description": "List smart home automation rules",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _engine is None:
            return ToolResult(
                tool_name="automation_query",
                success=True,
                data=[],
                display_text="Automations are not configured.",
            )

        rules = _engine.rules
        if not rules:
            return ToolResult(
                tool_name="automation_query",
                success=True,
                data=[],
                display_text="No automation rules configured.",
            )

        data = [
            {
                "id": r.id,
                "name": r.name,
                "trigger_type": r.trigger_type,
                "enabled": r.enabled,
                "fire_count": r.fire_count,
            }
            for r in rules
        ]

        names = [r.name for r in rules]
        display = f"You have {len(rules)} automation(s): {', '.join(names)}."

        return ToolResult(
            tool_name="automation_query",
            success=True,
            data=data,
            display_text=display,
        )


class AutomationCreateTool:
    """Create an automation rule. Tier 2 (requires approval)."""

    @property
    def name(self) -> str:
        return "automation_create"

    @property
    def description(self) -> str:
        return "Create a smart home automation rule"

    @property
    def permission_tier(self) -> int:
        return 2

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "automation_create",
            "description": "Create a smart home automation rule",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Rule name",
                    },
                    "trigger_type": {
                        "type": "string",
                        "description": "Trigger: time, state_change",
                    },
                    "trigger_config": {
                        "type": "object",
                        "description": "Trigger configuration",
                    },
                    "action_type": {
                        "type": "string",
                        "description": "Action: device_command, notification",
                    },
                    "action_config": {
                        "type": "object",
                        "description": "Action configuration",
                    },
                },
                "required": ["name", "trigger_type", "action_type"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _engine is None:
            return ToolResult(
                tool_name="automation_create",
                success=False,
                error="Automations are not configured.",
            )

        from cortex.iot.automations import AutomationRule

        name = arguments.get("name", "").strip()
        if not name:
            return ToolResult(
                tool_name="automation_create",
                success=False,
                error="Automation name is required.",
            )

        rule = AutomationRule(
            id="",
            name=name,
            trigger_type=arguments.get("trigger_type", "time"),
            trigger_config=arguments.get("trigger_config", {}),
            action_type=arguments.get("action_type", "device_command"),
            action_config=arguments.get("action_config", {}),
        )

        try:
            created = await _engine.create_rule(rule)
            return ToolResult(
                tool_name="automation_create",
                success=True,
                data={"id": created.id, "name": created.name},
                display_text=f"Automation '{created.name}' created.",
            )
        except Exception as e:
            return ToolResult(
                tool_name="automation_create",
                success=False,
                error=str(e),
            )


class AutomationDeleteTool:
    """Delete an automation rule. Tier 2 (requires approval)."""

    @property
    def name(self) -> str:
        return "automation_delete"

    @property
    def description(self) -> str:
        return "Delete a smart home automation rule"

    @property
    def permission_tier(self) -> int:
        return 2

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "automation_delete",
            "description": "Delete a smart home automation rule",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_id": {
                        "type": "string",
                        "description": "Automation rule ID",
                    },
                },
                "required": ["rule_id"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _engine is None:
            return ToolResult(
                tool_name="automation_delete",
                success=False,
                error="Automations are not configured.",
            )

        rule_id = arguments.get("rule_id", "").strip()
        if not rule_id:
            return ToolResult(
                tool_name="automation_delete",
                success=False,
                error="Rule ID is required.",
            )

        deleted = await _engine.delete_rule(rule_id)
        if deleted:
            return ToolResult(
                tool_name="automation_delete",
                success=True,
                data={"rule_id": rule_id},
                display_text=f"Automation '{rule_id}' deleted.",
            )
        return ToolResult(
            tool_name="automation_delete",
            success=False,
            error=f"Automation '{rule_id}' not found.",
        )
