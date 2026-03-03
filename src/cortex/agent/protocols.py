"""Agent framework protocol interfaces."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from cortex.agent.types import AgentResponse, RoutingDecision, ToolResult
from cortex.voice.types import VoiceSession


@runtime_checkable
class Tool(Protocol):
    """Interface for a cognitive tool or action handler."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def permission_tier(self) -> int: ...

    def get_schema(self) -> dict[str, Any]:
        """Return tool schema in canonical (OpenAI function calling) format."""
        ...

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool with validated arguments."""
        ...


@runtime_checkable
class AgentProcessor(Protocol):
    """Main interface between voice pipeline and agent framework.

    The pipeline calls process() with ASR text and session context.
    Returns either a complete response or streams text chunks.
    """

    async def process(
        self,
        text: str,
        session: VoiceSession,
        npu: Any = None,
    ) -> AgentResponse:
        """Process user text and return a response."""
        ...

    async def process_stream(
        self,
        text: str,
        session: VoiceSession,
        npu: Any = None,
    ) -> AsyncIterator[str]:
        """Process user text and stream response chunks for TTS."""
        ...

    def route(self, text: str) -> RoutingDecision:
        """Classify intent without executing (for testing/debugging)."""
        ...
