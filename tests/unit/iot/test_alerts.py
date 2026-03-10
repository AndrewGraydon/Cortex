"""Tests for SmartHomeAlertRouter."""

from __future__ import annotations

from cortex.iot.alerts import AlertRule, SmartHomeAlertRouter


class TestAlertRouter:
    def test_add_remove_rule(self) -> None:
        router = SmartHomeAlertRouter()
        rule = AlertRule(rule_id="r1", name="Test", priority=2)
        router.add_rule(rule)
        assert len(router.rules) == 1
        router.remove_rule("r1")
        assert len(router.rules) == 0


class TestStateChangeAlerts:
    def test_basic_state_change(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Light turned on",
            condition_type="state_change",
            condition_config={"to_state": "on"},
            priority=1,
            cooldown_seconds=0.0,
        ))

        alerts = router.evaluate_state_change(
            "light.kitchen", "light", "off", "on",
        )
        assert len(alerts) == 1
        assert alerts[0].title == "Light turned on"
        assert alerts[0].priority == 1

    def test_no_match_wrong_state(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Test",
            condition_type="state_change",
            condition_config={"to_state": "on"},
            cooldown_seconds=0.0,
        ))

        alerts = router.evaluate_state_change(
            "light.kitchen", "light", "on", "off",
        )
        assert len(alerts) == 0

    def test_device_filter(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Kitchen only",
            device_id="light.kitchen",
            condition_type="state_change",
            cooldown_seconds=0.0,
        ))

        # Wrong device
        alerts = router.evaluate_state_change(
            "light.bedroom", "light", "off", "on",
        )
        assert len(alerts) == 0

        # Correct device
        alerts = router.evaluate_state_change(
            "light.kitchen", "light", "off", "on",
        )
        assert len(alerts) == 1

    def test_category_filter(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Lights only",
            category="light",
            condition_type="state_change",
            cooldown_seconds=0.0,
        ))

        # Wrong category
        alerts = router.evaluate_state_change(
            "switch.plug", "switch", "off", "on",
        )
        assert len(alerts) == 0

        # Correct category
        alerts = router.evaluate_state_change(
            "light.kitchen", "light", "off", "on",
        )
        assert len(alerts) == 1

    def test_disabled_rule(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Disabled",
            condition_type="state_change",
            enabled=False,
        ))
        alerts = router.evaluate_state_change(
            "light.kitchen", "light", "off", "on",
        )
        assert len(alerts) == 0

    def test_cooldown(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Test",
            condition_type="state_change",
            cooldown_seconds=3600.0,
        ))

        # First fire
        alerts1 = router.evaluate_state_change(
            "light.kitchen", "light", "off", "on",
        )
        assert len(alerts1) == 1

        # Second fire — within cooldown
        alerts2 = router.evaluate_state_change(
            "light.kitchen", "light", "off", "on",
        )
        assert len(alerts2) == 0

    def test_from_state_filter(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Test",
            condition_type="state_change",
            condition_config={"from_state": "off", "to_state": "on"},
            cooldown_seconds=0.0,
        ))

        # Correct transition
        alerts = router.evaluate_state_change(
            "light.kitchen", "light", "off", "on",
        )
        assert len(alerts) == 1

        # Wrong from_state
        alerts = router.evaluate_state_change(
            "light.kitchen", "light", "on", "on",
        )
        assert len(alerts) == 0


class TestThresholdAlerts:
    def test_above_threshold(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="High temperature",
            condition_type="threshold",
            condition_config={
                "attribute": "temperature",
                "operator": "gt",
                "threshold": 30,
            },
            priority=3,
            cooldown_seconds=0.0,
        ))

        alerts = router.evaluate_state_change(
            "sensor.temp", "sensor", "25", "35",
            {"temperature": 35},
        )
        assert len(alerts) == 1
        assert alerts[0].priority == 3

    def test_below_threshold(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Low temp",
            condition_type="threshold",
            condition_config={
                "attribute": "temperature",
                "operator": "lt",
                "threshold": 10,
            },
            cooldown_seconds=0.0,
        ))

        alerts = router.evaluate_state_change(
            "sensor.temp", "sensor", "15", "5",
            {"temperature": 5},
        )
        assert len(alerts) == 1

    def test_not_triggered(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Test",
            condition_type="threshold",
            condition_config={
                "attribute": "temperature",
                "operator": "gt",
                "threshold": 30,
            },
            cooldown_seconds=0.0,
        ))

        alerts = router.evaluate_state_change(
            "sensor.temp", "sensor", "20", "25",
            {"temperature": 25},
        )
        assert len(alerts) == 0

    def test_missing_attribute(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Test",
            condition_type="threshold",
            condition_config={
                "attribute": "temperature",
                "operator": "gt",
                "threshold": 30,
            },
            cooldown_seconds=0.0,
        ))

        alerts = router.evaluate_state_change(
            "sensor.temp", "sensor", "20", "25",
            {"humidity": 50},
        )
        assert len(alerts) == 0


class TestOfflineAlerts:
    def test_device_offline(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Device offline",
            condition_type="offline",
            condition_config={"offline_seconds": 3600},
            priority=1,
            cooldown_seconds=0.0,
        ))

        # Not offline long enough
        alerts = router.evaluate_offline("light.test", "Test Light", 1800)
        assert len(alerts) == 0

        # Offline long enough
        alerts = router.evaluate_offline("light.test", "Test Light", 7200)
        assert len(alerts) == 1
        assert "offline" in alerts[0].title.lower()
        assert "120 minutes" in alerts[0].message

    def test_device_filter(self) -> None:
        router = SmartHomeAlertRouter()
        router.add_rule(AlertRule(
            rule_id="r1",
            name="Test",
            device_id="light.specific",
            condition_type="offline",
            condition_config={"offline_seconds": 60},
            cooldown_seconds=0.0,
        ))

        # Wrong device
        alerts = router.evaluate_offline("light.other", "Other", 120)
        assert len(alerts) == 0

        # Correct device
        alerts = router.evaluate_offline("light.specific", "Specific", 120)
        assert len(alerts) == 1
