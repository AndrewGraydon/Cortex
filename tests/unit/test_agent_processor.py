"""Tests for agent processor — routing, tool execution, pipeline integration."""

from __future__ import annotations

import numpy as np
import pytest

from cortex.agent.processor import AgentProcessor
from cortex.agent.tools.builtin.calculator import CalculatorTool
from cortex.agent.tools.builtin.clock import ClockTool
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
    return reg


@pytest.fixture
def processor(registry: ToolRegistry) -> AgentProcessor:
    return AgentProcessor(registry=registry)


@pytest.fixture(autouse=True)
def fresh_timer_store() -> None:
    set_timer_store(TimerStore())


class TestUtilityRouting:
    async def test_clock_response(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("what time is it", session)
        assert not resp.used_llm
        assert resp.intent_id == "clock"
        assert resp.text  # Non-empty response
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "clock"

    async def test_calculator_response(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("what is 42 * 17", session)
        assert not resp.used_llm
        assert resp.intent_id == "calculator"
        assert "714" in resp.text

    async def test_timer_set_response(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("set a timer for 5 minutes", session)
        assert not resp.used_llm
        assert resp.intent_id == "timer_set"
        assert "5 minute" in resp.text

    async def test_system_info_response(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("system status", session)
        assert not resp.used_llm
        assert resp.intent_id == "system_info"
        assert "Uptime" in resp.text


class TestFarewellRouting:
    async def test_farewell_response(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("goodbye", session)
        assert resp.intent_id == "farewell"
        assert resp.text == "Goodbye!"


class TestLLMFallback:
    async def test_general_question_falls_to_llm(self, processor: AgentProcessor) -> None:
        session = VoiceSession()
        resp = await processor.process("tell me about black holes", session)
        assert resp.used_llm
        assert resp.text == ""  # Empty = pipeline handles LLM streaming
        assert resp.intent_id is None


class TestPipelineIntegration:
    """Test the agent processor wired into the voice pipeline."""

    @pytest.fixture
    async def agent_pipeline(self, registry: ToolRegistry) -> VoicePipeline:
        npu = MockNpuService()
        from pathlib import Path

        await npu.load_model("sensevoice", Path("/mock/sensevoice"))
        await npu.load_model("qwen3-vl-2b", Path("/mock/qwen3vl"))
        await npu.load_model("kokoro", Path("/mock/kokoro"))

        processor = AgentProcessor(registry=registry)

        pipe = VoicePipeline(
            npu=npu,
            audio=MockAudioService(),
            display=MockDisplayService(),
            button=MockButtonService(),
            agent_processor=processor,
        )
        pipe.set_handles(
            asr=npu._loaded_models["sensevoice"],
            llm=npu._loaded_models["qwen3-vl-2b"],
            tts=npu._loaded_models["kokoro"],
        )
        return pipe

    async def test_utility_intent_skips_llm(self, agent_pipeline: VoicePipeline) -> None:
        # Mock ASR to return "what time is it"
        agent_pipeline._npu.set_asr_text("what time is it")
        audio = AudioData(
            samples=np.zeros(16000, dtype=np.int16),
            sample_rate=16000,
            format=AudioFormat.S16_LE,
        )
        await agent_pipeline.process_utterance(audio)
        # Should have created a session and added to history
        assert agent_pipeline.session is not None
        assert len(agent_pipeline.session.history) == 2  # user + assistant

    async def test_farewell_with_agent(self, agent_pipeline: VoicePipeline) -> None:
        agent_pipeline._npu.set_asr_text("goodbye")
        audio = AudioData(
            samples=np.zeros(16000, dtype=np.int16),
            sample_rate=16000,
            format=AudioFormat.S16_LE,
        )
        await agent_pipeline.process_utterance(audio)
        # Session should be cleared
        assert agent_pipeline.session is None

    async def test_llm_fallback_still_works(self, agent_pipeline: VoicePipeline) -> None:
        agent_pipeline._npu.set_asr_text("tell me about black holes")
        audio = AudioData(
            samples=np.zeros(16000, dtype=np.int16),
            sample_rate=16000,
            format=AudioFormat.S16_LE,
        )
        await agent_pipeline.process_utterance(audio)
        # Should still create session and use LLM
        assert agent_pipeline.session is not None
        assert agent_pipeline.session.turn_count >= 1
