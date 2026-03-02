"""ZeroMQ message bus — pub/sub and req/rep patterns for HAL IPC."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import zmq
import zmq.asyncio

from cortex.ipc.messages import CortexMessage

# Default IPC socket paths
PUB_SOCKET = "ipc:///tmp/cortex-pub.sock"
SUB_SOCKET = "ipc:///tmp/cortex-pub.sock"  # subscribers connect to publisher


class MessageBus:
    """Async ZeroMQ message bus for inter-service communication.

    Publisher side: publish messages to a PUB socket.
    Subscriber side: subscribe to topics on a SUB socket.
    """

    def __init__(self, ctx: zmq.asyncio.Context | None = None) -> None:
        self._ctx = ctx or zmq.asyncio.Context.instance()
        self._pub_socket: zmq.asyncio.Socket | None = None
        self._sub_socket: zmq.asyncio.Socket | None = None
        self._subscriptions: dict[str, list[Callable[[CortexMessage], Any]]] = {}

    async def bind_publisher(self, address: str = PUB_SOCKET) -> None:
        """Bind a PUB socket (one per service process)."""
        self._pub_socket = self._ctx.socket(zmq.PUB)
        self._pub_socket.bind(address)
        # Small delay for ZeroMQ socket binding
        await asyncio.sleep(0.01)

    async def connect_subscriber(
        self, address: str = SUB_SOCKET, topics: list[str] | None = None
    ) -> None:
        """Connect a SUB socket and subscribe to topics."""
        self._sub_socket = self._ctx.socket(zmq.SUB)
        self._sub_socket.connect(address)
        if topics:
            for topic in topics:
                self._sub_socket.subscribe(topic.encode("utf-8"))
        else:
            self._sub_socket.subscribe(b"")  # all messages
        await asyncio.sleep(0.01)

    async def publish(self, message: CortexMessage) -> None:
        """Publish a message on the PUB socket."""
        if self._pub_socket is None:
            msg = "Publisher not bound. Call bind_publisher() first."
            raise RuntimeError(msg)
        await self._pub_socket.send_multipart(message.to_zmq_frames())

    async def receive(self) -> CortexMessage:
        """Receive the next message from the SUB socket (blocking)."""
        if self._sub_socket is None:
            msg = "Subscriber not connected. Call connect_subscriber() first."
            raise RuntimeError(msg)
        frames = await self._sub_socket.recv_multipart()
        return CortexMessage.from_zmq_frames(frames)

    async def subscribe_iter(self) -> AsyncIterator[CortexMessage]:
        """Async iterator over incoming messages."""
        while True:
            yield await self.receive()

    async def close(self) -> None:
        """Close all sockets."""
        if self._pub_socket is not None:
            self._pub_socket.close()
            self._pub_socket = None
        if self._sub_socket is not None:
            self._sub_socket.close()
            self._sub_socket = None
