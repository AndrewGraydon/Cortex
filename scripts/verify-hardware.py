#!/usr/bin/env python3
"""Interactive hardware verification for Cortex on Raspberry Pi.

Run this script on the Pi to verify each peripheral works correctly:
  1. LED test — cycles through colors (visual check)
  2. Button test — detects gestures (physical interaction)
  3. Audio capture — records from microphone (speak into mic)
  4. Audio playback — plays a tone (listen for it)
  5. Combined test — button hold → record → playback

Usage:
    python scripts/verify-hardware.py           # Run all tests
    python scripts/verify-hardware.py led        # LED test only
    python scripts/verify-hardware.py button     # Button test only
    python scripts/verify-hardware.py audio      # Audio capture + playback
    python scripts/verify-hardware.py combined   # Full button → mic → speaker loop

Requires: RPi.GPIO, sounddevice, numpy (run from Cortex venv on Pi)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import numpy as np


def print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def print_pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def print_fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def print_info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def print_wait(msg: str) -> None:
    print(f"  [WAIT] {msg}")


# ---------------------------------------------------------------------------
# Test 1: LED verification
# ---------------------------------------------------------------------------
async def test_led() -> bool:
    print_header("Test 1: RGB LED Verification")
    print_info("This test cycles through LED colors. Watch the LED on the Whisplay HAT.")
    print_info("LED pins: Red=22, Green=18, Blue=16 (BOARD, active-low PWM)")
    print()

    try:
        from cortex.hal.display.led import GpioLedController
        from cortex.hal.types import LedColor
    except ImportError as e:
        print_fail(f"Import failed: {e}")
        return False

    led = GpioLedController()

    try:
        await led.start()
        print_pass("LED controller started")

        colors = [
            ("Red", LedColor(255, 0, 0)),
            ("Green", LedColor(0, 255, 0)),
            ("Blue", LedColor(0, 0, 255)),
            ("Amber (Thinking)", LedColor.thinking()),
            ("Dim Blue (Idle)", LedColor.idle()),
            ("Bright Blue (Speaking)", LedColor.speaking()),
            ("Bright Green (Listening)", LedColor.listening()),
            ("Red (Error)", LedColor.error()),
            ("White", LedColor(255, 255, 255)),
            ("Off", LedColor.off()),
        ]

        for name, color in colors:
            await led.set_color(color)
            print_info(f"{name}: R={color.r} G={color.g} B={color.b}")
            await asyncio.sleep(1.5)

        print()
        result = input("  Did you see all LED colors change correctly? (y/n): ").strip().lower()
        return result == "y"

    except Exception as e:
        print_fail(f"LED error: {e}")
        return False
    finally:
        await led.set_color(LedColor.off())
        await led.stop()


# ---------------------------------------------------------------------------
# Test 2: Button gesture detection
# ---------------------------------------------------------------------------
async def test_button() -> bool:
    print_header("Test 2: Button Gesture Detection")
    print_info("This test detects button gestures on GPIO 11 (BOARD, active-HIGH).")
    print_info("You will be asked to perform each gesture type.")
    print()

    try:
        from cortex.hal.display.button import GpioButtonService
        from cortex.hal.types import ButtonGesture
    except ImportError as e:
        print_fail(f"Import failed: {e}")
        return False

    button = GpioButtonService(pin=11)

    try:
        await button.start()
        print_pass("Button service started on pin 11")
    except Exception as e:
        print_fail(f"Button init failed: {e}")
        return False

    gestures_detected: dict[str, bool] = {}

    tests = [
        ("HOLD", "Press and HOLD the button for about 1 second, then release.", {ButtonGesture.HOLD_START, ButtonGesture.HOLD_END}),
        ("SINGLE CLICK", "Give the button a quick single tap.", {ButtonGesture.SINGLE_CLICK}),
        ("DOUBLE CLICK", "Double-tap the button quickly.", {ButtonGesture.DOUBLE_CLICK}),
        ("LONG PRESS", "Press and hold the button for 3+ seconds, then release.", {ButtonGesture.LONG_PRESS}),
    ]

    try:
        for test_name, instruction, expected_gestures in tests:
            print()
            print_wait(f"--- {test_name} ---")
            print_wait(instruction)
            print_wait("Waiting up to 10 seconds...")

            detected = set()
            deadline = time.monotonic() + 10.0

            while time.monotonic() < deadline:
                try:
                    event = await asyncio.wait_for(button.wait_gesture(), timeout=0.5)
                    detected.add(event.gesture)
                    print_info(
                        f"Detected: {event.gesture.value} "
                        f"(duration={event.duration_ms:.0f}ms)"
                    )
                    # Check if we got what we need
                    if expected_gestures.issubset(detected):
                        break
                except asyncio.TimeoutError:
                    continue

            if expected_gestures.issubset(detected):
                print_pass(f"{test_name} detected correctly!")
                gestures_detected[test_name] = True
            else:
                missing = expected_gestures - detected
                missing_names = ", ".join(g.value for g in missing)
                print_fail(f"{test_name}: missing gestures: {missing_names}")
                gestures_detected[test_name] = False

        print()
        passed = sum(gestures_detected.values())
        total = len(gestures_detected)
        print_info(f"Button results: {passed}/{total} gesture types detected")
        return passed == total

    except Exception as e:
        print_fail(f"Button error: {e}")
        return False
    finally:
        await button.stop()


# ---------------------------------------------------------------------------
# Test 3: Audio capture and playback
# ---------------------------------------------------------------------------
async def test_audio() -> bool:
    print_header("Test 3: Audio Capture & Playback")
    print_info("Capture device: default (ALSA plug→dsnoop, 16kHz mono)")
    print_info("Playback device: default (ALSA dmix, 24kHz)")
    print()

    try:
        from cortex.hal.audio.service import AlsaAudioService
    except ImportError as e:
        print_fail(f"Import failed: {e}")
        return False

    # First check available devices
    try:
        import sounddevice as sd

        print_info("Available audio devices:")
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            direction = ""
            if dev["max_input_channels"] > 0:
                direction += "IN"
            if dev["max_output_channels"] > 0:
                direction += ("+" if direction else "") + "OUT"
            print(f"    [{i}] {dev['name']} ({direction})")
        print()
    except Exception as e:
        print_fail(f"Device enumeration failed: {e}")

    audio = AlsaAudioService()
    capture_ok = False
    playback_ok = False

    # --- Capture test ---
    print_wait("Recording 3 seconds of audio. Speak into the microphone...")
    try:
        await audio.start_capture(sample_rate=16000)
        await asyncio.sleep(3.0)
        captured = await audio.stop_capture()

        duration = len(captured.samples) / captured.sample_rate
        peak = int(np.max(np.abs(captured.samples)))
        rms = int(np.sqrt(np.mean(captured.samples.astype(np.float64) ** 2)))

        print_info(f"Captured: {duration:.2f}s, {len(captured.samples)} samples")
        print_info(f"Peak amplitude: {peak} (of 32767)")
        print_info(f"RMS level: {rms}")

        if peak > 500:
            print_pass(f"Audio captured with signal (peak={peak})")
            capture_ok = True
        elif peak > 100:
            print_info("Low signal detected — may be very quiet or ambient noise only")
            capture_ok = True
        else:
            print_fail(f"No meaningful audio signal (peak={peak}). Is the mic working?")

    except Exception as e:
        print_fail(f"Capture error: {e}")

    # --- Playback test: 440Hz tone ---
    print()
    print_wait("Playing a 440Hz test tone for 2 seconds. Listen for it...")
    try:
        sample_rate = 24000
        duration_s = 2.0
        t = np.linspace(0, duration_s, int(sample_rate * duration_s), dtype=np.float32)
        tone = (np.sin(2 * np.pi * 440 * t) * 0.5 * 32767).astype(np.int16)

        from cortex.hal.types import AudioData, AudioFormat

        tone_audio = AudioData(
            samples=tone,
            sample_rate=sample_rate,
            format=AudioFormat.S16_LE,
        )
        await audio.play(tone_audio)
        print_info("Tone playback completed")

        result = input("  Did you hear the 440Hz tone? (y/n): ").strip().lower()
        playback_ok = result == "y"
        if playback_ok:
            print_pass("Audio playback confirmed")
        else:
            print_fail("Audio playback not heard")

    except Exception as e:
        print_fail(f"Playback error: {e}")

    # --- Loopback test: play back the captured audio ---
    if capture_ok and captured and len(captured.samples) > 0:
        print()
        print_wait("Playing back your captured audio. Listen for your voice...")
        try:
            # Resample 16kHz capture to 24kHz for playback
            from cortex.hal.types import AudioData, AudioFormat

            await audio.play(AudioData(
                samples=captured.samples,
                sample_rate=captured.sample_rate,
                format=AudioFormat.S16_LE,
            ))
            result = input("  Did you hear your recorded voice? (y/n): ").strip().lower()
            if result == "y":
                print_pass("Mic → Speaker loopback confirmed!")
            else:
                print_info("Loopback not confirmed (could be low volume or mic issue)")
        except Exception as e:
            print_fail(f"Loopback error: {e}")

    print()
    if capture_ok and playback_ok:
        print_pass("Audio tests passed")
    elif capture_ok:
        print_info("Capture OK, but playback needs verification")
    elif playback_ok:
        print_info("Playback OK, but capture needs verification")
    else:
        print_fail("Audio tests have issues")

    return capture_ok and playback_ok


# ---------------------------------------------------------------------------
# Test 4: Combined button → LED → record → playback
# ---------------------------------------------------------------------------
async def test_combined() -> bool:
    print_header("Test 4: Combined (Button → LED → Record → Playback)")
    print_info("This simulates the real voice interaction:")
    print_info("  1. Press and hold button → LED turns green (listening)")
    print_info("  2. Speak while holding → audio captured")
    print_info("  3. Release button → LED turns amber (processing)")
    print_info("  4. After 1s → LED turns blue (speaking) → playback your audio")
    print_info("  5. After playback → LED turns dim blue (idle)")
    print()

    try:
        from cortex.hal.audio.service import AlsaAudioService
        from cortex.hal.display.button import GpioButtonService
        from cortex.hal.display.led import GpioLedController
        from cortex.hal.types import AudioData, AudioFormat, ButtonGesture, LedColor
    except ImportError as e:
        print_fail(f"Import failed: {e}")
        return False

    led = GpioLedController()
    button = GpioButtonService(pin=11)
    audio = AlsaAudioService()

    try:
        await led.start()
        await button.start()

        # Set idle color
        await led.set_color(LedColor.idle())
        print_pass("All services started. LED is dim blue (idle).")
        print()
        print_wait("Press and HOLD the button, speak, then release. (10s timeout)")

        # Wait for hold start
        deadline = time.monotonic() + 15.0
        hold_started = False

        while time.monotonic() < deadline:
            try:
                event = await asyncio.wait_for(button.wait_gesture(), timeout=0.5)

                if event.gesture == ButtonGesture.HOLD_START:
                    hold_started = True
                    await led.set_color(LedColor.listening())
                    print_info("Hold detected → LED green (listening)")
                    print_info("Speak now! Release when done.")
                    await audio.start_capture(sample_rate=16000)
                    break
            except asyncio.TimeoutError:
                continue

        if not hold_started:
            print_fail("No hold detected within timeout")
            return False

        # Wait for hold end
        hold_ended = False
        while time.monotonic() < deadline:
            try:
                event = await asyncio.wait_for(button.wait_gesture(), timeout=0.5)
                if event.gesture in (ButtonGesture.HOLD_END, ButtonGesture.LONG_PRESS):
                    hold_ended = True
                    print_info(f"Release detected ({event.gesture.value}, {event.duration_ms:.0f}ms)")
                    break
            except asyncio.TimeoutError:
                continue

        if not hold_ended:
            print_fail("No release detected within timeout")
            if audio.is_capturing:
                await audio.stop_capture()
            return False

        # Stop capture
        captured = await audio.stop_capture()
        duration = len(captured.samples) / captured.sample_rate
        peak = int(np.max(np.abs(captured.samples)))

        await led.set_color(LedColor.thinking())
        print_info(f"Captured {duration:.2f}s of audio (peak={peak})")
        print_info("LED amber (thinking)...")
        await asyncio.sleep(1.0)

        # Play back
        await led.set_color(LedColor.speaking())
        print_info("LED blue (speaking) → playing back your audio...")

        await audio.play(AudioData(
            samples=captured.samples,
            sample_rate=captured.sample_rate,
            format=AudioFormat.S16_LE,
        ))

        # Return to idle
        await led.set_color(LedColor.idle())
        print_info("LED dim blue (idle)")

        print()
        result = input("  Did the full loop work (LED colors + audio)? (y/n): ").strip().lower()
        if result == "y":
            print_pass("Combined test passed!")
            return True
        else:
            print_fail("Combined test issues reported by user")
            return False

    except Exception as e:
        print_fail(f"Combined test error: {e}")
        return False
    finally:
        await led.set_color(LedColor.off())
        await led.stop()
        await button.stop()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(tests: list[str]) -> int:
    print_header("Cortex Hardware Verification")
    print_info("This script verifies each peripheral on the Whisplay HAT.")
    print_info("Run on the Raspberry Pi with Cortex venv activated.")
    print_info("LCD rendering is not yet implemented — LED colors verify display states.")

    results: dict[str, bool] = {}

    test_map = {
        "led": ("LED", test_led),
        "button": ("Button", test_button),
        "audio": ("Audio", test_audio),
        "combined": ("Combined", test_combined),
    }

    if not tests:
        tests = ["led", "button", "audio", "combined"]

    for test_name in tests:
        if test_name in test_map:
            label, func = test_map[test_name]
            try:
                results[label] = await func()
            except KeyboardInterrupt:
                print_info(f"\n  {label} test skipped (Ctrl+C)")
                results[label] = False
            except Exception as e:
                print_fail(f"{label} test crashed: {e}")
                results[label] = False
        else:
            print_fail(f"Unknown test: {test_name}")
            print_info(f"Available: {', '.join(test_map.keys())}")

    # Summary
    print_header("Verification Summary")
    all_pass = True
    for label, passed in results.items():
        status = "PASS" if passed else "FAIL"
        marker = "[PASS]" if passed else "[FAIL]"
        print(f"  {marker} {label}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("  All hardware tests PASSED!")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"  Some tests FAILED: {', '.join(failed)}")
        print("  Review the output above for details.")

    return 0 if all_pass else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Interactive hardware verification for Cortex"
    )
    parser.add_argument(
        "tests",
        nargs="*",
        choices=["led", "button", "audio", "combined"],
        default=[],
        help="Specific tests to run (default: all)",
    )
    args = parser.parse_args()

    try:
        sys.exit(asyncio.run(main(args.tests)))
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
