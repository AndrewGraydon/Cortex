"""Tests for Wyoming audio format conversion utilities."""

from __future__ import annotations

import numpy as np

from cortex.wyoming.types import (
    CORTEX_ASR_FORMAT,
    CORTEX_TTS_FORMAT,
    WYOMING_STT_FORMAT,
    WYOMING_TTS_FORMAT,
    AudioFormat,
    BridgeState,
    NpuAvailability,
    float32_to_pcm_int16,
    pcm_int16_to_float32,
    resample_linear,
)


class TestAudioFormatConstants:
    """Verify standard audio format constants."""

    def test_wyoming_stt_format(self) -> None:
        assert WYOMING_STT_FORMAT.rate == 16000
        assert WYOMING_STT_FORMAT.width == 2
        assert WYOMING_STT_FORMAT.channels == 1

    def test_wyoming_tts_format(self) -> None:
        assert WYOMING_TTS_FORMAT.rate == 22050
        assert WYOMING_TTS_FORMAT.width == 2
        assert WYOMING_TTS_FORMAT.channels == 1

    def test_cortex_asr_format(self) -> None:
        assert CORTEX_ASR_FORMAT.rate == 16000
        assert CORTEX_ASR_FORMAT.width == 2
        assert CORTEX_ASR_FORMAT.channels == 1

    def test_cortex_tts_format(self) -> None:
        assert CORTEX_TTS_FORMAT.rate == 24000
        assert CORTEX_TTS_FORMAT.width == 2
        assert CORTEX_TTS_FORMAT.channels == 1

    def test_audio_format_defaults(self) -> None:
        fmt = AudioFormat()
        assert fmt.rate == 16000
        assert fmt.width == 2
        assert fmt.channels == 1


class TestPcmInt16ToFloat32:
    """PCM int16 bytes → float32 numpy conversion."""

    def test_silence(self) -> None:
        """Zero samples convert to 0.0."""
        pcm = np.zeros(100, dtype=np.int16).tobytes()
        result = pcm_int16_to_float32(pcm)
        assert result.dtype == np.float32
        assert len(result) == 100
        assert np.allclose(result, 0.0)

    def test_max_positive(self) -> None:
        """INT16_MAX → ~1.0."""
        pcm = np.array([32767], dtype=np.int16).tobytes()
        result = pcm_int16_to_float32(pcm)
        assert abs(result[0] - 1.0) < 0.001

    def test_max_negative(self) -> None:
        """INT16_MIN → -1.0."""
        pcm = np.array([-32768], dtype=np.int16).tobytes()
        result = pcm_int16_to_float32(pcm)
        assert abs(result[0] - (-1.0)) < 0.001

    def test_empty_input(self) -> None:
        result = pcm_int16_to_float32(b"")
        assert len(result) == 0

    def test_roundtrip_shape(self) -> None:
        """PCM bytes → float32 preserves sample count."""
        n_samples = 1600  # 100ms at 16kHz
        pcm = np.random.randint(-32768, 32767, size=n_samples, dtype=np.int16).tobytes()
        result = pcm_int16_to_float32(pcm)
        assert len(result) == n_samples


class TestFloat32ToPcmInt16:
    """Float32 numpy → PCM int16 bytes conversion."""

    def test_silence(self) -> None:
        audio = np.zeros(100, dtype=np.float32)
        pcm = float32_to_pcm_int16(audio)
        assert len(pcm) == 200  # 100 samples × 2 bytes

    def test_clipping(self) -> None:
        """Values outside [-1, 1] are clipped."""
        audio = np.array([2.0, -2.0, 0.5], dtype=np.float32)
        pcm = float32_to_pcm_int16(audio)
        samples = np.frombuffer(pcm, dtype=np.int16)
        assert samples[0] == 32767  # clipped max
        assert samples[1] == -32767  # clipped min (np.clip to -1.0 × 32767)
        assert abs(samples[2] - 16383) < 2

    def test_roundtrip(self) -> None:
        """float32 → int16 → float32 is approximately identity."""
        original = np.array([0.0, 0.5, -0.5, 0.99, -0.99], dtype=np.float32)
        pcm = float32_to_pcm_int16(original)
        recovered = pcm_int16_to_float32(pcm)
        np.testing.assert_allclose(recovered, original, atol=1e-4)


class TestResampleLinear:
    """Linear interpolation resampling."""

    def test_same_rate(self) -> None:
        """Same src/dst rate returns identical array."""
        audio = np.random.randn(1000).astype(np.float32)
        result = resample_linear(audio, 24000, 24000)
        np.testing.assert_array_equal(result, audio)

    def test_downsample_24k_to_22050(self) -> None:
        """24kHz → 22050Hz reduces sample count."""
        n_src = 24000  # 1 second at 24kHz
        audio = np.sin(np.linspace(0, 2 * np.pi * 440, n_src)).astype(np.float32)
        result = resample_linear(audio, 24000, 22050)
        assert result.dtype == np.float32
        assert abs(len(result) - 22050) <= 1

    def test_upsample(self) -> None:
        """Upsampling increases sample count."""
        audio = np.ones(100, dtype=np.float32)
        result = resample_linear(audio, 16000, 24000)
        assert len(result) == 150  # 100 × (24000/16000)

    def test_empty_audio(self) -> None:
        result = resample_linear(np.array([], dtype=np.float32), 16000, 22050)
        assert len(result) == 0

    def test_single_sample(self) -> None:
        audio = np.array([0.5], dtype=np.float32)
        result = resample_linear(audio, 16000, 22050)
        assert len(result) >= 1
        assert abs(result[0] - 0.5) < 0.01


class TestEnums:
    """Bridge and NPU availability enums."""

    def test_bridge_states(self) -> None:
        assert BridgeState.STOPPED.value == "stopped"
        assert BridgeState.STARTING.value == "starting"
        assert BridgeState.RUNNING.value == "running"
        assert BridgeState.STOPPING.value == "stopping"

    def test_npu_availability(self) -> None:
        assert NpuAvailability.AVAILABLE.value == "available"
        assert NpuAvailability.BUSY.value == "busy"
        assert NpuAvailability.UNAVAILABLE.value == "unavailable"
