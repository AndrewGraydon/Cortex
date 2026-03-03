"""Hardware tests for Whisplay HAT peripherals.

These tests require a Raspberry Pi with Whisplay HAT.
Run with: make test-hw  (or pytest -m hardware)

Some tests are fully automated (LED init, audio device enumeration).
Others require user interaction (button press, audio verification).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.hardware


class TestLedHardware:
    """Test RGB LED controller on GPIO 22/18/16."""

    async def test_led_controller_starts(self) -> None:
        """LED controller initializes GPIO and PWM without error."""
        from cortex.hal.display.led import GpioLedController

        led = GpioLedController()
        await led.start()
        try:
            assert led._pwm_r is not None
            assert led._pwm_g is not None
            assert led._pwm_b is not None
        finally:
            await led.stop()

    async def test_led_set_color(self) -> None:
        """Setting LED colors doesn't error."""
        from cortex.hal.display.led import GpioLedController
        from cortex.hal.types import LedColor

        led = GpioLedController()
        await led.start()
        try:
            for color in [
                LedColor(255, 0, 0),
                LedColor(0, 255, 0),
                LedColor(0, 0, 255),
                LedColor.off(),
            ]:
                await led.set_color(color)
                assert led.current_color == color
                await asyncio.sleep(0.1)
        finally:
            await led.set_color(LedColor.off())
            await led.stop()

    async def test_led_state_colors(self) -> None:
        """Display state → LED color mapping works."""
        from cortex.hal.display.led import GpioLedController
        from cortex.hal.display.service import STATE_LED_MAP
        from cortex.hal.types import LedColor

        led = GpioLedController()
        await led.start()
        try:
            for _state, color in STATE_LED_MAP.items():
                await led.set_color(color)
                assert led.current_color == color
                await asyncio.sleep(0.05)
        finally:
            await led.set_color(LedColor.off())
            await led.stop()


class TestButtonHardware:
    """Test button service on GPIO 11."""

    async def test_button_service_starts(self) -> None:
        """Button service initializes GPIO edge detection."""
        from cortex.hal.display.button import GpioButtonService

        button = GpioButtonService(pin=11)
        await button.start()
        try:
            assert button._gpio is not None
        finally:
            await button.stop()

    async def test_button_detects_press(self) -> None:
        """Button detects at least one gesture within 10s.

        REQUIRES USER: Press the button when prompted.
        """
        from cortex.hal.display.button import GpioButtonService

        button = GpioButtonService(pin=11)
        await button.start()
        try:
            print("\n  >>> PRESS THE BUTTON NOW (10s timeout) <<<")
            event = await asyncio.wait_for(button.wait_gesture(), timeout=10.0)
            assert event is not None
            print(f"  Detected: {event.gesture.value} ({event.duration_ms:.0f}ms)")
        finally:
            await button.stop()


class TestAudioHardware:
    """Test audio capture and playback on WM8960."""

    async def test_audio_device_enumeration(self) -> None:
        """sounddevice can enumerate ALSA audio devices."""
        import sounddevice as sd

        devices = sd.query_devices()
        assert len(devices) > 0

        # Should have at least one input and one output device
        has_input = any(d["max_input_channels"] > 0 for d in devices)
        has_output = any(d["max_output_channels"] > 0 for d in devices)
        assert has_input, "No input audio devices found"
        assert has_output, "No output audio devices found"

    async def test_capture_records_audio(self) -> None:
        """Microphone capture produces non-empty audio data.

        REQUIRES: Ambient noise or tapping the mic.
        """
        from cortex.hal.audio.service import AlsaAudioService

        audio = AlsaAudioService()
        print("\n  >>> Make some noise near the microphone (2s recording) <<<")

        await audio.start_capture(sample_rate=16000)
        await asyncio.sleep(2.0)
        captured = await audio.stop_capture()

        assert captured.sample_rate == 16000
        assert len(captured.samples) > 0
        duration = len(captured.samples) / captured.sample_rate
        assert duration >= 1.5  # Should have ~2s of audio

        peak = int(np.max(np.abs(captured.samples)))
        print(f"  Captured {duration:.2f}s, peak amplitude: {peak}")
        # Even ambient noise should produce some signal
        assert peak > 10, f"No audio signal detected (peak={peak})"

    async def test_playback_tone(self) -> None:
        """Speaker can play a 440Hz test tone without error."""
        from cortex.hal.audio.service import AlsaAudioService
        from cortex.hal.types import AudioData, AudioFormat

        audio = AlsaAudioService()

        # Generate 1s of 440Hz tone at 24kHz
        sample_rate = 24000
        t = np.linspace(0, 1.0, sample_rate, dtype=np.float32)
        tone = (np.sin(2 * np.pi * 440 * t) * 0.5 * 32767).astype(np.int16)

        print("\n  >>> Listen for a 1-second 440Hz tone <<<")
        await audio.play(
            AudioData(samples=tone, sample_rate=sample_rate, format=AudioFormat.S16_LE)
        )
        # If we get here without error, playback succeeded
        assert not audio.is_playing

    async def test_capture_and_playback_loopback(self) -> None:
        """Record 2s then play it back (mic → speaker loopback).

        REQUIRES USER: Speak into mic, verify playback.
        """
        from cortex.hal.audio.service import AlsaAudioService
        from cortex.hal.types import AudioData, AudioFormat

        audio = AlsaAudioService()

        print("\n  >>> Speak into the microphone for 2 seconds <<<")
        await audio.start_capture(sample_rate=16000)
        await asyncio.sleep(2.0)
        captured = await audio.stop_capture()

        peak = int(np.max(np.abs(captured.samples)))
        print(f"  Captured {len(captured.samples)} samples, peak={peak}")

        print("  >>> Playing back your recording... <<<")
        await audio.play(
            AudioData(
                samples=captured.samples,
                sample_rate=captured.sample_rate,
                format=AudioFormat.S16_LE,
            )
        )
        assert True  # If no exception, loopback completed


