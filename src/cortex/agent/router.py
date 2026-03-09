"""Intent router — regex/keyword classifier for known intents.

Zero LLM cost for recognized patterns. Unmatched text falls through
to the LLM agent. This IS step 1 of the scope doc's orchestrator
(§4.4.2) — adding LLM-based classification later is additive.
"""

from __future__ import annotations

import logging
import re

from cortex.agent.types import IntentMatch, IntentType, RoutingDecision

logger = logging.getLogger(__name__)


class IntentPattern:
    """A regex pattern that matches a specific intent."""

    def __init__(
        self,
        intent_id: str,
        intent_type: IntentType,
        patterns: list[str],
        tool_hint: str | None = None,
        extract_groups: bool = False,
    ) -> None:
        self.intent_id = intent_id
        self.intent_type = intent_type
        self.tool_hint = tool_hint
        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self._extract_groups = extract_groups

    def match(self, text: str) -> IntentMatch | None:
        for pattern in self._patterns:
            m = pattern.search(text)
            if m:
                extracted = m.groupdict() if self._extract_groups else {}
                return IntentMatch(
                    intent_id=self.intent_id,
                    intent_type=self.intent_type,
                    tool_hint=self.tool_hint,
                    extracted=extracted,
                )
        return None


# Built-in intent patterns
BUILTIN_PATTERNS = [
    # Farewell
    IntentPattern(
        "farewell",
        IntentType.FAREWELL,
        [
            r"^(goodbye|bye|good night|see you|that'?s all|stop|quit|exit|"
            r"thanks?\s*bye|thank you\s*bye)\.?!?\s*$",
        ],
    ),
    # Clock / time
    IntentPattern(
        "clock",
        IntentType.UTILITY,
        [
            r"what\s*(time|'s the time)",
            r"what\s*is\s*the\s*(time|date)",
            r"tell\s*me\s*the\s*(time|date)",
            r"current\s*(time|date)",
            r"what\s*day\s*is\s*it",
        ],
        tool_hint="clock",
    ),
    # Timer set
    IntentPattern(
        "timer_set",
        IntentType.UTILITY,
        [
            r"set\s+(?:a\s+)?timer\s+(?:for\s+)?(?P<duration>\d+)\s*"
            r"(?P<unit>seconds?|minutes?|hours?|mins?|hrs?|secs?)",
            r"(?P<duration>\d+)\s*"
            r"(?P<unit>seconds?|minutes?|hours?|mins?|hrs?|secs?)\s+timer",
        ],
        tool_hint="timer_set",
        extract_groups=True,
    ),
    # Timer query
    IntentPattern(
        "timer_query",
        IntentType.UTILITY,
        [
            r"(how\s+much\s+time|what\s+time|how\s+long).*(timer|left|remaining)",
            r"(check|show|list)\s+(my\s+)?timers?",
            r"any\s+timers?\s+(running|active|set)",
        ],
        tool_hint="timer_query",
    ),
    # Calculator
    IntentPattern(
        "calculator",
        IntentType.UTILITY,
        [
            r"(?:what\s+is\s+|calculate\s+|compute\s+|what'?s\s+)"
            r"(?P<expression>\d[\d\s\+\-\*\/\.\(\)]+\d)",
        ],
        tool_hint="calculator",
        extract_groups=True,
    ),
    # System info
    IntentPattern(
        "system_info",
        IntentType.UTILITY,
        [
            r"(system|device)\s+(status|info|health|check)",
            r"how\s+are\s+you\s+(doing|running|performing)",
            r"(cpu|memory|npu)\s+(usage|status|temp)",
        ],
        tool_hint="system_info",
    ),
    # Memory save
    IntentPattern(
        "memory_save",
        IntentType.UTILITY,
        [
            r"remember\s+(?:that\s+)?(?P<fact>.+)",
            r"(?:my\s+name\s+is|i'?m\s+called)\s+(?P<fact>.+)",
        ],
        tool_hint="memory_save",
        extract_groups=True,
    ),
    # Calendar query
    IntentPattern(
        "calendar_query",
        IntentType.UTILITY,
        [
            r"what'?s\s+(?:on\s+)?my\s+calendar",
            r"(?:show|list|check|view)\s+(?:me\s+)?my\s+(?:upcoming\s+)?(?:events|appointments|meetings|calendar|schedule)",
            r"(?:do\s+)?i\s+have\s+(?:any\s+)?(?:events|appointments|meetings)\s+(?:today|tomorrow|this\s+week)",
            r"what\s+(?:do\s+)?i\s+have\s+(?:coming\s+)?up",
            r"(?:any|my)\s+(?:upcoming\s+)?(?:events|appointments|meetings)",
        ],
        tool_hint="calendar_query",
    ),
    # Calendar create
    IntentPattern(
        "calendar_create",
        IntentType.UTILITY,
        [
            r"(?:schedule|create|add|book|set\s+up)\s+(?:an?\s+)?(?:meeting|event|appointment)",
            r"(?:put|add)\s+(?:something\s+)?(?:on|to)\s+(?:my\s+)?calendar",
        ],
        tool_hint="calendar_create",
    ),
    # Email query
    IntentPattern(
        "email_query",
        IntentType.UTILITY,
        [
            r"(?:check|show|list|read)\s+(?:my\s+)?(?:email|inbox|mail)",
            r"(?:any|do\s+i\s+have)\s+(?:new\s+)?(?:emails?|messages?|mail)",
            r"(?:unread|new)\s+(?:emails?|messages?|mail)",
        ],
        tool_hint="email_query",
    ),
    # Email send
    IntentPattern(
        "email_send",
        IntentType.UTILITY,
        [
            r"(?:send|write|compose)\s+(?:an?\s+)?(?:email|message|mail)",
            r"(?:email|mail)\s+(?:to\s+)?\S+@\S+",
        ],
        tool_hint="email_send",
    ),
    # Notification send
    IntentPattern(
        "notification_send",
        IntentType.UTILITY,
        [
            r"(?:send|push)\s+(?:a\s+)?notification",
            r"notify\s+(?:me|my\s+phone)",
            r"(?:send|push)\s+(?:an?\s+)?(?:message|alert)\s+to\s+(?:my\s+)?(?:phone|device)",
        ],
        tool_hint="notification_send_external",
    ),
]


class IntentRouter:
    """Classifies user utterances into intents using regex patterns.

    Matched intents get a RoutingDecision with a specific handler.
    Unmatched text falls through to LLM with optional tool hints.
    """

    def __init__(
        self,
        patterns: list[IntentPattern] | None = None,
    ) -> None:
        self._patterns = patterns or list(BUILTIN_PATTERNS)

    def route(self, text: str) -> RoutingDecision:
        """Classify an utterance and return a routing decision."""
        normalized = text.strip()
        if not normalized:
            return RoutingDecision(intent_type=IntentType.LLM)

        for pattern in self._patterns:
            match = pattern.match(normalized)
            if match:
                logger.debug(
                    "Intent matched: %s → %s",
                    match.intent_id,
                    match.intent_type.value,
                )
                return RoutingDecision(
                    intent_type=match.intent_type,
                    intent_match=match,
                    tool_hints=[match.tool_hint] if match.tool_hint else [],
                )

        # No match — route to LLM
        return RoutingDecision(intent_type=IntentType.LLM)

    def add_pattern(self, pattern: IntentPattern) -> None:
        """Add a custom intent pattern."""
        self._patterns.insert(0, pattern)  # Custom patterns take priority
