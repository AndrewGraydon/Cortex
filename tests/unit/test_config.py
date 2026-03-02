"""Tests for cortex.config module."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from cortex.config import CortexConfig, find_config_file, load_config


class TestCortexConfigDefaults:
    """Test that default config values match design expectations."""

    def test_default_config_creates_without_file(self) -> None:
        cfg = CortexConfig()
        assert cfg.system.hostname == "cortex"
        assert cfg.system.log_level == "INFO"

    def test_default_hal_npu(self) -> None:
        cfg = CortexConfig()
        assert cfg.hal.npu.device_id == 0
        assert cfg.hal.npu.thermal_throttle_temp == 75

    def test_default_audio(self) -> None:
        cfg = CortexConfig()
        assert cfg.hal.audio.sample_rate == 16000
        assert cfg.hal.audio.channels == 1
        assert cfg.hal.audio.card_name == "wm8960sound"

    def test_default_voice(self) -> None:
        cfg = CortexConfig()
        assert cfg.voice.activation_mode == "button"
        assert cfg.voice.session.idle_timeout == 300
        assert cfg.voice.asr.providers == ["axcl"]
        assert cfg.voice.tts.axcl.voice == "af_heart"
        assert cfg.voice.tts.axcl.sample_rate == 24000

    def test_default_button(self) -> None:
        cfg = CortexConfig()
        assert cfg.button.gpio_pin == 11
        assert cfg.button.gestures.hold["min_duration_ms"] == 300
        assert cfg.button.gestures.double_click["max_gap_ms"] == 400

    def test_default_reasoning(self) -> None:
        cfg = CortexConfig()
        assert cfg.reasoning.default_profile == "chat"
        assert cfg.reasoning.max_tokens == 512
        assert cfg.reasoning.temperature == 0.7


class TestConfigLoading:
    """Test YAML config loading."""

    def test_load_from_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "cortex.yaml"
        config_file.write_text(
            dedent("""\
                system:
                  hostname: test-pi
                  log_level: DEBUG
                hal:
                  audio:
                    volume: 50
                voice:
                  activation_mode: button
                  session:
                    idle_timeout: 600
            """)
        )
        cfg = load_config(config_file)
        assert cfg.system.hostname == "test-pi"
        assert cfg.system.log_level == "DEBUG"
        assert cfg.hal.audio.volume == 50
        assert cfg.voice.session.idle_timeout == 600
        # Unset values keep defaults
        assert cfg.hal.npu.device_id == 0
        assert cfg.button.gpio_pin == 11

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "cortex.yaml"
        config_file.write_text("")
        cfg = load_config(config_file)
        assert cfg.system.hostname == "cortex"

    def test_load_missing_file_returns_defaults(self) -> None:
        cfg = load_config(Path("/nonexistent/cortex.yaml"))
        assert cfg.system.hostname == "cortex"

    def test_load_no_path_returns_defaults_when_no_file(self) -> None:
        # When no config files exist in search paths, defaults are used
        cfg = load_config()
        assert isinstance(cfg, CortexConfig)

    def test_partial_override(self, tmp_path: Path) -> None:
        config_file = tmp_path / "cortex.yaml"
        config_file.write_text(
            dedent("""\
                hal:
                  npu:
                    thermal_throttle_temp: 70
            """)
        )
        cfg = load_config(config_file)
        assert cfg.hal.npu.thermal_throttle_temp == 70
        assert cfg.hal.npu.thermal_shutdown_temp == 85  # default preserved


class TestConfigSerialization:
    """Test config round-trip serialization."""

    def test_json_round_trip(self) -> None:
        cfg = CortexConfig()
        json_str = cfg.model_dump_json()
        restored = CortexConfig.model_validate_json(json_str)
        assert restored == cfg


class TestFindConfigFile:
    """Test config file discovery."""

    def test_explicit_path_found(self, tmp_path: Path) -> None:
        f = tmp_path / "test.yaml"
        f.write_text("system:\n  hostname: test\n")
        assert find_config_file(f) == f

    def test_explicit_path_not_found(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.yaml"
        assert find_config_file(f) is None
