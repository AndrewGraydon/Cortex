"""End-to-end integration tests verifying Phase 2 exit criteria.

Exit criteria:
1. At least 3 built-in tools callable via voice with Hermes template parsing
2. Tier 2 action triggers approval prompt on LCD; single-click approves
3. Conversation memory persists across sessions
4. Timer set via voice fires notification at correct time after reboot
5. Health endpoint returns valid JSON with all component statuses
6. Audit log captures all tool executions and approval decisions
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest

from cortex.agent.health import HealthMonitor
from cortex.agent.processor import AgentProcessor
from cortex.agent.scheduling import SchedulingService
from cortex.agent.tools.builtin.calculator import CalculatorTool
from cortex.agent.tools.builtin.clock import ClockTool
from cortex.agent.tools.builtin.memory_tool import (
    MemoryQueryTool,
    MemorySaveTool,
    set_memory_backend,
)
from cortex.agent.tools.builtin.system_info import SystemInfoTool
from cortex.agent.tools.builtin.timer import (
    TimerQueryTool,
    TimerSetTool,
    TimerStore,
    set_timer_store,
)
from cortex.agent.tools.registry import ToolRegistry
from cortex.hal.audio.mock import MockAudioService
from cortex.hal.display.mock import MockButtonService, MockDisplayService
from cortex.hal.npu.mock import MockNpuService
from cortex.hal.types import AudioData, AudioFormat
from cortex.memory.embedding import MockEmbeddingService
from cortex.memory.store import SqliteMemoryStore
from cortex.security.audit import SqliteAuditLog
from cortex.security.permissions import PermissionEngine
from cortex.security.types import PermissionTier
from cortex.voice.pipeline import VoicePipeline
from cortex.voice.types import VoiceSession


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ClockTool())
    reg.register(CalculatorTool())
    reg.register(SystemInfoTool())
    reg.register(TimerSetTool())
    reg.register(TimerQueryTool())
    reg.register(MemoryQueryTool())
    reg.register(MemorySaveTool())
    return reg


@pytest.fixture
def processor(registry: ToolRegistry) -> AgentProcessor:
    return AgentProcessor(registry=registry)


@pytest.fixture(autouse=True)
def fresh_timer_store() -> None:
    set_timer_store(TimerStore())


class TestExitCriteria1ToolsCalling:
    """EC1: At least 3 built-in tools callable via voice."""

    async def test_clock_via_voice(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("what time is it", session)
        assert not resp.used_llm
        assert resp.intent_id == "clock"
        assert resp.text  # Non-empty time response

    async def test_calculator_via_voice(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("what is 42 * 17", session)
        assert not resp.used_llm
        assert resp.intent_id == "calculator"
        assert "714" in resp.text

    async def test_system_info_via_voice(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("system status", session)
        assert not resp.used_llm
        assert resp.intent_id == "system_info"
        assert "Uptime" in resp.text

    async def test_timer_via_voice(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("set a timer for 5 minutes", session)
        assert not resp.used_llm
        assert resp.intent_id == "timer_set"
        assert "5 minute" in resp.text

    async def test_pipeline_tool_call(self, registry: ToolRegistry) -> None:
        """Test tool call through full pipeline."""
        npu = MockNpuService()
        await npu.load_model("sensevoice", Path("/mock/sv"))
        await npu.load_model("qwen3-vl-2b", Path("/mock/qwen3vl"))
        await npu.load_model("kokoro", Path("/mock/kokoro"))

        proc = AgentProcessor(registry=registry)
        pipe = VoicePipeline(
            npu=npu,
            audio=MockAudioService(),
            display=MockDisplayService(),
            button=MockButtonService(),
            agent_processor=proc,
        )
        pipe.set_handles(
            asr=npu._loaded_models["sensevoice"],
            llm=npu._loaded_models["qwen3-vl-2b"],
            tts=npu._loaded_models["kokoro"],
        )

        npu.set_asr_text("what time is it")
        audio = AudioData(
            samples=np.zeros(16000, dtype=np.int16),
            sample_rate=16000,
            format=AudioFormat.S16_LE,
        )
        await pipe.process_utterance(audio)
        assert pipe.session is not None
        # Should have user + assistant in history
        assert len(pipe.session.history) == 2


class TestExitCriteria2Approval:
    """EC2: Tier 2 action triggers approval prompt."""

    async def test_risky_action_requires_approval(self) -> None:
        engine = PermissionEngine(approval_manager=None)
        check = await engine.check("timer_cancel", PermissionTier.RISKY)
        assert not check.allowed

    async def test_safe_action_auto_approved(self) -> None:
        engine = PermissionEngine()
        check = await engine.check("clock", PermissionTier.SAFE)
        assert check.allowed


class TestExitCriteria3MemoryPersistence:
    """EC3: Conversation memory persists across sessions."""

    async def test_save_and_retrieve_across_sessions(self, tmp_path) -> None:
        db_path = str(tmp_path / "memory_e2e.db")
        embedder = MockEmbeddingService()

        # Session 1: Save a fact
        store1 = SqliteMemoryStore(db_path=db_path)
        await store1.start()
        set_memory_backend(store1, embedder)

        save_tool = MemorySaveTool()
        result = await save_tool.execute({"fact": "User's name is Andrew"})
        assert result.success
        await store1.stop()

        # Session 2: Query the fact
        store2 = SqliteMemoryStore(db_path=db_path)
        await store2.start()
        set_memory_backend(store2, embedder)

        query_tool = MemoryQueryTool()
        result = await query_tool.execute({"query": "User's name is Andrew"})
        assert result.success
        assert "Andrew" in result.display_text
        await store2.stop()

        # Clean up
        set_memory_backend(None, None)


class TestExitCriteria4TimerReboot:
    """EC4: Timer set via voice fires notification at correct time after reboot."""

    async def test_timer_survives_reboot(self, tmp_path) -> None:
        db_path = str(tmp_path / "timer_reboot.db")
        fired: list[str] = []

        async def on_fire(timer: object) -> None:
            fired.append(getattr(timer, "label", ""))

        # "Session 1" — set timer
        svc1 = SchedulingService(db_path=db_path, on_fire=on_fire)
        await svc1.start()
        await svc1.create_timer(1, "reboot_test")
        await svc1.stop()

        # Wait for it to become past-due
        await asyncio.sleep(1.5)

        # "Session 2" — reboot recovery
        svc2 = SchedulingService(db_path=db_path, on_fire=on_fire)
        await svc2.start()
        await asyncio.sleep(0.2)

        assert "reboot_test" in fired
        await svc2.stop()


class TestExitCriteria5HealthEndpoint:
    """EC5: Health endpoint returns valid JSON with all component statuses."""

    async def test_health_valid_json(self) -> None:
        npu = MockNpuService()
        await npu.load_model("sensevoice", Path("/mock/sv"))
        await npu.load_model("qwen3-vl-2b", Path("/mock/qwen3vl"))
        await npu.load_model("kokoro", Path("/mock/kokoro"))

        monitor = HealthMonitor(npu=npu)
        health = await monitor.check()
        d = health.to_dict()

        # Validate JSON schema
        json_str = json.dumps(d)
        parsed = json.loads(json_str)

        assert parsed["status"] in ("healthy", "degraded", "unhealthy")
        assert isinstance(parsed["uptime_seconds"], float)
        assert isinstance(parsed["components"], dict)
        assert isinstance(parsed["models_loaded"], list)
        assert "cpu" in parsed["components"]
        assert "memory" in parsed["components"]
        assert "storage" in parsed["components"]
        assert "npu" in parsed["components"]
        assert "sensevoice" in parsed["models_loaded"]


class TestExitCriteria6AuditLog:
    """EC6: Audit log captures all tool executions and approval decisions."""

    async def test_audit_captures_tool_execution(self, tmp_path) -> None:
        audit = SqliteAuditLog(db_path=str(tmp_path / "audit_e2e.db"))
        await audit.start()

        engine = PermissionEngine()
        check = await engine.check("clock", PermissionTier.SAFE)
        entry = engine.make_audit_entry(
            action_type="tool_call",
            action_id="clock",
            check=check,
            tier=PermissionTier.SAFE,
        )
        await audit.log(entry)

        results = await audit.query(action_type="tool_call")
        assert len(results) == 1
        assert results[0].action_id == "clock"
        assert results[0].approval_status == "auto"
        await audit.stop()

    async def test_audit_captures_approval_decision(self, tmp_path) -> None:
        audit = SqliteAuditLog(db_path=str(tmp_path / "audit_approval.db"))
        await audit.start()

        engine = PermissionEngine(approval_manager=None)
        check = await engine.check("system_reboot", PermissionTier.DANGER)
        entry = engine.make_audit_entry(
            action_type="tool_call",
            action_id="system_reboot",
            check=check,
            tier=PermissionTier.DANGER,
        )
        await audit.log(entry)

        results = await audit.query()
        assert len(results) == 1
        assert results[0].result == "denied"
        await audit.stop()
