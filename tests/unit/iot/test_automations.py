"""Tests for AutomationEngine — rule CRUD and evaluation."""

from __future__ import annotations

import pytest

from cortex.iot.automations import AutomationEngine, AutomationRule


@pytest.fixture()
async def engine(tmp_path: object) -> AutomationEngine:
    eng = AutomationEngine(":memory:")
    await eng.start()
    yield eng  # type: ignore[misc]
    await eng.stop()


class TestAutomationRuleCRUD:
    @pytest.mark.asyncio()
    async def test_create_rule(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="", name="Test Rule",
            trigger_type="time",
            trigger_config={"hour": 22, "minute": 0},
            action_type="device_command",
            action_config={"device": "light.bedroom", "action": "turn_off"},
        )
        created = await engine.create_rule(rule)
        assert created.id  # Generated
        assert created.name == "Test Rule"
        assert engine.rule_count == 1

    @pytest.mark.asyncio()
    async def test_get_rule(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="test1", name="Test",
            trigger_type="time",
            action_type="device_command",
        )
        await engine.create_rule(rule)
        got = await engine.get_rule("test1")
        assert got is not None
        assert got.name == "Test"

    @pytest.mark.asyncio()
    async def test_get_rule_nonexistent(self, engine: AutomationEngine) -> None:
        assert await engine.get_rule("nonexistent") is None

    @pytest.mark.asyncio()
    async def test_delete_rule(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="test1", name="Test",
            trigger_type="time",
            action_type="device_command",
        )
        await engine.create_rule(rule)
        assert await engine.delete_rule("test1") is True
        assert engine.rule_count == 0

    @pytest.mark.asyncio()
    async def test_delete_nonexistent(self, engine: AutomationEngine) -> None:
        assert await engine.delete_rule("nonexistent") is False

    @pytest.mark.asyncio()
    async def test_set_enabled(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="test1", name="Test",
            trigger_type="time",
            action_type="device_command",
        )
        await engine.create_rule(rule)
        assert await engine.set_enabled("test1", False) is True
        got = await engine.get_rule("test1")
        assert got is not None
        assert got.enabled is False

    @pytest.mark.asyncio()
    async def test_set_enabled_nonexistent(self, engine: AutomationEngine) -> None:
        assert await engine.set_enabled("nonexistent", True) is False

    @pytest.mark.asyncio()
    async def test_rules_property(self, engine: AutomationEngine) -> None:
        for i in range(3):
            rule = AutomationRule(
                id=f"r{i}", name=f"Rule {i}",
                trigger_type="time",
                action_type="device_command",
            )
            await engine.create_rule(rule)
        assert len(engine.rules) == 3


class TestEvaluateStateChange:
    @pytest.mark.asyncio()
    async def test_matching_rule(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="r1", name="Light off at night",
            trigger_type="state_change",
            trigger_config={"device_id": "light.bedroom", "to_state": "off"},
            action_type="notification",
        )
        await engine.create_rule(rule)

        matched = engine.evaluate_state_change("light.bedroom", "on", "off")
        assert len(matched) == 1
        assert matched[0].id == "r1"

    @pytest.mark.asyncio()
    async def test_no_match_wrong_device(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="r1", name="Test",
            trigger_type="state_change",
            trigger_config={"device_id": "light.bedroom"},
            action_type="notification",
        )
        await engine.create_rule(rule)

        matched = engine.evaluate_state_change("light.kitchen", "on", "off")
        assert len(matched) == 0

    @pytest.mark.asyncio()
    async def test_no_match_wrong_state(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="r1", name="Test",
            trigger_type="state_change",
            trigger_config={"to_state": "on"},
            action_type="notification",
        )
        await engine.create_rule(rule)

        matched = engine.evaluate_state_change("light.bedroom", "on", "off")
        assert len(matched) == 0

    @pytest.mark.asyncio()
    async def test_disabled_rule(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="r1", name="Test",
            trigger_type="state_change",
            trigger_config={},
            action_type="notification",
            enabled=False,
        )
        await engine.create_rule(rule)

        matched = engine.evaluate_state_change("light.bedroom", "on", "off")
        assert len(matched) == 0

    @pytest.mark.asyncio()
    async def test_with_condition(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="r1", name="Bright alert",
            trigger_type="state_change",
            trigger_config={"device_id": "light.bedroom"},
            condition_config={"attribute": "brightness", "operator": "gt", "value": 200},
            action_type="notification",
        )
        await engine.create_rule(rule)

        # Below threshold
        matched = engine.evaluate_state_change(
            "light.bedroom", "off", "on", {"brightness": 100},
        )
        assert len(matched) == 0

        # Above threshold
        matched = engine.evaluate_state_change(
            "light.bedroom", "off", "on", {"brightness": 255},
        )
        assert len(matched) == 1


class TestEvaluateTime:
    @pytest.mark.asyncio()
    async def test_matching_time(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="r1", name="Lights off at 22:00",
            trigger_type="time",
            trigger_config={"hour": 22, "minute": 0},
            action_type="device_command",
        )
        await engine.create_rule(rule)

        matched = engine.evaluate_time(22, 0)
        assert len(matched) == 1

    @pytest.mark.asyncio()
    async def test_no_match_wrong_time(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="r1", name="Test",
            trigger_type="time",
            trigger_config={"hour": 22, "minute": 0},
            action_type="device_command",
        )
        await engine.create_rule(rule)

        matched = engine.evaluate_time(21, 59)
        assert len(matched) == 0


class TestMarkFired:
    @pytest.mark.asyncio()
    async def test_mark_fired(self, engine: AutomationEngine) -> None:
        rule = AutomationRule(
            id="r1", name="Test",
            trigger_type="time",
            action_type="device_command",
        )
        await engine.create_rule(rule)
        await engine.mark_fired(rule)
        assert rule.fire_count == 1
        assert rule.last_fired > 0


class TestSuggestFromPatterns:
    def test_suggest(self) -> None:
        engine = AutomationEngine()
        patterns = [
            {"content": "kitchen_light", "count": 10, "hour": 22},
        ]
        suggestions = engine.suggest_from_patterns(patterns)
        assert len(suggestions) == 1
        assert "kitchen_light" in suggestions[0].name
        assert suggestions[0].trigger_config["hour"] == 22

    def test_skip_low_count(self) -> None:
        engine = AutomationEngine()
        patterns = [{"content": "test", "count": 2, "hour": 8}]
        suggestions = engine.suggest_from_patterns(patterns)
        assert len(suggestions) == 0
