"""Cortex configuration — loads cortex.yaml via Pydantic models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# --- HAL Config ---


class NpuConfig(BaseModel):
    device_id: int = 0
    axcl_json: str = "/etc/axcl.json"
    thermal_throttle_temp: int = 75
    thermal_shutdown_temp: int = 85


class AudioConfig(BaseModel):
    card_name: str = "wm8960sound"
    sample_rate: int = 16000
    channels: int = 1
    format: str = "S16_LE"
    volume: int = 80


class DisplayConfig(BaseModel):
    brightness: int = 80
    idle_timeout: int = 30
    orientation: int = 0


class HalConfig(BaseModel):
    npu: NpuConfig = Field(default_factory=NpuConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)


# --- Voice Config ---


class SessionConfig(BaseModel):
    idle_timeout: int = 300
    farewell_patterns: list[str] = Field(
        default_factory=lambda: ["goodbye", "that's all", "thanks i'm done", "see you later"]
    )


class StreamingConfig(BaseModel):
    min_chunk_tokens: int = 8
    crossfade_ms: int = 10
    max_queue_depth: int = 5


class AsrProviderConfig(BaseModel):
    model: str = "sensevoice"
    language: str = "en"


class AsrConfig(BaseModel):
    providers: list[str] = Field(default_factory=lambda: ["axcl"])
    axcl: AsrProviderConfig = Field(default_factory=AsrProviderConfig)


class TtsAxclConfig(BaseModel):
    model: str = "kokoro"
    voice: str = "af_heart"
    speed: float = 1.0
    sample_rate: int = 24000
    max_chunk_tokens: int = 96


class TtsConfig(BaseModel):
    providers: list[str] = Field(default_factory=lambda: ["axcl"])
    axcl: TtsAxclConfig = Field(default_factory=TtsAxclConfig)


class LatencyBudgetConfig(BaseModel):
    asr_max_ms: int = 500
    tts_first_audio_ms: int = 200


class VoiceConfig(BaseModel):
    activation_mode: str = "button"
    max_recording_duration: int = 30
    session: SessionConfig = Field(default_factory=SessionConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    latency_budget: LatencyBudgetConfig = Field(default_factory=LatencyBudgetConfig)


# --- Button Config ---


class GestureConfig(BaseModel):
    hold: dict[str, Any] = Field(
        default_factory=lambda: {"min_duration_ms": 300, "action": "push_to_talk"}
    )
    double_click: dict[str, Any] = Field(
        default_factory=lambda: {"max_gap_ms": 400, "action": "camera_capture"}
    )
    single_click: dict[str, Any] = Field(
        default_factory=lambda: {"delay_ms": 400, "action": "confirm"}
    )
    long_press: dict[str, Any] = Field(
        default_factory=lambda: {"min_duration_ms": 2000, "action": "cancel"}
    )
    triple_click: dict[str, Any] = Field(
        default_factory=lambda: {"max_gap_ms": 600, "action": "system_menu"}
    )


class ButtonConfig(BaseModel):
    gpio_pin: int = 11
    debounce_ms: int = 50
    gestures: GestureConfig = Field(default_factory=GestureConfig)


# --- Reasoning Config ---


class ReasoningConfig(BaseModel):
    default_profile: str = "chat"
    max_tokens: int = 512
    temperature: float = 0.7
    system_prompt_version: str = "v1"
    profiles: dict[str, Any] = Field(default_factory=dict)


# --- System Config ---


class SystemConfig(BaseModel):
    hostname: str = "cortex"
    log_level: str = "INFO"
    data_dir: str = "/opt/cortex/data"
    timezone: str = "UTC"


# --- Top-level Config ---


class CortexConfig(BaseModel):
    """Top-level configuration loaded from cortex.yaml."""

    system: SystemConfig = Field(default_factory=SystemConfig)
    hal: HalConfig = Field(default_factory=HalConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    button: ButtonConfig = Field(default_factory=ButtonConfig)
    reasoning: ReasoningConfig = Field(default_factory=ReasoningConfig)


# --- Config search paths (in priority order) ---

CONFIG_SEARCH_PATHS = [
    Path("cortex.yaml"),
    Path("config/cortex.yaml"),
    Path("/etc/cortex/cortex.yaml"),
]


def find_config_file(explicit_path: Path | None = None) -> Path | None:
    """Find the configuration file. Returns None if no config file exists."""
    if explicit_path is not None:
        if explicit_path.is_file():
            return explicit_path
        return None
    for path in CONFIG_SEARCH_PATHS:
        if path.is_file():
            return path
    return None


def load_config(path: Path | None = None) -> CortexConfig:
    """Load configuration from a YAML file.

    If no path is given, searches CONFIG_SEARCH_PATHS.
    If no file is found, returns default configuration.
    """
    config_path = find_config_file(path)
    if config_path is None:
        return CortexConfig()

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return CortexConfig()

    return CortexConfig.model_validate(raw)
