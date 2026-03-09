"""Memory system data types — entries, categories, search results."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


class MemoryCategory(enum.Enum):
    """Categories for long-term memory entries."""

    FACT = "fact"  # "User's name is Andrew"
    PREFERENCE = "preference"  # "User prefers 22°C"
    PERSON = "person"  # "Sarah is user's sister"
    PLACE = "place"  # "User lives in Vancouver"
    ROUTINE = "routine"  # "User wakes up at 7am"


@dataclass
class MemoryEntry:
    """A single long-term memory entry with embedding."""

    id: str
    content: str
    category: MemoryCategory
    embedding: NDArray[np.float32] | None = None  # 384-dim vector
    source_conversation: str | None = None
    confidence: float = 1.0
    created_at: float = 0.0
    last_referenced: float = 0.0
    superseded_by: str | None = None


@dataclass
class ConversationSummary:
    """A short-term memory entry — summary of a completed conversation."""

    id: str
    started_at: float
    ended_at: float
    summary: str
    turn_count: int = 0
    topics: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Result from memory retrieval with similarity score."""

    entry: MemoryEntry
    similarity: float  # 0.0-1.0 cosine similarity


class EventType(enum.Enum):
    """Types of episodic events tracked for pattern detection."""

    TOOL_USE = "tool_use"
    QUERY_TOPIC = "query_topic"
    ROUTINE_ACTION = "routine_action"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


@dataclass
class EpisodicEvent:
    """A timestamped event for episodic memory."""

    id: str
    event_type: EventType
    content: str  # tool name, topic, or action description
    timestamp: float = 0.0
    session_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
