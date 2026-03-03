"""ALSA audio service — mic capture and speaker playback via sounddevice.

Hardware: WM8960 codec on PiSugar Whisplay HAT.
Capture: 16kHz mono S16_LE via ALSA 'default' device (plug→dsnoop, stereo→mono).
Playback: 24kHz S16_LE via ALSA 'default' device (dmix resamples 24kHz→48kHz).

Note: The WM8960 hardware requires 2-channel capture. The /etc/asound.conf on the
Pi configures 'default' capture through a plug→dsnoop chain that handles stereo
capture and channel conversion. Do NOT use 'hw:0,0' directly with channels=1.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
import sounddevice as sd

from cortex.hal.types import AudioData, AudioFormat

logger = logging.getLogger(__name__)

DEFAULT_CAPTURE_RATE = 16000
DEFAULT_PLAYBACK_RATE = 24000
DEFAULT_CAPTURE_DEVICE = "default"
DEFAULT_PLAYBACK_DEVICE = "default"
PLAYBACK_BLOCKSIZE = 1024  # ~43ms at 24kHz


class AlsaAudioService:
    """Audio capture and playback via sounddevice/ALSA.

    Implements the AudioService Protocol.
    Capture is blocking (runs in thread pool via sounddevice).
    Playback supports both one-shot and streaming.
    """

    def __init__(
        self,
        capture_device: str = DEFAULT_CAPTURE_DEVICE,
        playback_device: str = DEFAULT_PLAYBACK_DEVICE,
        capture_rate: int = DEFAULT_CAPTURE_RATE,
        playback_rate: int = DEFAULT_PLAYBACK_RATE,
    ) -> None:
        self._capture_device = capture_device
        self._playback_device = playback_device
        self._capture_rate = capture_rate
        self._playback_rate = playback_rate
        self._capturing = False
        self._playing = False
        self._capture_buffer: list[np.ndarray] = []
        self._capture_stream: sd.InputStream | None = None
        self._playback_stop_event: asyncio.Event = asyncio.Event()

    @property
    def is_capturing(self) -> bool:
        return self._capturing

    @property
    def is_playing(self) -> bool:
        return self._playing

    async def start_capture(self, sample_rate: int = DEFAULT_CAPTURE_RATE) -> None:
        """Start recording from microphone.

        Accumulates audio in a buffer until stop_capture() is called.
        """
        if self._capturing:
            msg = "Already capturing"
            raise RuntimeError(msg)

        self._capture_rate = sample_rate
        self._capture_buffer = []

        def callback(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
            if status:
                logger.warning("Capture status: %s", status)
            # Store a copy (sounddevice reuses the buffer)
            self._capture_buffer.append(indata[:, 0].copy())

        self._capture_stream = sd.InputStream(
            device=self._capture_device,
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=int(sample_rate * 0.05),  # 50ms blocks
            callback=callback,
        )
        self._capture_stream.start()
        self._capturing = True
        logger.info("Capture started at %dHz on %s", sample_rate, self._capture_device)

    async def stop_capture(self) -> AudioData:
        """Stop recording and return captured audio."""
        if not self._capturing or self._capture_stream is None:
            msg = "Not capturing"
            raise RuntimeError(msg)

        self._capture_stream.stop()
        self._capture_stream.close()
        self._capture_stream = None
        self._capturing = False

        if self._capture_buffer:
            samples = np.concatenate(self._capture_buffer)
        else:
            samples = np.zeros(0, dtype=np.int16)

        self._capture_buffer = []

        # Remove DC offset (WM8960 ADC has persistent ~300-600 bias)
        if len(samples) > 0:
            dc_offset = int(np.mean(samples))
            if abs(dc_offset) > 10:
                samples = np.clip(samples.astype(np.int32) - dc_offset, -32768, 32767).astype(
                    np.int16
                )
                logger.debug("DC offset removed: %d", dc_offset)

        duration = len(samples) / self._capture_rate
        peak = int(np.max(np.abs(samples))) if len(samples) > 0 else 0
        logger.info(
            "Capture stopped: %.2fs, %d samples, peak=%d",
            duration,
            len(samples),
            peak,
        )

        return AudioData(
            samples=samples,
            sample_rate=self._capture_rate,
            channels=1,
            format=AudioFormat.S16_LE,
        )

    async def play(self, audio: AudioData) -> None:
        """Play audio buffer to speaker (blocking until done)."""
        if self._playing:
            await self.stop_playback()

        self._playing = True
        self._playback_stop_event.clear()

        try:
            samples = self._prepare_playback(audio)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._play_sync, samples, audio.sample_rate)
        finally:
            self._playing = False

    async def play_stream(self, chunks: AsyncIterator[AudioData]) -> None:
        """Play streaming audio chunks with minimal gap.

        Each chunk is played sequentially. Playback can be
        interrupted by calling stop_playback().
        """
        self._playing = True
        self._playback_stop_event.clear()

        try:
            async for chunk in chunks:
                if self._playback_stop_event.is_set():
                    break
                samples = self._prepare_playback(chunk)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._play_sync, samples, chunk.sample_rate)
        finally:
            self._playing = False

    async def stop_playback(self) -> None:
        """Stop any active playback."""
        self._playback_stop_event.set()
        sd.stop()
        self._playing = False
        logger.info("Playback stopped")

    def _play_sync(self, samples: np.ndarray, sample_rate: int) -> None:
        """Synchronous playback (runs in thread pool)."""
        sd.play(
            samples,
            samplerate=sample_rate,
            device=self._playback_device,
            blocksize=PLAYBACK_BLOCKSIZE,
        )
        sd.wait()

    @staticmethod
    def _prepare_playback(audio: AudioData) -> np.ndarray:
        """Convert audio to playback format."""
        samples = audio.samples

        # Convert float32 to int16 if needed
        if samples.dtype == np.float32:
            samples = (samples * 32767).clip(-32768, 32767).astype(np.int16)

        return samples
