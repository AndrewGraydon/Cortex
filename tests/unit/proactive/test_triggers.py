"""Tests for EventTrigger system."""

from __future__ import annotations

from cortex.agent.proactive.triggers import EventTrigger, TriggerManager
from cortex.agent.proactive.types import ProactiveCandidate, ProactiveType


class TestTriggerManager:
    def test_register(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test", event_type="iot_state",
        )
        manager.register(trigger)
        assert len(manager.triggers) == 1

    def test_unregister(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test", event_type="iot_state",
        )
        manager.register(trigger)
        manager.unregister("t1")
        assert len(manager.triggers) == 0

    def test_unregister_nonexistent(self) -> None:
        manager = TriggerManager()
        manager.unregister("nonexistent")  # should not raise

    def test_evaluate_no_match(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test", event_type="iot_state",
        )
        manager.register(trigger)
        result = manager.evaluate("timer_fire", {})
        assert len(result.candidates) == 0
        assert result.triggers_fired == 0

    def test_evaluate_match(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test Alert", event_type="iot_state",
            cooldown_seconds=0.0,
        )
        manager.register(trigger)
        result = manager.evaluate("iot_state", {"device_id": "light.1"})
        assert len(result.candidates) == 1
        assert result.triggers_fired == 1
        assert result.candidates[0].title == "Test Alert"

    def test_evaluate_with_condition(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="High Temp",
            event_type="iot_state",
            condition=lambda d: d.get("temperature", 0) > 30,
            cooldown_seconds=0.0,
        )
        manager.register(trigger)

        # Below threshold
        result = manager.evaluate("iot_state", {"temperature": 20})
        assert len(result.candidates) == 0

        # Above threshold
        result = manager.evaluate("iot_state", {"temperature": 35})
        assert len(result.candidates) == 1

    def test_evaluate_disabled_trigger(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test", event_type="iot_state",
            enabled=False,
        )
        manager.register(trigger)
        result = manager.evaluate("iot_state", {})
        assert len(result.candidates) == 0

    def test_evaluate_cooldown(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test", event_type="iot_state",
            cooldown_seconds=3600.0,
        )
        manager.register(trigger)

        # First fire
        result1 = manager.evaluate("iot_state", {})
        assert result1.triggers_fired == 1

        # Second fire — within cooldown
        result2 = manager.evaluate("iot_state", {})
        assert result2.triggers_fired == 0

    def test_fire_count(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test", event_type="iot_state",
            cooldown_seconds=0.0,
        )
        manager.register(trigger)

        manager.evaluate("iot_state", {})
        manager.evaluate("iot_state", {})
        assert trigger.fire_count == 2

    def test_custom_candidate_builder(self) -> None:
        def build(data: dict) -> ProactiveCandidate:
            return ProactiveCandidate(
                proactive_type=ProactiveType.IOT_ALERT,
                title=f"Custom: {data.get('name', 'unknown')}",
                message="Custom alert",
                priority=3,
            )

        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Custom", event_type="iot_state",
            candidate_builder=build,
            cooldown_seconds=0.0,
        )
        manager.register(trigger)

        result = manager.evaluate("iot_state", {"name": "Kitchen"})
        assert result.candidates[0].title == "Custom: Kitchen"

    def test_clear(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test", event_type="iot_state",
        )
        manager.register(trigger)
        manager.clear()
        assert len(manager.triggers) == 0

    def test_default_candidate_metadata(self) -> None:
        manager = TriggerManager()
        trigger = EventTrigger(
            trigger_id="t1", name="Test", event_type="iot_state",
            cooldown_seconds=0.0,
        )
        manager.register(trigger)

        result = manager.evaluate("iot_state", {"key": "value"})
        candidate = result.candidates[0]
        assert candidate.metadata["trigger_id"] == "t1"
        assert candidate.metadata["key"] == "value"
