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
    max_context_tokens: int = 2047
    temperature: float = 0.7
    system_prompt_version: str = "v1"
    profiles: dict[str, Any] = Field(default_factory=dict)


# --- Agent Config ---


class AgentConfig(BaseModel):
    enabled: bool = True
    max_tool_iterations: int = 2
    confidence_threshold: float = 0.6
    actions_dir: str = "config/actions"


# --- Security Config ---


class AuditConfig(BaseModel):
    enabled: bool = True
    db_path: str = "data/audit.db"
    retention_days: int = 90


class ApprovalConfig(BaseModel):
    timeout_seconds: float = 60.0
    default_deny_on_timeout: bool = True


class SecurityConfig(BaseModel):
    audit: AuditConfig = Field(default_factory=AuditConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)


# --- Memory Config ---


class ShortTermMemoryConfig(BaseModel):
    retention_days: int = 30
    max_conversations: int = 100


class LongTermMemoryConfig(BaseModel):
    max_entries: int = 10000
    similarity_threshold: float = 0.3
    dedup_threshold: float = 0.85
    auto_inject_count: int = 3
    embedding_dimensions: int = 384


class MemoryConfig(BaseModel):
    db_path: str = "data/memory.db"
    extraction_idle_timeout: int = 300
    regex_patterns: bool = True
    short_term: ShortTermMemoryConfig = Field(default_factory=ShortTermMemoryConfig)
    long_term: LongTermMemoryConfig = Field(default_factory=LongTermMemoryConfig)


# --- Scheduling Config ---


class SchedulingConfig(BaseModel):
    db_path: str = "data/schedules.db"
    max_active_timers: int = 20
    max_active_reminders: int = 100
    snooze_duration: int = 600
    max_snoozes: int = 3


# --- Notification Config ---


class DndConfig(BaseModel):
    enabled: bool = False
    start_hour: int = 22
    end_hour: int = 7


class NotificationConfig(BaseModel):
    dnd: DndConfig = Field(default_factory=DndConfig)
    timer_complete_priority: int = 2
    reminder_due_priority: int = 3
    system_health_priority: int = 2


# --- Health Config ---


class HealthConfig(BaseModel):
    enabled: bool = True
    endpoint: str = "/api/health"
    npu_poll_interval: int = 5
    cpu_poll_interval: int = 10
    memory_poll_interval: int = 30


# --- Web Config ---


class WebConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    session_timeout_local: int = 3600
    session_timeout_remote: int = 1800
    password_hash: str = ""


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
    agent: AgentConfig = Field(default_factory=AgentConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    web: WebConfig = Field(default_factory=WebConfig)


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
