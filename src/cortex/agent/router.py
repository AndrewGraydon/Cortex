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
    # Greeting — handled directly to avoid LLM generating a sticky greeting
    # pattern that causes Qwen3-VL-2B to repeat greetings in multi-turn.
    IntentPattern(
        "greeting",
        IntentType.GREETING,
        [
            r"^(hey|hi|hello|howdy|good\s+(morning|afternoon|evening)|"
            r"what'?s\s+up|yo|sup|greetings?)\.?!?\s*$",
        ],
    ),
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
    # Weather query
    IntentPattern(
        "weather_query",
        IntentType.UTILITY,
        [
            r"what'?s\s+the\s+weather",
            r"(?:how'?s|what'?s)\s+(?:the\s+)?weather\s+(?:like|looking|today|tomorrow)?",
            r"(?:what|how)\s+(?:is|will)\s+(?:the\s+)?(?:temperature|temp|forecast)",
            r"(?:will\s+it|is\s+it\s+going\s+to)\s+(?:rain|snow|be\s+(?:hot|cold|warm|sunny|cloudy))",
            r"(?:current|today'?s?|tomorrow'?s?)\s+(?:weather|temperature|forecast)",
            r"(?:weather|temperature|forecast)\s+(?:today|tomorrow|this\s+week)",
        ],
        tool_hint="weather_query",
    ),
    # Task query
    IntentPattern(
        "task_query",
        IntentType.UTILITY,
        [
            r"(?:show|list|check|view|what\s+are)\s+(?:my\s+)?(?:tasks?|to-?dos?|things\s+to\s+do)",
            r"(?:do\s+i\s+have\s+)?(?:any\s+)?(?:pending\s+)?(?:tasks?|to-?dos?)",
            r"what(?:'s|\s+is)\s+on\s+my\s+(?:task|to-?do)\s*(?:list)?",
        ],
        tool_hint="task_query",
    ),
    # Task create
    IntentPattern(
        "task_create",
        IntentType.UTILITY,
        [
            r"(?:add|create|make)\s+(?:a\s+)?(?:task|to-?do)",
            r"(?:remind\s+me\s+to|i\s+need\s+to)\s+(?P<summary>.+)",
        ],
        tool_hint="task_create",
        extract_groups=True,
    ),
    # Device control
    IntentPattern(
        "device_control",
        IntentType.UTILITY,
        [
            r"turn\s+(?:on|off)\s+(?:the\s+)?(?P<device>.+)",
            r"(?:switch|toggle)\s+(?:the\s+)?(?P<device>.+?)(?:\s+(?:on|off))?$",
            r"(?:dim|brighten)\s+(?:the\s+)?(?P<device>.+?)(?:\s+to\s+(?P<brightness>\d+))?",
            r"set\s+(?:the\s+)?(?P<device>.+?)\s+(?:to|at)\s+(?P<value>.+)",
        ],
        tool_hint="device_control",
        extract_groups=True,
    ),
    # Device query
    IntentPattern(
        "device_query",
        IntentType.UTILITY,
        [
            r"(?:what'?s|what\s+is)\s+(?:the\s+)?(?:state|status)\s+of\s+(?:the\s+)?(?P<device>.+)",
            r"is\s+(?:the\s+)?(?P<device>.+?)\s+(?:on|off|open|closed|locked|unlocked)",
            r"(?:check|get)\s+(?:the\s+)?(?P<device>.+?)\s+(?:state|status)",
        ],
        tool_hint="device_query",
        extract_groups=True,
    ),
    # Device list
    IntentPattern(
        "device_list",
        IntentType.UTILITY,
        [
            r"(?:list|show|what)\s+(?:all\s+)?(?:my\s+)?(?:smart\s+home\s+)?devices?",
            r"what\s+devices?\s+(?:do\s+i\s+have|are\s+(?:there|available))",
            r"(?:show|list)\s+(?:the\s+)?(?:devices?|lights?|switches?)\s+in\s+(?:the\s+)?(?P<room>.+)",
        ],
        tool_hint="device_list",
        extract_groups=True,
    ),
    # Automation query
    IntentPattern(
        "automation_query",
        IntentType.UTILITY,
        [
            r"(?:list|show|what)\s+(?:my\s+)?automations?",
            r"what\s+automations?\s+(?:do\s+i\s+have|are\s+(?:set\s+up|configured))",
        ],
        tool_hint="automation_query",
    ),
    # Automation create
    IntentPattern(
        "automation_create",
        IntentType.UTILITY,
        [
            r"(?:create|add|set\s+up)\s+(?:an?\s+)?automation",
            r"(?:every|when)\s+(?:night|morning|day)\s+(?:at\s+)?\d",
            r"when\s+(?P<device>.+?)\s+(?:turns?\s+(?:on|off)|changes?)\s+(?:then\s+)?(?P<action>.+)",
        ],
        tool_hint="automation_create",
        extract_groups=True,
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
