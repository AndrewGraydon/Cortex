"""A2A protocol types — Agent Card, skills, tasks, and JSON-RPC messages."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class TaskState(enum.Enum):
    """A2A task lifecycle states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


@dataclass
class A2aSkill:
    """A capability exposed by an A2A agent."""

    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "examples": self.examples,
        }


@dataclass
class AgentCard:
    """A2A Agent Card — describes an agent's capabilities and endpoints."""

    name: str
    description: str
    url: str
    version: str = "0.1.0"
    protocol_version: str = "0.2.0"
    skills: list[A2aSkill] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    authentication: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "protocolVersion": self.protocol_version,
            "capabilities": self.capabilities,
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
            "skills": [s.to_dict() for s in self.skills],
            "authentication": self.authentication,
        }


@dataclass
class A2aMessage:
    """A message within an A2A task."""

    role: str  # "user" or "agent"
    parts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "parts": self.parts}


@dataclass
class A2aTask:
    """An A2A task — a unit of work exchanged between agents."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: TaskState = TaskState.SUBMITTED
    messages: list[A2aMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": {"state": self.state.value},
            "history": [m.to_dict() for m in self.messages],
            "metadata": self.metadata,
        }


@dataclass
class JsonRpcRequest:
    """JSON-RPC 2.0 request."""

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: str | int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcRequest:
        return cls(
            method=data.get("method", ""),
            params=data.get("params", {}),
            id=data.get("id"),
        )


@dataclass
class JsonRpcResponse:
    """JSON-RPC 2.0 response."""

    id: str | int | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        resp: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            resp["error"] = self.error
        else:
            resp["result"] = self.result or {}
        return resp