class TestDisplayServiceHardware:
    """Test display service with real LED controller."""

    async def test_display_state_changes_led(self) -> None:
        """Display state transitions update LED colors."""
        from cortex.hal.display.led import GpioLedController
        from cortex.hal.display.service import WhisplayDisplayService
        from cortex.hal.types import DisplayState, LedColor

        led = GpioLedController()
        await led.start()

        display = WhisplayDisplayService()
        await display.start(led_controller=led)

        try:
            # Walk through pipeline states
            states_and_expected = [
                (DisplayState.IDLE, LedColor.idle()),
                (DisplayState.LISTENING, LedColor.listening()),
                (DisplayState.THINKING, LedColor.thinking()),
                (DisplayState.SPEAKING, LedColor.speaking()),
                (DisplayState.ERROR, LedColor.error()),
                (DisplayState.IDLE, LedColor.idle()),
            ]

            for state, expected_color in states_and_expected:
                await display.set_state(state, f"Testing {state.value}...")
                assert led.current_color == expected_color
                assert await display.get_state() == state
                await asyncio.sleep(0.5)

        finally:
            await led.set_color(LedColor.off())
            await display.stop()
            await led.stop()


class TestCombinedPipelineHardware:
    """Test 5: Combined button → LED → record → ASR pipeline.

    End-to-end test that exercises all Whisplay HAT peripherals together:
    LED signals the user, button controls recording, mic captures speech,
    and SenseVoice ASR transcribes it on the NPU.

    REQUIRES USER: Press and hold button, speak, then release.
    REQUIRES: SenseVoice model at ~/models/SenseVoice
    """

    async def test_button_record_asr_pipeline(self) -> None:
        """Hold button → record speech → ASR transcription → playback.

        Pipeline stages with LED color feedback:
          1. Dim blue (idle) — waiting for button hold
          2. Green (listening) — recording while button held
          3. Amber (thinking) — running ASR inference
          4. Blue (result) — showing transcription, playing back audio
        """
        from cortex.hal.audio.service import AlsaAudioService
        from cortex.hal.display.button import GpioButtonService
        from cortex.hal.display.led import GpioLedController
        from cortex.hal.npu.runners.asr import ASRRunner
        from cortex.hal.types import AudioData, AudioFormat, ButtonGesture, LedColor

        model_path = Path.home() / "models" / "SenseVoice"
        if not model_path.exists():
            pytest.skip(f"SenseVoice model not found at {model_path}")

        led = GpioLedController()
        button = GpioButtonService(pin=11)
        audio = AlsaAudioService()
        asr = ASRRunner()

        await led.start()
        await button.start()

        try:
            # Load ASR model
            await asr.load(model_path, {})

            # Stage 1: Idle — dim blue
            await led.set_color(LedColor.idle())
            print("\n  DIM BLUE = Idle. Press and HOLD the button, speak, then release.")
            print("  Waiting for button hold... (15s timeout)")

            # Wait for hold_start gesture
            event = await asyncio.wait_for(button.wait_gesture(), timeout=15.0)
            assert event.gesture == ButtonGesture.HOLD_START, (
                f"Expected hold_start, got {event.gesture.value}"
            )

            # Stage 2: Listening — green
            await led.set_color(LedColor.listening())
            print("  GREEN = RECORDING! Speak now, release when done.")
            await audio.start_capture(sample_rate=16000)

            # Wait for hold_end or long_press (release)
            release = await asyncio.wait_for(button.wait_gesture(), timeout=15.0)
            assert release.gesture in (ButtonGesture.HOLD_END, ButtonGesture.LONG_PRESS), (
                f"Expected hold_end/long_press, got {release.gesture.value}"
            )
            print(f"  Released ({release.gesture.value}, {release.duration_ms:.0f}ms)")

            captured = await audio.stop_capture()
            duration = len(captured.samples) / captured.sample_rate
            peak = int(np.max(np.abs(captured.samples))) if len(captured.samples) > 0 else 0
            print(f"  Captured: {duration:.2f}s, peak={peak}/32767 ({peak / 327.67:.1f}%)")

            assert len(captured.samples) > 0, "No audio captured"
            assert duration >= 0.5, f"Recording too short: {duration:.2f}s"
            assert peak > 100, f"No audio signal detected (peak={peak})"

            # Stage 3: Thinking — amber
            await led.set_color(LedColor.thinking())
            print("  AMBER = Transcribing...")

            from cortex.hal.types import InferenceInputs

            t0 = time.monotonic()
            result = await asr.infer(
                InferenceInputs(
                    data=captured.samples,
                    params={"language": "auto", "sample_rate": 16000},
                )
            )
            asr_time = time.monotonic() - t0

            text = str(result.data).strip()
            print(f"  === TRANSCRIPTION ({asr_time:.2f}s) ===")
            print(f'    "{text}"')
            print("  ===================================")

            assert len(text) > 0, "ASR returned empty transcription"

            # Stage 4: Result — blue, play back captured audio
            await led.set_color(LedColor.speaking())
            print("  BLUE = Result shown. Playing back audio...")

            await audio.play(
                AudioData(
                    samples=captured.samples,
                    sample_rate=captured.sample_rate,
                    format=AudioFormat.S16_LE,
                )
            )

            print("  SUCCESS: Combined pipeline test complete!")

        finally:
            await asr.unload()
            await led.set_color(LedColor.off())
            await button.stop()
            await led.stop()
