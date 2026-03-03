"""Display service entry point — runs as cortex-display.service.

Manages LCD display, button gestures, and LED control.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import structlog

from cortex.ipc.bus import MessageBus
from cortex.ipc.messages import CortexMessage

logger = structlog.get_logger()

DISPLAY_PUB_ADDRESS = "ipc:///tmp/cortex-display-pub.sock"
DISPLAY_SUB_ADDRESS = "ipc:///tmp/cortex-core-pub.sock"


async def run_display_service(mock: bool = False) -> None:
    """Main display service loop."""
    bus = MessageBus()

    display: Any
    button: Any
    if mock:
        from cortex.hal.display.mock import MockButtonService, MockDisplayService

        display = MockDisplayService()
        button = MockButtonService()
        logger.info("Display service starting (mock mode)")
    else:
        from cortex.hal.display.button import GpioButtonService
        from cortex.hal.display.led import GpioLedController
        from cortex.hal.display.service import WhisplayDisplayService

        led = GpioLedController()
        await led.start()
        display = WhisplayDisplayService()
        await display.start(led_controller=led)
        button = GpioButtonService()
        await button.start()
        logger.info("Display service starting (GPIO mode)")

    await bus.bind_publisher(DISPLAY_PUB_ADDRESS)
    await bus.connect_subscriber(DISPLAY_SUB_ADDRESS, topics=["display."])

    await bus.publish(CortexMessage(topic="display.status", payload={"state": "ready"}))

    stop = asyncio.Event()

    def _signal_handler() -> None:
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # Forward button gestures to bus
    async def forward_gestures() -> None:
        async for event in button.subscribe():
            await bus.publish(
                CortexMessage(
                    topic=f"button.{event.gesture.value}",
                    payload={
                        "gesture": event.gesture.value,
                        "duration_ms": event.duration_ms,
                        "timestamp": event.timestamp,
                    },
                )
            )

    gesture_task = asyncio.create_task(forward_gestures())

    logger.info("Display service running")

    try:
        while not stop.is_set():
            try:
                msg = await asyncio.wait_for(bus.receive(), timeout=1.0)
                logger.debug("Display received: %s", msg.topic)
            except TimeoutError:
                continue
    finally:
        gesture_task.cancel()
        if hasattr(button, "stop"):
            await button.stop()
        if hasattr(display, "stop"):
            await display.stop()
        await bus.close()
        logger.info("Display service stopped")


def main() -> None:
    """CLI entry point for cortex-display service."""
    import argparse

    parser = argparse.ArgumentParser(description="Cortex Display Service")
    parser.add_argument("--mock", action="store_true", help="Use mock services")
    args = parser.parse_args()

    from cortex.utils.logging import configure_logging

    configure_logging()

    asyncio.run(run_display_service(mock=args.mock))


if __name__ == "__main__":
    main()
