"""Tests for ZeroMQ message bus."""

from __future__ import annotations

import asyncio

import pytest

from cortex.ipc.bus import MessageBus
from cortex.ipc.messages import CortexMessage


@pytest.fixture
async def pub_sub_pair(tmp_path: object) -> tuple[MessageBus, MessageBus]:
    """Create a connected publisher/subscriber pair using inproc transport."""
    address = "inproc://test-bus"
    ctx_mod = __import__("zmq.asyncio", fromlist=["Context"])
    ctx = ctx_mod.Context()

    pub = MessageBus(ctx=ctx)
    sub = MessageBus(ctx=ctx)

    await pub.bind_publisher(address)
    await sub.connect_subscriber(address, topics=["test."])

    # Small delay for ZMQ subscription propagation
    await asyncio.sleep(0.05)

    yield pub, sub  # type: ignore[misc]

    await pub.close()
    await sub.close()
    ctx.term()


class TestMessageBus:
    async def test_publish_and_receive(self, pub_sub_pair: tuple[MessageBus, MessageBus]) -> None:
        pub, sub = pub_sub_pair
        msg = CortexMessage(topic="test.hello", payload={"data": "world"})
        await pub.publish(msg)

        received = await asyncio.wait_for(sub.receive(), timeout=1.0)
        assert received.topic == "test.hello"
        assert received.payload["data"] == "world"

    async def test_topic_filtering(self, pub_sub_pair: tuple[MessageBus, MessageBus]) -> None:
        """Subscriber only receives messages matching subscribed topic prefix."""
        pub, sub = pub_sub_pair

        # Send matching and non-matching messages
        await pub.publish(CortexMessage(topic="test.match", payload={"v": 1}))
        await pub.publish(CortexMessage(topic="other.nomatch", payload={"v": 2}))
        await pub.publish(CortexMessage(topic="test.also", payload={"v": 3}))

        # Should get test.match and test.also but not other.nomatch
        msg1 = await asyncio.wait_for(sub.receive(), timeout=1.0)
        msg2 = await asyncio.wait_for(sub.receive(), timeout=1.0)
        assert msg1.topic == "test.match"
        assert msg2.topic == "test.also"

    async def test_publish_without_bind_raises(self) -> None:
        bus = MessageBus()
        with pytest.raises(RuntimeError, match="Publisher not bound"):
            await bus.publish(CortexMessage(topic="x", payload={}))
        await bus.close()

    async def test_receive_without_connect_raises(self) -> None:
        bus = MessageBus()
        with pytest.raises(RuntimeError, match="Subscriber not connected"):
            await bus.receive()
        await bus.close()

    async def test_subscribe_iter(self, pub_sub_pair: tuple[MessageBus, MessageBus]) -> None:
        pub, sub = pub_sub_pair
        await pub.publish(CortexMessage(topic="test.iter", payload={"n": 1}))
        await pub.publish(CortexMessage(topic="test.iter", payload={"n": 2}))

        messages: list[CortexMessage] = []
        async for msg in sub.subscribe_iter():
            messages.append(msg)
            if len(messages) == 2:
                break

        assert len(messages) == 2
        assert messages[0].payload["n"] == 1
        assert messages[1].payload["n"] == 2
