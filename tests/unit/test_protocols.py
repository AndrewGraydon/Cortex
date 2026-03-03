"""Tests for Phase 2 protocol interfaces — runtime checkability."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cortex.agent.protocols import AgentProcessor, Tool
from cortex.agent.types import AgentResponse, RoutingDecision, ToolResult
from cortex.memory.protocols import EmbeddingService, MemoryStore
from cortex.memory.types import ConversationSummary, MemoryCategory, MemoryEntry, SearchResult
from cortex.reasoning.protocols import ContextAssembler, ToolCallParser
from cortex.reasoning.types import AssembledPrompt, ToolSchema
from cortex.security.protocols import AuditLog, PermissionEngine
from cortex.security.types import ApprovalStatus, AuditEntry, PermissionCheck, PermissionTier
from cortex.voice.types import VoiceSession

# --- Concrete implementations for isinstance checks ---


class FakeTool:
    @property
    def name(self) -> str:
        return "fake"

    @property
    def description(self) -> str:
        return "A fake tool"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {"name": "fake"}

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name="fake", success=True)


class FakeAgentProcessor:
    async def process(self, text: str, session: VoiceSession, npu: Any = None) -> AgentResponse:
        return AgentResponse(text="response")

    async def process_stream(
        self, text: str, session: VoiceSession, npu: Any = None
    ) -> AsyncIterator[str]:
        yield "response"

    def route(self, text: str) -> RoutingDecision:
        from cortex.agent.types import IntentType

        return RoutingDecision(intent_type=IntentType.LLM)


class FakePermissionEngine:
    async def check(
        self, action_id: str, tier: PermissionTier, source: str = "voice"
    ) -> PermissionCheck:
        return PermissionCheck(allowed=True, status=ApprovalStatus.AUTO_APPROVED)


class FakeAuditLog:
    async def log(self, entry: AuditEntry) -> None:
        pass

    async def query(
        self,
        action_type: str | None = None,
        since: float | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        return []


class FakeMemoryStore:
    async def save_conversation(self, summary: ConversationSummary) -> None:
        pass

    async def get_recent_conversations(self, limit: int = 10) -> list[ConversationSummary]:
        return []

    async def save_fact(self, entry: MemoryEntry) -> None:
        pass

    async def search(
        self,
        embedding: NDArray[np.float32],
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[SearchResult]:
        return []

    async def get_all_facts(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
        return []


class FakeEmbeddingService:
    async def embed(self, text: str) -> NDArray[np.float32]:
        return np.zeros(384, dtype=np.float32)

    @property
    def dimensions(self) -> int:
        return 384


class FakeContextAssembler:
    def assemble(
        self,
        user_message: str,
        tools: list[ToolSchema] | None = None,
        memories: list[str] | None = None,
        summary: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AssembledPrompt:
        return AssembledPrompt(text=user_message)


class FakeToolCallParser:
    def parse(self, text: str) -> tuple[str, list]:
        return (text, [])


# --- Tests ---


class TestToolProtocol:
    def test_isinstance_check(self) -> None:
        tool = FakeTool()
        assert isinstance(tool, Tool)

    def test_non_tool_fails(self) -> None:
        assert not isinstance("not a tool", Tool)


class TestAgentProcessorProtocol:
    def test_isinstance_check(self) -> None:
        proc = FakeAgentProcessor()
        assert isinstance(proc, AgentProcessor)


class TestPermissionEngineProtocol:
    def test_isinstance_check(self) -> None:
        engine = FakePermissionEngine()
        assert isinstance(engine, PermissionEngine)


class TestAuditLogProtocol:
    def test_isinstance_check(self) -> None:
        log = FakeAuditLog()
        assert isinstance(log, AuditLog)


class TestMemoryStoreProtocol:
    def test_isinstance_check(self) -> None:
        store = FakeMemoryStore()
        assert isinstance(store, MemoryStore)


class TestEmbeddingServiceProtocol:
    def test_isinstance_check(self) -> None:
        svc = FakeEmbeddingService()
        assert isinstance(svc, EmbeddingService)


class TestContextAssemblerProtocol:
    def test_isinstance_check(self) -> None:
        asm = FakeContextAssembler()
        assert isinstance(asm, ContextAssembler)


class TestToolCallParserProtocol:
    def test_isinstance_check(self) -> None:
        parser = FakeToolCallParser()
        assert isinstance(parser, ToolCallParser)
