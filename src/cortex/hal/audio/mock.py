"""Mock audio service for off-Pi development and testing.

Records all operations for verification in tests.
No actual hardware interaction.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import numpy as np

from cortex.hal.types import AudioData, AudioFormat


@dataclass
class MockAudioService:
    """Mock audio service that records operations for testing.

    Implements the AudioService Protocol.
    """

    _capturing: bool = False
    _playing: bool = False
    _capture_rate: int = 16000
    _mock_capture_audio: np.ndarray | None = None
    _played_audio: list[AudioData] = field(default_factory=list)
    _operations: list[str] = field(default_factory=list)

    def set_mock_capture(self, audio: np.ndarray, sample_rate: int = 16000) -> None:
        """Set audio data that will be returned by stop_capture()."""
        self._mock_capture_audio = audio
        self._capture_rate = sample_rate

    @property
    def is_capturing(self) -> bool:
        return self._capturing

    @property
    def is_playing(self) -> bool:
        return self._playing

    async def start_capture(self, sample_rate: int = 16000) -> None:
        if self._capturing:
            msg = "Already capturing"
            raise RuntimeError(msg)
        self._capture_rate = sample_rate
        self._capturing = True
        self._operations.append(f"start_capture({sample_rate})")

    async def stop_capture(self) -> AudioData:
        if not self._capturing:
            msg = "Not capturing"
            raise RuntimeError(msg)
        self._capturing = False
        self._operations.append("stop_capture")

        if self._mock_capture_audio is not None:
            samples = self._mock_capture_audio
            self._mock_capture_audio = None
        else:
            # Default: 1 second of silence
            samples = np.zeros(self._capture_rate, dtype=np.int16)

        return AudioData(
            samples=samples,
            sample_rate=self._capture_rate,
            channels=1,
            format=AudioFormat.S16_LE,
        )

    async def play(self, audio: AudioData) -> None:
        self._playing = True
        self._operations.append(f"play({len(audio.samples)} samples)")
        self._played_audio.append(audio)
        # Simulate playback time (~10ms per 1000 samples at mock speed)
        await asyncio.sleep(0.01)
        self._playing = False

    async def play_stream(self, chunks: AsyncIterator[AudioData]) -> None:
        self._playing = True
        self._operations.append("play_stream_start")
        async for chunk in chunks:
            self._played_audio.append(chunk)
            self._operations.append(f"play_stream_chunk({len(chunk.samples)})")
            await asyncio.sleep(0.01)
        self._operations.append("play_stream_end")
        self._playing = False

    async def stop_playback(self) -> None:
        self._playing = False
        self._operations.append("stop_playback")
