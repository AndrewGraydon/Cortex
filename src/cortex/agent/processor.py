"""Agent processor — main orchestration between voice pipeline and agent framework.

Routes ASR text → if regex match: utility handler → response (no LLM).
If LLM needed: context assembler builds prompt → LLM stream → tool call
parser → if tool: execute via action engine → response.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from cortex.agent.action_engine import ActionEngine
from cortex.agent.router import IntentRouter
from cortex.agent.tools.registry import ToolRegistry
from cortex.agent.types import (
    AgentResponse,
    IntentType,
    RoutingDecision,
    ToolCall,
)
from cortex.reasoning.context_assembler import ContextAssembler
from cortex.reasoning.tool_parser import HermesToolCallParser
from cortex.voice.types import VoiceSession

logger = logging.getLogger(__name__)

# Duration unit → seconds multiplier
DURATION_UNITS = {
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "secs": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "mins": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "hrs": 3600,
}


class AgentProcessor:
    """Main agent processor — routes, executes tools, and manages LLM interaction.

    The voice pipeline calls process() with ASR text and session context.
    Returns an AgentResponse with text to speak, tool calls made, etc.
    """

    def __init__(
        self,
        router: IntentRouter | None = None,
        registry: ToolRegistry | None = None,
        action_engine: ActionEngine | None = None,
        context_assembler: ContextAssembler | None = None,
        tool_parser: HermesToolCallParser | None = None,
        max_tool_iterations: int = 2,
    ) -> None:
        self._router = router or IntentRouter()
        self._registry = registry or ToolRegistry()
        self._action_engine = action_engine
        self._assembler = context_assembler or ContextAssembler()
        self._tool_parser = tool_parser or HermesToolCallParser()
        self._max_iterations = max_tool_iterations

    def route(self, text: str) -> RoutingDecision:
        """Classify intent without executing (for testing/debugging)."""
        return self._router.route(text)

    async def process(
        self,
        text: str,
        session: VoiceSession,
        npu: Any = None,
    ) -> AgentResponse:
        """Process user text and return a response.

        Routes through intent router first. If matched:
          - FAREWELL → signals pipeline to end session
          - UTILITY → executes tool directly, no LLM
        If unmatched:
          - LLM → returns None (pipeline handles LLM streaming itself)
        """
        decision = self._router.route(text)

        if decision.intent_type == IntentType.FAREWELL:
            return AgentResponse(
                text="Goodbye!",
                intent_id="farewell",
            )

        if decision.intent_type == IntentType.GREETING:
            return AgentResponse(
                text="Hey! What can I help you with?",
                intent_id="greeting",
            )

        if decision.intent_type == IntentType.UTILITY:
            return await self._handle_utility(decision, text)

        # LLM fallback — build messages context for callers that need it
        messages = self._assembler.build_messages(
            user_message=text,
            history=session.history if session else None,
        )
        return AgentResponse(
            text="",
            used_llm=True,
            intent_id=None,
            llm_messages=messages,
        )

    async def _handle_utility(
        self,
        decision: RoutingDecision,
        text: str,
    ) -> AgentResponse:
        """Handle a utility intent with direct tool execution."""
        match = decision.intent_match
        if match is None:
            return AgentResponse(text="I'm not sure how to help with that.")

        tool_name = match.tool_hint
        if tool_name is None:
            return AgentResponse(text="I'm not sure how to help with that.")

        # Build tool arguments from extracted regex groups
        arguments = self._build_arguments(tool_name, match.extracted, text)

        # Execute via action engine or directly
        call = ToolCall(name=tool_name, arguments=arguments)

        if self._action_engine:
            result = await self._action_engine.execute(call)
        else:
            result = await self._registry.execute(call)

        return AgentResponse(
            text=result.display_text or ("Done." if result.success else result.error or "Error."),
            tool_calls=[call],
            tool_results=[result],
            used_llm=False,
            intent_id=match.intent_id,
        )

    def _build_arguments(
        self,
        tool_name: str,
        extracted: dict[str, str],
        text: str,
    ) -> dict[str, Any]:
        """Build tool arguments from regex captures."""
        if tool_name == "timer_set":
            return self._build_timer_args(extracted)
        if tool_name == "calculator":
            return self._build_calculator_args(extracted, text)
        if tool_name == "memory_save":
            return self._build_memory_args(extracted, text)
        if tool_name == "clock":
            return self._build_clock_args(text)
        return {}

    @staticmethod
    def _build_timer_args(extracted: dict[str, str]) -> dict[str, Any]:
        duration_str = extracted.get("duration", "")
        unit = extracted.get("unit", "seconds").lower()
        try:
            duration = int(duration_str)
        except (ValueError, TypeError):
            return {"duration": 60}  # Default 1 minute
        multiplier = DURATION_UNITS.get(unit, 1)
        return {"duration": duration * multiplier}

    @staticmethod
    def _build_calculator_args(
        extracted: dict[str, str],
        text: str,
    ) -> dict[str, Any]:
        expr = extracted.get("expression", "")
        if not expr:
            # Try to extract from full text
            m = re.search(r"(\d[\d\s\+\-\*\/\.\(\)]+\d)", text)
            if m:
                expr = m.group(1)
        return {"expression": expr.strip()} if expr else {}

    @staticmethod
    def _build_memory_args(
        extracted: dict[str, str],
        text: str,
    ) -> dict[str, Any]:
        fact = extracted.get("fact", "")
        if not fact:
            # Use full text minus "remember that" prefix
            fact = re.sub(
                r"^(remember\s+that\s+|remember\s+)",
                "",
                text,
                flags=re.IGNORECASE,
            ).strip()
        return {"fact": fact} if fact else {}

    @staticmethod
    def _build_clock_args(text: str) -> dict[str, Any]:
        lower = text.lower()
        if "date" in lower and "time" not in lower:
            return {"format": "date"}
        if "time" in lower and "date" not in lower:
            return {"format": "time"}
        return {"format": "both"}
