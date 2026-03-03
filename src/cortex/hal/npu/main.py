"""NPU service entry point — runs as cortex-npu.service.

Starts AxclNpuService (or MockNpuService), exposes it via ZeroMQ.
Handles model load/unload/infer requests from cortex-core.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import structlog

from cortex.ipc.bus import MessageBus
from cortex.ipc.messages import CortexMessage

logger = structlog.get_logger()

NPU_PUB_ADDRESS = "ipc:///tmp/cortex-npu-pub.sock"
NPU_SUB_ADDRESS = "ipc:///tmp/cortex-core-pub.sock"


async def run_npu_service(mock: bool = False) -> None:
    """Main NPU service loop."""
    bus = MessageBus()

    npu: Any
    if mock:
        from cortex.hal.npu.mock import MockNpuService

        npu = MockNpuService()
        logger.info("NPU service starting (mock mode)")
    else:
        from cortex.hal.npu.axcl import AxclNpuService

        npu = AxclNpuService()
        logger.info("NPU service starting (AXCL mode)")

    await bus.bind_publisher(NPU_PUB_ADDRESS)
    await bus.connect_subscriber(NPU_SUB_ADDRESS, topics=["npu."])

    # Publish ready status
    await bus.publish(CortexMessage(topic="npu.status", payload={"state": "ready"}))

    stop = asyncio.Event()

    def _signal_handler() -> None:
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info("NPU service running")

    try:
        while not stop.is_set():
            try:
                msg = await asyncio.wait_for(bus.receive(), timeout=1.0)
                logger.debug("NPU received: %s", msg.topic)
            except TimeoutError:
                continue
    finally:
        if hasattr(npu, "shutdown"):
            await npu.shutdown()
        await bus.close()
        logger.info("NPU service stopped")


def main() -> None:
    """CLI entry point for cortex-npu service."""
    import argparse

    parser = argparse.ArgumentParser(description="Cortex NPU Service")
    parser.add_argument("--mock", action="store_true", help="Use MockNpuService")
    args = parser.parse_args()

    from cortex.utils.logging import configure_logging

    configure_logging()

    asyncio.run(run_npu_service(mock=args.mock))


if __name__ == "__main__":
    main()
