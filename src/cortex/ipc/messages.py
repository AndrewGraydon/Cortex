"""IPC message types — JSON-serializable messages for ZeroMQ transport.

Topic convention: {service}.{event_type}
Examples: button.gesture, npu.model_loaded, voice.state_changed
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CortexMessage:
    """Standard message envelope for ZeroMQ IPC.

    All inter-service communication uses this format.
    Audio data is sent as separate multipart frames, not inside JSON.
    """

    topic: str  # {service}.{event_type}
    payload: dict[str, Any] = field(default_factory=dict)
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, data: str | bytes) -> CortexMessage:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        raw = json.loads(data)
        return cls(**raw)

    def to_zmq_frames(self) -> list[bytes]:
        """Encode as ZeroMQ multipart: [topic, json_body]."""
        return [self.topic.encode("utf-8"), self.to_json().encode("utf-8")]

    @classmethod
    def from_zmq_frames(cls, frames: list[bytes]) -> CortexMessage:
        """Decode from ZeroMQ multipart: [topic, json_body]."""
        if len(frames) < 2:
            msg = f"Expected at least 2 frames, got {len(frames)}"
            raise ValueError(msg)
        return cls.from_json(frames[1])
