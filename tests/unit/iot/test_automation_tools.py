"""Tests for automation tools (query, create, delete)."""

from __future__ import annotations

import pytest

from cortex.agent.tools.builtin.automation_tool import (
    AutomationCreateTool,
    AutomationDeleteTool,
    AutomationQueryTool,
    set_automation_backend,
)
from cortex.iot.automations import AutomationEngine


@pytest.fixture()
async def engine() -> AutomationEngine:
    eng = AutomationEngine(":memory:")
    await eng.start()
    yield eng  # type: ignore[misc]
    await eng.stop()


@pytest.fixture(autouse=True)
async def _wire(engine: AutomationEngine) -> None:
    set_automation_backend(engine)
    yield  # type: ignore[misc]
    set_automation_backend(None)


class TestAutomationQueryTool:
    def test_schema(self) -> None:
        tool = AutomationQueryTool()
        assert tool.get_schema()["name"] == "automation_query"
        assert tool.name == "automation_query"
        assert tool.permission_tier == 0

    @pytest.mark.asyncio()
    async def test_no_backend(self) -> None:
        set_automation_backend(None)
        tool = AutomationQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert "not configured" in result.display_text

    @pytest.mark.asyncio()
    async def test_empty_rules(self) -> None:
        tool = AutomationQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert "No automation" in result.display_text

    @pytest.mark.asyncio()
    async def test_with_rules(self, engine: AutomationEngine) -> None:
        from cortex.iot.automations import AutomationRule

        await engine.create_rule(AutomationRule(
            id="r1", name="Test Rule",
            trigger_type="time",
            action_type="device_command",
        ))

        tool = AutomationQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert "1 automation" in result.display_text
        assert "Test Rule" in result.display_text


class TestAutomationCreateTool:
    def test_schema(self) -> None:
        tool = AutomationCreateTool()
        schema = tool.get_schema()
        assert schema["name"] == "automation_create"
        assert "name" in schema["parameters"]["properties"]
        assert tool.permission_tier == 2

    @pytest.mark.asyncio()
    async def test_no_backend(self) -> None:
        set_automation_backend(None)
        tool = AutomationCreateTool()
        result = await tool.execute({
            "name": "test", "trigger_type": "time", "action_type": "device_command",
        })
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_empty_name(self) -> None:
        tool = AutomationCreateTool()
        result = await tool.execute({
            "name": "", "trigger_type": "time", "action_type": "device_command",
        })
        assert result.success is False
        assert "required" in (result.error or "").lower()

    @pytest.mark.asyncio()
    async def test_create_success(self) -> None:
        tool = AutomationCreateTool()
        result = await tool.execute({
            "name": "Lights off at night",
            "trigger_type": "time",
            "trigger_config": {"hour": 22, "minute": 0},
            "action_type": "device_command",
            "action_config": {"device": "light.bedroom", "action": "turn_off"},
        })
        assert result.success is True
        assert "Lights off at night" in result.display_text


class TestAutomationDeleteTool:
    def test_schema(self) -> None:
        tool = AutomationDeleteTool()
        assert tool.get_schema()["name"] == "automation_delete"
        assert tool.permission_tier == 2

    @pytest.mark.asyncio()
    async def test_no_backend(self) -> None:
        set_automation_backend(None)
        tool = AutomationDeleteTool()
        result = await tool.execute({"rule_id": "r1"})
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_empty_rule_id(self) -> None:
        tool = AutomationDeleteTool()
        result = await tool.execute({"rule_id": ""})
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_delete_success(self, engine: AutomationEngine) -> None:
        from cortex.iot.automations import AutomationRule

        await engine.create_rule(AutomationRule(
            id="r1", name="Test",
            trigger_type="time",
            action_type="device_command",
        ))

        tool = AutomationDeleteTool()
        result = await tool.execute({"rule_id": "r1"})
        assert result.success is True

    @pytest.mark.asyncio()
    async def test_delete_nonexistent(self) -> None:
        tool = AutomationDeleteTool()
        result = await tool.execute({"rule_id": "nonexistent"})
        assert result.success is False
