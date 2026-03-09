"""Memory extraction — captures facts from conversation history.

Two extraction modes:
1. Regex-based immediate capture: "remember that...", "my name is..."
   → Instant save during conversation (no LLM needed).
2. Post-session LLM extraction: After session ends, LLM analyzes
   conversation to extract atomic facts. (Deferred to when LLM is available.)
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from cortex.memory.types import EpisodicEvent, EventType, MemoryCategory, MemoryEntry

logger = logging.getLogger(__name__)

# Regex patterns for immediate fact capture
IMMEDIATE_PATTERNS: list[tuple[re.Pattern[str], MemoryCategory, str]] = [
    # "Remember that X"
    (
        re.compile(r"remember\s+that\s+(.+)", re.IGNORECASE),
        MemoryCategory.FACT,
        "remember_that",
    ),
    # "Remember X" (shorter form)
    (
        re.compile(r"^remember\s+(.{10,})", re.IGNORECASE),
        MemoryCategory.FACT,
        "remember",
    ),
    # "My name is X"
    (
        re.compile(r"my\s+name\s+is\s+(\w[\w\s]{0,30})", re.IGNORECASE),
        MemoryCategory.PERSON,
        "name",
    ),
    # "I live in X" / "I'm from X"
    (
        re.compile(
            r"(?:i\s+live\s+in|i'm\s+from|i\s+am\s+from)\s+(\w[\w\s]{0,30})",
            re.IGNORECASE,
        ),
        MemoryCategory.PLACE,
        "location",
    ),
    # "I like X" / "I prefer X" / "My favorite X is Y"
    (
        re.compile(
            r"(?:i\s+(?:like|prefer|love|enjoy)\s+(.+)|my\s+fav(?:ou?rite)?\s+\w+\s+is\s+(.+))",
            re.IGNORECASE,
        ),
        MemoryCategory.PREFERENCE,
        "preference",
    ),
    # "I wake up at X" / "I usually X at Y"
    (
        re.compile(
            r"i\s+(?:wake\s+up|get\s+up|go\s+to\s+(?:bed|sleep))\s+(?:at\s+)?(.+)",
            re.IGNORECASE,
        ),
        MemoryCategory.ROUTINE,
        "routine",
    ),
]


class MemoryExtractor:
    """Extracts facts from conversation text using regex patterns.

    For immediate capture during conversation. Post-session LLM extraction
    is handled separately when an LLM is available.
    """

    def extract_immediate(self, text: str) -> list[MemoryEntry]:
        """Try to extract facts from user text using regex patterns.

        Returns a list of MemoryEntry objects (without embeddings —
        embeddings are added asynchronously by the memory pipeline).
        """
        results: list[MemoryEntry] = []
        for pattern, category, source_type in IMMEDIATE_PATTERNS:
            match = pattern.search(text)
            if match:
                # Get the captured fact (first non-None group)
                fact = next((g.strip() for g in match.groups() if g is not None), None)
                if fact and len(fact) >= 3:
                    entry = MemoryEntry(
                        id=uuid.uuid4().hex[:16],
                        content=self._normalize_fact(fact, category, text),
                        category=category,
                        source_conversation=None,  # Set by caller
                        confidence=0.9,  # Regex extraction = high confidence
                        created_at=time.time(),
                    )
                    results.append(entry)
                    logger.info(
                        "Immediate memory capture [%s]: %s",
                        source_type,
                        entry.content,
                    )
                    break  # One extraction per utterance
        return results

    def extract_from_conversation(
        self,
        history: list[dict[str, str]],
        session_id: str | None = None,
    ) -> list[MemoryEntry]:
        """Extract facts from a completed conversation history.

        Scans all user messages for regex-matchable facts.
        For LLM-based extraction, use a separate method with NPU access.
        """
        results: list[MemoryEntry] = []
        seen_contents: set[str] = set()

        for msg in history:
            if msg.get("role") != "user":
                continue
            text = msg.get("content", "")
            entries = self.extract_immediate(text)
            for entry in entries:
                if entry.content not in seen_contents:
                    entry.source_conversation = session_id
                    results.append(entry)
                    seen_contents.add(entry.content)
        return results

    @staticmethod
    def _normalize_fact(fact: str, category: MemoryCategory, original_text: str) -> str:
        """Normalize extracted fact into a clean, storable form."""
        fact = fact.strip().rstrip(".")

        if category == MemoryCategory.PERSON:
            # "my name is Andrew" → "User's name is Andrew"
            if not fact.lower().startswith("user"):
                return f"User's name is {fact}"
        elif category == MemoryCategory.PLACE:
            if not fact.lower().startswith("user"):
                return f"User lives in {fact}"
        elif category == MemoryCategory.ROUTINE:
            original_lower = original_text.lower()
            if "wake" in original_lower or "get up" in original_lower:
                return f"User wakes up at {fact}"
            if "bed" in original_lower or "sleep" in original_lower:
                return f"User goes to bed at {fact}"
            return f"User routine: {fact}"

        return fact


def extract_episodic_events(
    tool_calls: list[dict[str, str]] | None = None,
    user_messages: list[str] | None = None,
    session_id: str | None = None,
) -> list[EpisodicEvent]:
    """Extract episodic events from an interaction.

    Generates events for:
    - Tool uses (one event per tool call)
    - Query topics (simple keyword extraction from user messages)
    """
    events: list[EpisodicEvent] = []
    now = time.time()

    # Tool use events
    if tool_calls:
        for call in tool_calls:
            tool_name = call.get("name", "unknown")
            events.append(
                EpisodicEvent(
                    id=uuid.uuid4().hex[:16],
                    event_type=EventType.TOOL_USE,
                    content=tool_name,
                    timestamp=now,
                    session_id=session_id,
                    metadata={"arguments": call.get("arguments", "")},
                )
            )

    # Topic events from user messages
    if user_messages:
        topics = _extract_topics(user_messages)
        for topic in topics:
            events.append(
                EpisodicEvent(
                    id=uuid.uuid4().hex[:16],
                    event_type=EventType.QUERY_TOPIC,
                    content=topic,
                    timestamp=now,
                    session_id=session_id,
                )
            )

    return events


def _extract_topics(messages: list[str]) -> list[str]:
    """Simple keyword-based topic extraction from user messages."""
    topic_keywords = {
        "weather",
        "time",
        "timer",
        "alarm",
        "reminder",
        "calendar",
        "email",
        "news",
        "music",
        "light",
        "temperature",
        "schedule",
        "recipe",
        "math",
        "calculate",
        "search",
        "help",
    }
    topics: list[str] = []
    seen: set[str] = set()
    for msg in messages:
        words = {w.strip(".,!?;:'\"") for w in msg.lower().split()}
        for keyword in topic_keywords:
            if keyword in words and keyword not in seen:
                topics.append(keyword)
                seen.add(keyword)
    return topics
