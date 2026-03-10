"""Smart home alert router — IoT state changes to notifications.

Routes device state changes through configurable rules to generate
appropriate notifications with correct priorities.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """A configurable alert rule for IoT state changes."""

    rule_id: str
    name: str
    device_id: str = ""  # Empty = all devices
    category: str = ""  # Empty = all categories
    condition_type: str = "state_change"  # "state_change", "threshold", "offline"
    condition_config: dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # Notification priority 0-4
    enabled: bool = True
    cooldown_seconds: float = 300.0
    last_fired: float = 0.0


@dataclass
class AlertCandidate:
    """An alert to be delivered."""

    rule: AlertRule
    title: str
    message: str
    device_id: str
    priority: int


class SmartHomeAlertRouter:
    """Routes IoT state changes to notifications based on alert rules."""

    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}

    @property
    def rules(self) -> list[AlertRule]:
        return list(self._rules.values())

    def add_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> None:
        """Remove an alert rule."""
        self._rules.pop(rule_id, None)

    def evaluate_state_change(
        self,
        device_id: str,
        category: str,
        old_state: str,
        new_state: str,
        attributes: dict[str, Any] | None = None,
    ) -> list[AlertCandidate]:
        """Evaluate alert rules against a device state change."""
        candidates: list[AlertCandidate] = []
        now = time.time()

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            # Device/category filter
            if rule.device_id and rule.device_id != device_id:
                continue
            if rule.category and rule.category != category:
                continue

            # Cooldown
            if rule.last_fired and (now - rule.last_fired) < rule.cooldown_seconds:
                continue

            # Evaluate condition
            alert = self._evaluate_rule(
                rule, device_id, old_state, new_state, attributes or {},
            )
            if alert:
                rule.last_fired = now
                candidates.append(alert)

        return candidates

    def evaluate_offline(
        self,
        device_id: str,
        device_name: str,
        offline_seconds: float,
    ) -> list[AlertCandidate]:
        """Check for device offline alerts."""
        candidates: list[AlertCandidate] = []
        now = time.time()

        for rule in self._rules.values():
            if not rule.enabled:
                continue
            if rule.condition_type != "offline":
                continue
            if rule.device_id and rule.device_id != device_id:
                continue

            threshold = rule.condition_config.get("offline_seconds", 3600)
            if offline_seconds < threshold:
                continue

            # Cooldown
            if rule.last_fired and (now - rule.last_fired) < rule.cooldown_seconds:
                continue

            rule.last_fired = now
            candidates.append(AlertCandidate(
                rule=rule,
                title=f"{device_name} offline",
                message=f"{device_name} has been offline for {int(offline_seconds / 60)} minutes.",
                device_id=device_id,
                priority=rule.priority,
            ))

        return candidates

    def _evaluate_rule(
        self,
        rule: AlertRule,
        device_id: str,
        old_state: str,
        new_state: str,
        attributes: dict[str, Any],
    ) -> AlertCandidate | None:
        """Evaluate a single rule."""
        if rule.condition_type == "state_change":
            return self._eval_state_change(rule, device_id, old_state, new_state)
        if rule.condition_type == "threshold":
            return self._eval_threshold(rule, device_id, attributes)
        return None

    def _eval_state_change(
        self,
        rule: AlertRule,
        device_id: str,
        old_state: str,
        new_state: str,
    ) -> AlertCandidate | None:
        """Evaluate a state change rule."""
        config = rule.condition_config
        expected_from = config.get("from_state")
        expected_to = config.get("to_state")

        if expected_from and expected_from != old_state:
            return None
        if expected_to and expected_to != new_state:
            return None

        return AlertCandidate(
            rule=rule,
            title=rule.name,
            message=f"Device {device_id}: {old_state} → {new_state}",
            device_id=device_id,
            priority=rule.priority,
        )

    def _eval_threshold(
        self,
        rule: AlertRule,
        device_id: str,
        attributes: dict[str, Any],
    ) -> AlertCandidate | None:
        """Evaluate a threshold rule."""
        config = rule.condition_config
        attr_name = config.get("attribute", "")
        if not attr_name or attr_name not in attributes:
            return None

        value = float(attributes[attr_name])
        operator = config.get("operator", "gt")
        threshold = float(config.get("threshold", 0))

        triggered = (
            (operator == "gt" and value > threshold)
            or (operator == "lt" and value < threshold)
            or (operator == "eq" and value == threshold)
        )

        if not triggered:
            return None

        return AlertCandidate(
            rule=rule,
            title=rule.name,
            message=f"Device {device_id}: {attr_name}={value} ({operator} {threshold})",
            device_id=device_id,
            priority=rule.priority,
        )
