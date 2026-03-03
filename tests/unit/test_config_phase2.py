"""Tests for Phase 2 config models — agent, security, memory, scheduling, etc."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from cortex.config import CortexConfig, load_config


class TestAgentConfigDefaults:
    def test_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.agent.enabled is True
        assert cfg.agent.max_tool_iterations == 2
        assert cfg.agent.confidence_threshold == 0.6
        assert cfg.agent.actions_dir == "config/actions"


class TestSecurityConfigDefaults:
    def test_audit_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.security.audit.enabled is True
        assert cfg.security.audit.db_path == "data/audit.db"
        assert cfg.security.audit.retention_days == 90

    def test_approval_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.security.approval.timeout_seconds == 60.0
        assert cfg.security.approval.default_deny_on_timeout is True


class TestMemoryConfigDefaults:
    def test_top_level_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.memory.db_path == "data/memory.db"
        assert cfg.memory.extraction_idle_timeout == 300
        assert cfg.memory.regex_patterns is True

    def test_short_term_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.memory.short_term.retention_days == 30
        assert cfg.memory.short_term.max_conversations == 100

    def test_long_term_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.memory.long_term.max_entries == 10000
        assert cfg.memory.long_term.similarity_threshold == 0.3
        assert cfg.memory.long_term.dedup_threshold == 0.85
        assert cfg.memory.long_term.auto_inject_count == 3
        assert cfg.memory.long_term.embedding_dimensions == 384


class TestSchedulingConfigDefaults:
    def test_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.scheduling.db_path == "data/schedules.db"
        assert cfg.scheduling.max_active_timers == 20
        assert cfg.scheduling.max_active_reminders == 100
        assert cfg.scheduling.snooze_duration == 600
        assert cfg.scheduling.max_snoozes == 3


class TestNotificationConfigDefaults:
    def test_dnd_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.notifications.dnd.enabled is False
        assert cfg.notifications.dnd.start_hour == 22
        assert cfg.notifications.dnd.end_hour == 7

    def test_priority_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.notifications.timer_complete_priority == 2
        assert cfg.notifications.reminder_due_priority == 3
        assert cfg.notifications.system_health_priority == 2


class TestHealthConfigDefaults:
    def test_defaults(self) -> None:
        cfg = CortexConfig()
        assert cfg.health.enabled is True
        assert cfg.health.endpoint == "/api/health"
        assert cfg.health.npu_poll_interval == 5
        assert cfg.health.cpu_poll_interval == 10
        assert cfg.health.memory_poll_interval == 30


class TestReasoningConfigMaxContext:
    def test_max_context_tokens(self) -> None:
        cfg = CortexConfig()
        assert cfg.reasoning.max_context_tokens == 2047


class TestPhase2ConfigLoading:
    def test_load_phase2_overrides(self, tmp_path: Path) -> None:
        config_file = tmp_path / "cortex.yaml"
        config_file.write_text(
            dedent("""\
                agent:
                  max_tool_iterations: 3
                  confidence_threshold: 0.8
                security:
                  audit:
                    retention_days: 30
                  approval:
                    timeout_seconds: 30.0
                memory:
                  long_term:
                    similarity_threshold: 0.5
                    auto_inject_count: 5
                scheduling:
                  max_active_timers: 10
                notifications:
                  dnd:
                    enabled: true
                    start_hour: 23
                health:
                  npu_poll_interval: 10
            """)
        )
        cfg = load_config(config_file)
        assert cfg.agent.max_tool_iterations == 3
        assert cfg.agent.confidence_threshold == 0.8
        assert cfg.security.audit.retention_days == 30
        assert cfg.security.approval.timeout_seconds == 30.0
        assert cfg.memory.long_term.similarity_threshold == 0.5
        assert cfg.memory.long_term.auto_inject_count == 5
        assert cfg.scheduling.max_active_timers == 10
        assert cfg.notifications.dnd.enabled is True
        assert cfg.notifications.dnd.start_hour == 23
        assert cfg.health.npu_poll_interval == 10

    def test_phase2_json_round_trip(self) -> None:
        cfg = CortexConfig()
        json_str = cfg.model_dump_json()
        restored = CortexConfig.model_validate_json(json_str)
        assert restored.agent == cfg.agent
        assert restored.security == cfg.security
        assert restored.memory == cfg.memory
        assert restored.scheduling == cfg.scheduling
        assert restored.notifications == cfg.notifications
        assert restored.health == cfg.health
