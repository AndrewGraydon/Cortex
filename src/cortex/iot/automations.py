"""Automation engine — rule-based smart home automations.

SQLite rule store with trigger + condition + action model. LLM proposes
rules from detected patterns; runtime execution is pure rule-based.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    trigger_config TEXT NOT NULL DEFAULT '{}',
    condition_config TEXT NOT NULL DEFAULT '{}',
    action_type TEXT NOT NULL,
    action_config TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    last_fired REAL NOT NULL DEFAULT 0,
    fire_count INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class AutomationRule:
    """A stored automation rule."""

    id: str
    name: str
    trigger_type: str  # "time", "state_change", "pattern"
    trigger_config: dict[str, Any] = field(default_factory=dict)
    condition_config: dict[str, Any] = field(default_factory=dict)
    action_type: str = "device_command"  # "device_command", "notification"
    action_config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: float = 0.0
    last_fired: float = 0.0
    fire_count: int = 0


class AutomationEngine:
    """Manages and evaluates smart home automation rules.

    Rules are stored in SQLite. Evaluation is rule-based at runtime
    (no LLM inference per evaluation). LLM only proposes new rules
    from detected patterns.
    """

    def __init__(self, db_path: str = "data/automations.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._rules: dict[str, AutomationRule] = {}

    async def start(self) -> None:
        """Open database and load rules."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_CREATE_TABLE_SQL)
        await self._db.commit()
        await self._load_rules()

    async def stop(self) -> None:
        """Close database."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def rules(self) -> list[AutomationRule]:
        return list(self._rules.values())

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    async def create_rule(self, rule: AutomationRule) -> AutomationRule:
        """Create a new automation rule."""
        if not rule.id:
            rule.id = uuid.uuid4().hex[:8]
        if not rule.created_at:
            rule.created_at = time.time()

        db = self._ensure_started()
        await db.execute(
            """INSERT INTO automations
               (id, name, trigger_type, trigger_config, condition_config,
                action_type, action_config, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rule.id,
                rule.name,
                rule.trigger_type,
                json.dumps(rule.trigger_config),
                json.dumps(rule.condition_config),
                rule.action_type,
                json.dumps(rule.action_config),
                1 if rule.enabled else 0,
                rule.created_at,
            ),
        )
        await db.commit()
        self._rules[rule.id] = rule
        logger.info("Automation '%s' created", rule.name)
        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete an automation rule."""
        db = self._ensure_started()
        cursor = await db.execute(
            "DELETE FROM automations WHERE id = ?", (rule_id,),
        )
        await db.commit()
        self._rules.pop(rule_id, None)
        return cursor.rowcount > 0

    async def get_rule(self, rule_id: str) -> AutomationRule | None:
        """Get a rule by ID."""
        return self._rules.get(rule_id)

    async def set_enabled(self, rule_id: str, enabled: bool) -> bool:
        """Enable or disable a rule."""
        rule = self._rules.get(rule_id)
        if rule is None:
            return False
        rule.enabled = enabled
        db = self._ensure_started()
        await db.execute(
            "UPDATE automations SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, rule_id),
        )
        await db.commit()
        return True

    def evaluate_state_change(
        self,
        device_id: str,
        old_state: str,
        new_state: str,
        attributes: dict[str, Any] | None = None,
    ) -> list[AutomationRule]:
        """Evaluate rules against a device state change.

        Returns rules that should fire.
        """
        matched: list[AutomationRule] = []
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            if rule.trigger_type != "state_change":
                continue

            config = rule.trigger_config
            # Check device match
            if config.get("device_id") and config["device_id"] != device_id:
                continue
            # Check state transition
            if config.get("from_state") and config["from_state"] != old_state:
                continue
            if config.get("to_state") and config["to_state"] != new_state:
                continue

            # Check condition
            if rule.condition_config and not self._check_condition(
                rule.condition_config, attributes or {},
            ):
                continue

            matched.append(rule)
        return matched

    def evaluate_time(self, hour: int, minute: int) -> list[AutomationRule]:
        """Evaluate time-based rules."""
        matched: list[AutomationRule] = []
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            if rule.trigger_type != "time":
                continue
            config = rule.trigger_config
            if config.get("hour") == hour and config.get("minute") == minute:
                matched.append(rule)
        return matched

    async def mark_fired(self, rule: AutomationRule) -> None:
        """Record that a rule fired."""
        rule.fire_count += 1
        rule.last_fired = time.time()
        db = self._ensure_started()
        await db.execute(
            "UPDATE automations SET fire_count = ?, last_fired = ? WHERE id = ?",
            (rule.fire_count, rule.last_fired, rule.id),
        )
        await db.commit()

    def suggest_from_patterns(
        self,
        patterns: list[dict[str, Any]],
    ) -> list[AutomationRule]:
        """Suggest automation rules from detected usage patterns.

        Pure rule-based suggestion (no LLM needed).
        """
        suggestions: list[AutomationRule] = []
        for pattern in patterns:
            content = pattern.get("content", "")
            count = pattern.get("count", 0)
            hour = pattern.get("hour", 0)

            if count < 5:
                continue

            suggestion = AutomationRule(
                id="",
                name=f"Auto: {content} at {hour}:00",
                trigger_type="time",
                trigger_config={"hour": hour, "minute": 0},
                action_type="device_command",
                action_config={"device": content, "action": "turn_on"},
            )
            suggestions.append(suggestion)
        return suggestions

    # --- Internal ---

    def _ensure_started(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "AutomationEngine not started"
            raise RuntimeError(msg)
        return self._db

    async def _load_rules(self) -> None:
        """Load all rules from database."""
        db = self._ensure_started()
        cursor = await db.execute("SELECT * FROM automations")
        rows = await cursor.fetchall()
        for row in rows:
            rule = AutomationRule(
                id=str(row[0]),
                name=str(row[1]),
                trigger_type=str(row[2]),
                trigger_config=json.loads(str(row[3])),
                condition_config=json.loads(str(row[4])),
                action_type=str(row[5]),
                action_config=json.loads(str(row[6])),
                enabled=bool(row[7]),
                created_at=float(str(row[8])),
                last_fired=float(str(row[9])),
                fire_count=int(str(row[10])),
            )
            self._rules[rule.id] = rule

    @staticmethod
    def _check_condition(
        condition: dict[str, Any], attributes: dict[str, Any],
    ) -> bool:
        """Evaluate a condition against device attributes."""
        # Simple threshold check
        attr_name = condition.get("attribute")
        if not attr_name:
            return True
        value = attributes.get(attr_name)
        if value is None:
            return False

        op = condition.get("operator", "eq")
        threshold = condition.get("value")
        if threshold is None:
            return True

        if op == "gt":
            return float(value) > float(threshold)
        if op == "lt":
            return float(value) < float(threshold)
        if op == "eq":
            return str(value) == str(threshold)
        return True
