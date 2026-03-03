"""Audio service entry point — runs as cortex-audio.service.

Manages mic capture and speaker playback.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import structlog

from cortex.ipc.bus import MessageBus
from cortex.ipc.messages import CortexMessage

logger = structlog.get_logger()

AUDIO_PUB_ADDRESS = "ipc:///tmp/cortex-audio-pub.sock"
AUDIO_SUB_ADDRESS = "ipc:///tmp/cortex-core-pub.sock"


async def run_audio_service(mock: bool = False) -> None:
    """Main audio service loop."""
    bus = MessageBus()

    audio: Any
    if mock:
        from cortex.hal.audio.mock import MockAudioService

        audio = MockAudioService()
        logger.info("Audio service starting (mock mode)")
    else:
        from cortex.hal.audio.service import AlsaAudioService

        audio = AlsaAudioService()
        logger.info("Audio service starting (ALSA mode)")

    await bus.bind_publisher(AUDIO_PUB_ADDRESS)
    await bus.connect_subscriber(AUDIO_SUB_ADDRESS, topics=["audio."])

    await bus.publish(CortexMessage(topic="audio.status", payload={"state": "ready"}))

    stop = asyncio.Event()

    def _signal_handler() -> None:
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info("Audio service running")

    try:
        while not stop.is_set():
            try:
                msg = await asyncio.wait_for(bus.receive(), timeout=1.0)
                logger.debug("Audio received: %s", msg.topic)
            except TimeoutError:
                continue
    finally:
        _ = audio  # Will be wired into message handler in voice pipeline
        await bus.close()
        logger.info("Audio service stopped")


def main() -> None:
    """CLI entry point for cortex-audio service."""
    import argparse

    parser = argparse.ArgumentParser(description="Cortex Audio Service")
    parser.add_argument("--mock", action="store_true", help="Use MockAudioService")
    args = parser.parse_args()

    from cortex.utils.logging import configure_logging

    configure_logging()

    asyncio.run(run_audio_service(mock=args.mock))


if __name__ == "__main__":
    main()
