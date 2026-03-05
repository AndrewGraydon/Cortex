"""Tests for IPC message types and serialization."""

from __future__ import annotations

from cortex.ipc.messages import CortexMessage


class TestCortexMessage:
    def test_create_message(self) -> None:
        msg = CortexMessage(topic="button.gesture", payload={"gesture": "hold_start"})
        assert msg.topic == "button.gesture"
        assert msg.payload["gesture"] == "hold_start"
        assert len(msg.msg_id) == 12
        assert msg.timestamp > 0

    def test_json_round_trip(self) -> None:
        msg = CortexMessage(
            topic="npu.model_loaded",
            payload={"model_id": "qwen3-vl-2b", "memory_mb": 1771},
        )
        json_str = msg.to_json()
        restored = CortexMessage.from_json(json_str)
        assert restored.topic == msg.topic
        assert restored.payload == msg.payload
        assert restored.msg_id == msg.msg_id

    def test_json_from_bytes(self) -> None:
        msg = CortexMessage(topic="voice.state_changed", payload={"state": "listening"})
        json_bytes = msg.to_json().encode("utf-8")
        restored = CortexMessage.from_json(json_bytes)
        assert restored.topic == "voice.state_changed"

    def test_zmq_frames_round_trip(self) -> None:
        msg = CortexMessage(
            topic="audio.level",
            payload={"rms": 0.42},
        )
        frames = msg.to_zmq_frames()
        assert len(frames) == 2
        assert frames[0] == b"audio.level"

        restored = CortexMessage.from_zmq_frames(frames)
        assert restored.topic == msg.topic
        assert restored.payload["rms"] == 0.42

    def test_zmq_frames_topic_prefix_filtering(self) -> None:
        """ZeroMQ topic filtering works on byte prefixes."""
        msg = CortexMessage(topic="button.gesture", payload={})
        frames = msg.to_zmq_frames()
        topic_bytes = frames[0]
        assert topic_bytes.startswith(b"button.")

    def test_zmq_frames_too_few_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="at least 2 frames"):
            CortexMessage.from_zmq_frames([b"topic_only"])

    def test_empty_payload(self) -> None:
        msg = CortexMessage(topic="health.heartbeat")
        json_str = msg.to_json()
        restored = CortexMessage.from_json(json_str)
        assert restored.payload == {}
