# Project Cortex — Agentic Local LLM Voice Assistant
## System Design Scope Document v0.1.12

---

## 1. Vision Statement

A fully local, privacy-first, voice-and-web AI assistant running on a Raspberry Pi 5 with NPU acceleration. The system operates autonomously for safe tasks, requests approval for risky operations, can dynamically create its own tools and agents, integrates with smart home/IoT devices, and maintains comprehensive audit trails — all while keeping data local by default with optional secure external access.

### User Personas

Four personas anchor the interaction design. Each maps to a permission level and has different expectations.

| Persona | Description | Access Level | Primary Interface | Key Expectations |
|---|---|---|---|---|
| **Primary User** | Developer/owner who built and maintains the system | Full (all tiers, admin) | Voice + Web UI | Deep customization, tool creation, agent tuning, full memory access |
| **Household Member** | Non-technical family member using the assistant daily | Standard (Tier 0-1 auto, Tier 2 with approval) | Voice (primary), Web UI (occasional) | "Just works" — ask questions, set timers, control lights, no config required |
| **Guest** | Visitor with temporary, limited access | Restricted (Tier 0 only, no memory, no IoT) | Voice only | Basic questions, time/weather, no personal data exposure, no device control |
| **Remote User** | Primary user accessing from outside the home network | Full (via authenticated Web UI) | Web UI only | Same capabilities as at home, but through web interface with auth |

**Primary User (Andrew):** The person who built and maintains the system. Creates and edits agents, tools, and automations. Reviews audit logs, manages memory, configures providers, approves Tier 3 operations. Uses both voice and web UI depending on context. The system recognizes this user by default (single-user voice; multi-user voice ID is a Phase 6+ stretch goal).

**Household Member:** Uses the assistant like a smart speaker — "set a timer for 10 minutes", "what's the weather", "turn off the kitchen lights". Never touches config. Expects natural conversation, clear confirmations, and graceful handling of unsupported requests. Should never encounter raw error messages or technical jargon. The system should feel helpful and approachable. Access controlled by the primary user's permission configuration.

**Guest:** Temporary access, no persistence. Cannot trigger any Tier 1+ actions without primary user approval. Cannot access memory (personal facts about the household). Cannot control IoT devices. Can ask general knowledge questions, get the time, and have basic conversation. Guest mode activated explicitly by the primary user (voice command or web UI toggle). When active, long-term memory injection is disabled and the system prompt includes privacy constraints.

**Remote User:** The primary user accessing from outside the local network via the authenticated web UI (§4.6.2). Same capabilities as local primary user, but voice input goes through browser microphone and TTS plays through browser audio. Latency is higher (network round-trip) but functionality is identical. Requires authentication (§4.5). Cannot use physical button gestures but all software equivalents are available.

---

## 2. Hardware Platform

| Component | Role | Key Specs |
|---|---|---|
| **Raspberry Pi 5 (8GB)** | Host orchestrator, web server, agent runtime | BCM2712, 8GB LPDDR4X, Debian 12 / Ubuntu 24.04 |
| **M5Stack LLM-8850 (AX8850)** | NPU inference engine | 24 TOPS INT8, 8-core A55 1.7GHz, 8GB LPDDR4x, PCIe 2.0 x1 |
| **PiSugar Whisplay HAT** | Physical I/O interface | 1.69" IPS LCD (240×280), dual mics (WM8960), speaker, RGB LEDs, buttons |
| **PiSugar 3 Plus** | Battery / UPS | LiPo battery, power management, RTC, USB-C charging |

### Hardware Constraints & Design Implications

- **NPU memory (8GB)** limits model sizes. Max practical LLM: ~1.7B params (Qwen3-1.7B). ASR/TTS models must share this memory budget.
- **PCIe 2.0 x1** bandwidth (~500 MB/s) is the bottleneck between Pi and NPU. Minimize host↔NPU data transfers.
- **NPU draws ~7W at full load**; Pi 5 can draw ~12W. Combined ~19W exceeds PiSugar 3 Plus sustained output. Design for aggressive power management.
- **Cannot share PCIe with NVMe SSD**. Storage must be microSD or USB-attached.
- **Whisplay HAT uses I2C, SPI, I2S buses**. If using PiSugar 3 Plus simultaneously, disable AUTO switch on PiSugar to avoid I2C conflicts.
- **NPU has its own 8-core CPU** — can run inference workloads independently, freeing Pi 5 CPU for orchestration.

---

## 3. Software Architecture — Seven-Layer Stack

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACES                       │
│         Voice (Whisplay)  │  Web UI  │  LCD Display      │
├─────────────────────────────────────────────────────────┤
│                   AGENT FRAMEWORK                        │
│   Planner  │  Tool Registry  │  Agent Factory  │ Memory  │
├─────────────────────────────────────────────────────────┤
│                  SECURITY LAYER                          │
│  Permission Engine │ Sandbox │ Audit Log │ Crypto Store  │
├─────────────────────────────────────────────────────────┤
│                 REASONING CORE                           │
│     Qwen3-1.7B (primary)  │  Model Router │ Prompt Mgr  │
├─────────────────────────────────────────────────────────┤
│                  VOICE PIPELINE                          │
│   Button/Wake → ASR → [LLM] → TTS → Speaker             │
├─────────────────────────────────────────────────────────┤
│              HARDWARE ABSTRACTION LAYER                   │
│   NPU Driver (AXCL) │ Audio (WM8960) │ Display │ Power   │
├─────────────────────────────────────────────────────────┤
│                OPERATING SYSTEM                           │
│         Debian 12 / Raspberry Pi OS (hardened)           │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Layer Specifications

### 4.1 Hardware Abstraction Layer (HAL)

**Purpose:** Single point of access to all hardware. No other layer touches GPIO, PCIe, I2C, SPI, or I2S directly.

**Components:**
- **NPU Service** — Wraps AXCL Runtime (Python bindings). Manages model loading/unloading on NPU memory, inference queuing, and NPU health monitoring (temperature, memory, utilization). Exposes a local gRPC or Unix socket API.
- **Audio Service** — Manages WM8960 codec via ALSA. Handles mic input (16kHz mono for ASR), speaker output, volume control, and audio routing (internal speaker vs external via XH2.0).
- **Display Service** — Drives Whisplay LCD via SPI (ST7789 controller). Provides framebuffer abstraction for UI rendering. Manages RGB LEDs and button input events.
- **Power Service** — Interfaces with PiSugar 3 Plus power manager daemon. Reports battery level, charging state, estimated runtime. Triggers power-saving modes. Provides RTC access.
- **Camera Service** — Manages CSI camera module (e.g., Freenove, Raspberry Pi Camera) via `libcamera`/`picamera2`. Provides single-frame capture on demand (not continuous streaming). Supports resolution negotiation and format conversion (JPEG/PNG). Camera is optional hardware — system operates fully without it.

**Key Design Decisions:**
- All HAL services run as systemd units with dedicated service accounts (no root).
- Hardware access controlled via udev rules and Linux capability sets.
- HAL exposes a unified event bus (e.g., ZeroMQ or D-Bus) for hardware events (button press, low battery, NPU thermal throttle).

#### 4.1.1 System Health & Monitoring

A dedicated HAL-level service that continuously monitors system health and publishes status on the ZeroMQ event bus. Other layers (agent framework, web UI, display UI, notification system) subscribe to health events.

**Monitored Metrics:**

| Component | Metrics | Poll Interval | Alert Threshold |
|---|---|---|---|
| NPU | Temperature, CMM usage, utilization % | 5s | Temp > 75°C (throttle), > 85°C (shutdown) |
| CPU (Pi 5) | Temperature, load average, usage % | 10s | Temp > 80°C, load > 3.0 |
| Memory (Pi 5) | RAM usage %, swap usage % | 30s | RAM > 85%, swap > 50% |
| Storage | Disk usage %, I/O latency | 60s | Disk > 90% |
| Battery | Level %, charging state, estimated runtime | 30s | < 15% (low), < 5% (critical) |
| Network | Connectivity to configured endpoints | 60s | Unreachable for > 30s |
| Services | systemd unit status for all Cortex services | 10s | Any unit in failed state |

**Health API Endpoint:**

`GET /api/health` — FastAPI endpoint, no auth required on local network. Returns JSON:
```json
{
  "status": "healthy | degraded | critical",
  "uptime_seconds": 12345,
  "components": {
    "npu": {"status": "healthy", "temp_c": 62, "cmm_used_mb": 4500, "cmm_total_mb": 7040},
    "cpu": {"status": "healthy", "temp_c": 55, "load_1m": 1.2},
    "memory": {"status": "healthy", "used_pct": 45},
    "storage": {"status": "healthy", "used_pct": 32},
    "battery": {"status": "healthy", "level_pct": 85, "charging": true},
    "services": {"status": "healthy", "failed": []}
  },
  "models_loaded": ["sensevoice", "qwen3-1.7b", "kokoro", "smolvlm2-500m"]
}
```
Overall `status` is the worst of any component: all healthy = healthy, any warning = degraded, any critical = critical.

**NPU Thermal Management (4 zones):**

| Zone | Temperature | Behavior | User Impact |
|---|---|---|---|
| Normal | < 65°C | Full speed, all models co-resident | None |
| Warm | 65-75°C | Log warning, monitor trend | None (transparent) |
| Throttle | 75-85°C | Reduce generation speed, pause non-essential models | Transparent unless sustained >30s, then "I need to cool down for a moment." |
| Shutdown | > 85°C | Emergency model unload, NPU service restart | "Something's too hot. Give me a minute to cool down." |

**Watchdog:**
- **systemd software watchdog:** `WatchdogSec=30` on the main Cortex service. If the service fails to send a heartbeat within 30s, systemd restarts it. On restart: health check runs, models reloaded, pending timers/reminders recovered from SQLite.
- **Max restarts:** 3 within 5 minutes. After that, systemd gives up — LCD shows static error screen, LED pulses red, web UI shows diagnostic page.
- **Hardware watchdog (Phase 6):** Raspberry Pi BCM2835 hardware watchdog via `dtparam=watchdog=on`. Recovers from kernel panics and complete system freezes.

**Graceful Degradation Matrix:**

| Failure | User Experience | System Behavior |
|---|---|---|
| All LLM providers fail | "I can't think right now, but I can still set timers and tell you the time." | Rule-based fallback: regex-matched commands for utility agents (timer, clock, system status). No LLM-dependent features. |
| TTS fails | Response displayed as text on LCD | Silent mode — all responses visual-only. Log TTS error. |
| ASR fails | LCD shows "Voice unavailable — use web UI" | Web UI text input still works. Button press plays error tone. |
| Network down | (Transparent for local-only operation) | Cloud providers marked unavailable. Local NPU continues. User notified only when attempting a network-dependent action. |
| Battery < 15% | "Battery is getting low." | Reduce LCD brightness, suspend non-essential polling, disable IoT monitoring. |
| Battery < 5% | "Battery critical. Saving state and shutting down." | Save working memory, pending schedules. Clean shutdown. |
| Storage full | "I'm running out of storage space." | Disable audit log writes (ring buffer), stop memory extraction, alert user to free space. |
| Service crash | (Brief interruption, ~5-10s) | systemd auto-restart, state recovery from persistent storage. |

**Error UX Principles:**
1. Never show raw error messages or stack traces to the user via voice or LCD.
2. Always provide a human-readable explanation of what went wrong and what the user can do.
3. Self-recoverable failures → tell the user to wait. Non-recoverable → tell the user what manual step is needed.
4. Full technical details logged to audit system for primary user to review via web UI.
5. LCD always shows *something* — even in catastrophic failure, display a static "Cortex is having trouble — check the web dashboard" screen.

#### 4.1.2 Power-Aware Operation Profiles

The system adapts its capability level based on power state, balancing performance against battery life. The Power Service publishes charging state changes on the ZeroMQ event bus; the Model Router and other services subscribe and adjust automatically.

**Profile Definitions:**

| Profile | Trigger | LLM | ASR | TTS | Health Polling | Display |
|---|---|---|---|---|---|---|
| `mains` | AC power detected (PiSugar charging) | Qwen3-1.7B (`chat` profile) | SenseVoice | Kokoro (full) | Full intervals | Full brightness |
| `battery` | On battery, > 15% | Qwen3-0.6B (`quick` profile) | SenseVoice | Kokoro (full) | 2x intervals | 50% brightness |
| `low_battery` | Battery < 15% | Qwen3-0.6B (`quick` profile) | SenseVoice | Kokoro (short) | 4x intervals | 30% brightness |
| `critical` | Battery < 5% | None (regex-only utility commands) | None | None (LCD text only) | Off | Dim, static |

**Behavior on Profile Transitions:**
- `mains` → `battery`: Load Qwen3-0.6B, unload Qwen3-1.7B, reduce polling, dim display. Voice feedback: "Switched to battery mode."
- `battery` → `mains`: Load Qwen3-1.7B, unload Qwen3-0.6B, restore full polling/brightness. Voice feedback: "Full power restored."
- `battery` → `low_battery`: Further reduce polling, skip post-session memory extraction (defer to next mains period), disable proactive engine.
- `low_battery` → `critical`: Unload all NPU models, save state, enter minimal mode. LCD shows: "Battery critical — limited to basic commands."
- `critical` → shutdown: Clean shutdown after saving working memory and pending schedules to SQLite.

**Manual Override:** User can say "Full power mode" (force `mains` profile regardless of battery) or "Battery mode" (force `battery` profile on mains power for quieter operation). Override persists until next power state change or explicit reversal.

**Configuration:** Thresholds and profile mappings in `hal.power.profiles` config section. Model profile names reference existing entries in `reasoning.profiles` (§4.3.5).

#### 4.1.3 NPU Service Protocol

The NPU Service interface is defined as a Python `Protocol` class that is **hardware-agnostic**. No AXCL-specific types, constants, or behaviors leak into the interface. All AXCL specifics are isolated inside the `AxclNpuService` implementation.

```python
class NpuService(Protocol):
    """Hardware-agnostic NPU service interface."""
    async def load_model(self, model_id: str, model_path: Path) -> ModelHandle: ...
    async def unload_model(self, handle: ModelHandle) -> None: ...
    async def infer(self, handle: ModelHandle, inputs: InferenceInputs) -> InferenceOutputs: ...
    async def get_status(self) -> NpuStatus: ...  # temp, memory usage, utilization
    @property
    def capabilities(self) -> NpuCapabilities: ...  # total memory, compute TOPS, supported formats
```

**Key design constraints:**
- `InferenceInputs` and `InferenceOutputs` use generic numpy arrays, not AXCL-specific tensor types
- `ModelHandle` is an opaque identifier — implementation-specific metadata hidden behind it
- `NpuStatus` and `NpuCapabilities` are plain dataclasses with no hardware-specific fields
- All model-specific logic (axmodel format, CMM memory management, context switching) lives inside `AxclNpuService`

**Implementations:**

| Class | Hardware | Phase |
|---|---|---|
| `AxclNpuService` | M5Stack LLM-8850 (AX8850, AXCL runtime) | Phase 1 |
| `HailoNpuService` | Raspberry Pi AI HAT+ 2 (Hailo-10H, 40 TOPS, 2.5W) | Future |
| `MockNpuService` | No hardware (returns synthetic responses) | Phase 1 (testing) |

**Rationale:** The Raspberry Pi AI HAT+ 2 (January 2026, $130) offers 40 TOPS, 8GB LPDDR4X, and dramatically lower power (2.5W vs 7W for LLM-8850). By abstracting the NPU interface from Phase 1, Cortex can support multiple NPU backends without changing any code above the HAL layer. This is a design discipline — it constrains how the AXCL implementation is written, not an additional feature.

---

### 4.2 Voice Pipeline

**Purpose:** Real-time voice interaction loop, fully local.

**Pipeline Stages:**

```
Physical Pi (button-driven):
Button Hold → Mic → ASR ──→ Intent/LLM ──→ TTS ──→ Speaker
                                                      │
                                                  LCD Update

Web UI (button-driven):
Record Button → Mic → ASR ──→ Intent/LLM ──→ TTS ──→ Browser Audio
  (hold or        (or text bypass)
  click start/
  click stop)
```

**No VAD anywhere.** Both interfaces use explicit user-controlled recording boundaries:
- **Physical Pi:** Whisplay button (GPIO 11) held = recording, released = send to ASR.
- **Web UI:** Record button mirrors the physical button — hold-to-talk or click-to-start/click-to-stop. The user explicitly controls when recording begins and ends.

This eliminates VAD entirely from the system — no Silero, no silence detection, no false activations, no always-on mic. The user is always in control of when audio is captured.

**Model Allocation on NPU (7,040 MiB CMM usable):**

*Confirmed benchmarks from [AXERA-TECH](https://huggingface.co/AXERA-TECH) and [M5Stack docs](https://docs.m5stack.com/en/guide/ai_accelerator/llm-8850/m5_llm_8850_npu_benchmark):*

| Model | Purpose | CMM Used | CMM Remaining | Performance (M.2 + Pi 5) |
|---|---|---|---|---|
| SenseVoice-Small | ASR (Speech-to-Text) | ~500MB | ~6,540 MB | RTF 0.015 (67x real-time), ~50-75ms per utterance |
| Qwen3-0.6B (w8a16) | Quick commands / orchestrator | ~2.0 GB | ~5,068 MB | 12.88 tok/s |
| **Qwen3-1.7B (w8a16)** | **Primary LLM (default)** | **~3.3 GB** | **~3,788 MB** | **7.38 tok/s** |
| Kokoro-82M (v1.0, axmodel) | TTS (Text-to-Speech) | ~237MB | — | RTF 0.067 (15x real-time) |
| SmolVLM2-500M | Vision (always resident) | ~500MB | — | TBD (Phase 0 testing) |
| **Default co-resident set** | | **~4.5 GB** | **~2.5 GB** | All models loaded simultaneously |

**Why not Qwen3-4B?** Evaluated — uses 6.2 GB CMM (691 MB remaining), only 3.65 tok/s, max 2,559 tokens. Cannot co-reside with ANY other model. Every voice interaction would require sequential model swaps (ASR→LLM→TTS). Not viable as primary. Available as hot-swap for heavy reasoning when Pulsar2 v4.2 releases. See DD-029.

**Vision model hot-swap pool (loaded on demand, replaces Qwen3-1.7B temporarily):**

| Model | Purpose | Est. NPU Memory | Notes |
|---|---|---|---|
| InternVL3-1B | Detailed image analysis | ~1.5GB (est.) | Best quality; requires unloading LLM |
| Qwen2.5-VL-3B-Instruct | Advanced multimodal reasoning | ~3GB (est.) | Largest; requires unloading LLM + possibly ASR |
| Qwen3-VL-4B-GPTQ-Int4 | Combined LLM+VLM (future) | ~5.1 GB | INT4; replaces both LLM and VLM; needs Pulsar2 v4.2 |

**Additional models available from [AXERA-TECH catalog](https://huggingface.co/AXERA-TECH) (148 models) — evaluate in Phase 0:**
- DeepSeek-R1-Distill-Qwen-1.5B (alternative reasoning), InternVL3.5, FastVLM, MiniCPM4-V (newer VLMs)
- Qwen3-Embedding-0.6B (potential NPU-accelerated embedding model for memory retrieval)

**Activation Modes:**
1. **Button push-to-talk (physical Pi, default)** — Whisplay button (GPIO 11) held down; audio captured while held, sent to ASR on release. Zero false activations.
2. **Button push-to-talk (Web UI)** — Browser record button mirrors physical button: hold-to-talk or click-to-start/click-to-stop. User controls recording boundaries explicitly.
3. **Text input (Web UI)** — Bypasses voice pipeline entirely.

**Latency Budget (voice round-trip, first audio target: < 3 seconds):**
- ASR: < 500ms for typical utterance (button release triggers immediate ASR — no VAD delay on any interface)
- LLM first token: ~1-2s (prefill)
- LLM generation (50-token response @ 7.38 tok/s): ~6.8s total
- TTS first audio: < 200ms after first sentence complete (streaming)
- **Critical optimization:** Stream TTS while LLM is still generating (sentence-level chunking). First audio plays within ~5s of button release even though full generation takes longer. See Streaming Voice Pipeline below.

#### 4.2.1 Streaming Voice Pipeline

**Problem:** At 7.38 tok/s, a 50-token response takes ~6.8s of silence before the user hears anything. Unacceptable for voice UX.

**Solution:** Sentence-boundary streaming with parallel TTS — deliver audio sentence-by-sentence while the LLM is still generating.

```
LLM generates tokens ──→ Sentence Detector ──→ TTS Queue ──→ Audio Output
    (7.38 tok/s)          (buffer until          (Kokoro       (sequential
                           sentence end)          synthesis)     playback)
```

**Sentence Boundary Detection:**
Lightweight buffer on Pi 5 CPU that accumulates LLM output tokens and flushes on sentence boundaries:
- **Primary triggers:** `.` `!` `?` followed by whitespace or end-of-generation
- **Secondary triggers:** `:` `;` `—` followed by whitespace (for lists, clauses)
- **Minimum chunk:** 8 tokens (avoids tiny fragments that sound choppy)
- **Maximum chunk:** 96 tokens (Kokoro axmodel limit, matches `tts.axcl.max_chunk_tokens` in config)
- **End flush:** When LLM generation completes, flush any remaining buffered tokens regardless of boundary
- Simple state machine implementation — no NLP library, negligible CPU overhead.

**Parallel TTS via NPU Model Multiplexing:**
LLM (Qwen3-1.7B) and TTS (Kokoro-82M) are co-resident in NPU memory. While the LLM generates sentence 2, Kokoro synthesizes sentence 1. The AXCL runtime supports context-switching between co-resident models. Phase 0 testing must verify context-switch latency is acceptable.

Audio chunks played sequentially with 10ms linear crossfade (NumPy on CPU) to prevent pops/clicks at sentence boundaries.

**Timeline example (3-sentence, ~80-token response):**
```
t=0.0s  Button released, ASR starts
t=0.5s  ASR complete (~50-75ms SenseVoice), LLM prefill begins
t=1.5s  LLM first token generated
t=4.0s  First sentence complete (~18 tokens, ~2.4s generation)
t=4.2s  Kokoro synthesizes sentence 1 (RTF 0.067 ≈ ~200ms for short sentence)
t=4.4s  *** FIRST AUDIO PLAYS ***
t=6.5s  Second sentence complete (generated while sentence 1 plays)
t=6.7s  Kokoro synthesizes sentence 2 (overlapped with playback of sentence 1)
t=9.0s  Third sentence complete → synthesize → play seamlessly
```

**Audio Format:**

| Stage | Format | Sample Rate | Notes |
|---|---|---|---|
| Mic input (ASR) | S16_LE mono PCM | 16,000 Hz | WM8960 codec, ALSA capture |
| Kokoro TTS output | Float32 PCM | 24,000 Hz | Native Kokoro output rate |
| Speaker output | S16_LE mono PCM | 24,000 Hz | WM8960 playback via ALSA |
| Web UI audio | Opus or PCM | 24,000 Hz | WebSocket binary frames or Web Audio API |

**Latency Metrics (logged per voice interaction for profiling):**

| Metric | Target | Measurement Point |
|---|---|---|
| Time-to-first-audio (TTFA) | < 5.0s | Button release → first audio sample out of speaker |
| ASR latency | < 500ms | Button release → ASR text available |
| LLM prefill latency | < 1.5s | ASR complete → first LLM token |
| TTS chunk latency | < 300ms | Sentence text → audio chunk ready |
| Inter-chunk gap | < 50ms | End of chunk N playback → start of chunk N+1 |

**Fallback:** If Phase 0 testing shows NPU model context-switching is too slow for parallel operation, fall back to sequential mode: generate full LLM response, then synthesize and play all at once. TTFA degrades to ~7-10s but the system remains fully functional. Sequential mode is the pessimistic baseline; streaming is the optimistic target.

**NPU Memory Management Strategy:**
- Default: all four primary models co-resident (~4.5 GB of 7 GB, ~2.5 GB headroom).
- Kokoro uses a hybrid pipeline: 3 axmodel parts on NPU + ONNX vocoder on CPU, reducing NPU memory pressure.
- Monitor via NPU Service; degrade gracefully (e.g., smaller ASR model) if memory pressure detected.
- **Vision hot-swap:** SmolVLM2-500M stays resident for quick image descriptions (~500MB). For detailed analysis, unload Qwen3-1.7B, load InternVL3-1B or Qwen2.5-VL-3B, process image, then swap back. Voice pipeline pauses during hot-swap.
- **Heavy reasoning hot-swap (future):** Qwen3-4B or Qwen3-VL-4B can be loaded for complex tasks, but requires unloading all other models. Only viable when hot-swap latency is confirmed acceptable (Phase 0 testing).

---

### 4.3 Reasoning Core

**Purpose:** The "brain" — language understanding, planning, tool dispatch.

**Default Primary Model:** Qwen3-1.7B (w8a16 quantization on AX8850)
- Native Hermes-style tool calling support
- Thinking/non-thinking mode switching (thinking for complex tasks, non-thinking for quick responses)
- 32K native context window

#### 4.3.1 Model Provider Layer

All model interactions (LLM, ASR, TTS, VLM) are routed through a **provider-agnostic abstraction layer**. This decouples the reasoning core from any specific inference backend, allowing the same agent framework to use local NPU models, cloud APIs, or remote LLM servers — configured per profile.

**Core abstraction:** Each model category (LLM, ASR, TTS, VLM) has a **Provider Protocol** — a Python `Protocol` class defining the async interface. Provider implementations are thin adapters (~50-100 lines each) that translate between Cortex's internal format and the provider's API.

```
┌─────────────────────────────────────────────────────┐
│                  MODEL ROUTER                        │
│   Profile → Provider Chain → Context Adaptation      │
├──────┬──────┬──────┬──────┬──────┬─────────────────┤
│ AXCL │ OAI- │ Anth │ Goog │ Olla │  Custom         │
│ NPU  │ Comp │ ropi │ le   │ ma   │  (any URL)      │
│      │ at   │ c    │      │      │                  │
└──────┴──────┴──────┴──────┴──────┴─────────────────┘
  Local    Cloud APIs              LAN/Remote
```

**Provider types:**

| Provider ID | Backend | Covers | LLM | ASR | TTS | VLM |
|---|---|---|---|---|---|---|
| `axcl` | Local NPU (AXCL runtime) | M5Stack LLM-8850 | Yes | Yes (sherpa-onnx) | Yes (Kokoro hybrid) | Yes |
| `openai` | OpenAI API | GPT-4o, GPT-4, Whisper API | Yes | Yes | Yes | Yes |
| `anthropic` | Anthropic API | Claude 4.5/4.6 family | Yes | No | No | Yes |
| `google` | Google AI API | Gemini 2.x family | Yes | Yes (Cloud STT) | Yes (Cloud TTS) | Yes |
| `xai` | xAI API (OpenAI-compatible) | Grok | Yes | No | No | Yes |
| `ollama` | Ollama server | Any GGUF model | Yes | No | No | Yes (LLaVA, etc.) |
| `openai_compatible` | Any OpenAI-compatible API | vLLM, LiteLLM, TGI, Groq, Together | Yes | No | No | Varies |

`openai_compatible` is the **universal adapter** — most remote LLM servers expose OpenAI-compatible APIs. This single provider covers the majority of remote/LAN use cases.

**LLM Provider Protocol:**
```python
class LLMProvider(Protocol):
    """Provider-agnostic LLM interface."""
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        stop: list[str] | None = None,
    ) -> CompletionResponse: ...

    @property
    def capabilities(self) -> ModelCapabilities: ...
    # context_window, supports_tools, supports_vision,
    # supports_streaming, tool_call_format, supports_thinking_mode
```

Similar protocols for `ASRProvider` (audio → text), `TTSProvider` (text → audio), `VLMProvider` (image + text → text).

**Use cases:**

| Scenario | Network | LLM Provider | ASR/TTS Provider | Description |
|---|---|---|---|---|
| Fully offline | None | `axcl` (Qwen3-1.7B) | `axcl` (SenseVoice/Kokoro) | Physical Pi, no internet. Primary use case. |
| LAN-only | LAN | `axcl` | `axcl` | Web UI accesses Pi on local network. |
| Internet-connected | Internet | `axcl` primary, cloud fallback | `axcl` | Local NPU for speed; cloud for complex tasks. |
| Remote LLM server | LAN/Internet | `ollama` or `openai_compatible` | `axcl` | Bigger models on another machine; Pi orchestrates. |
| Cloud-primary | Internet | `anthropic` or `openai` | `openai` or `google` | Pi as thin client; all inference in cloud. |

#### 4.3.2 Tool Calling Adaptation

Different providers use different tool calling formats. The Model Router handles translation transparently through a **Tool Adapter**:

| Provider | Tool Call Format | Adaptation |
|---|---|---|
| `axcl` (Qwen3) | NousFnCallPrompt (`<tool_call>` XML) | Qwen-Agent parser (current) |
| `openai` / `openai_compatible` / `xai` | OpenAI function calling JSON | Native — canonical format |
| `anthropic` | `tool_use` content blocks | Translate to/from canonical |
| `google` | `functionCall` / `functionResponse` | Translate to/from canonical |
| `ollama` | OpenAI-compatible function calling | Native — canonical format |

**Canonical internal format:** OpenAI function calling schema (most widely supported). Cognitive tools and action templates are defined once in canonical format. The Tool Adapter translates to/from provider-specific formats at the boundary. For `axcl`, Qwen-Agent NousFnCallPrompt remains the parser.

#### 4.3.3 Provider-Managed Context

Each provider knows its own context window limits. The agent framework passes the full conversation (system prompt, tool descriptions, history, user request) to the provider — the provider handles truncation or summarization if the context exceeds its capacity.

**Why no central Context Manager:** With providers ranging from 4K (local NPU) to 200K+ (cloud APIs), a centralized budget system would either over-constrain large-context providers or require complex scaling logic. Instead:
- The agent framework constructs the ideal prompt (all relevant history, full tool descriptions).
- The provider truncates from the oldest history if needed, preserving system prompt and current request.
- Local NPU providers are naturally limited by their 4K effective window — no artificial budgeting required.
- Cloud providers use their full capacity — more history means better multi-turn reasoning.

#### 4.3.4 Profile-to-Provider Routing

Each model profile specifies an ordered **provider chain** — the Model Router tries providers in order until one succeeds:

```yaml
profiles:
  chat:
    providers: [axcl, ollama, openai]  # NPU → Ollama → OpenAI
    axcl: { model: qwen3-1.7b, mode: non_thinking }
    ollama: { model: qwen3:8b }
    openai: { model: gpt-4o-mini }
  reason:
    providers: [axcl, anthropic]
    axcl: { model: qwen3-1.7b, mode: thinking }
    anthropic: { model: claude-sonnet-4-6 }
```

**Fallback logic:**
1. Try the first enabled provider in the chain.
2. If unavailable (network down, NPU error, API timeout) → try next provider.
3. If all providers fail → report inability to orchestrator → escalate to user.
4. **Circuit breaker:** After 3 consecutive failures for a provider, skip it for 60s before retrying.

**Default configuration:** All profiles route to `axcl` only (fully offline). Cloud and remote providers are opt-in — the user explicitly enables them in config.

#### 4.3.5 Model Router

The Model Router maps task profiles to providers and models:

| Profile | Default Provider | Default Model | Use Case | Mode |
|---|---|---|---|---|
| `chat` | `axcl` | Qwen3-1.7B | General conversation | Non-thinking |
| `reason` | `axcl` | Qwen3-1.7B | Complex planning, multi-step tasks | Thinking |
| `code` | `axcl` | Qwen3-1.7B | Tool/agent code generation | Thinking |
| `quick` | `axcl` | Qwen3-0.6B | Simple commands, slot filling | Non-thinking |
| `vision_quick` | `axcl` | SmolVLM2-500M | Quick image descriptions (always resident) | Non-thinking |
| `vision_detail` | `axcl` | InternVL3-1B | Detailed image analysis (hot-swap) | — |
| `vision_advanced` | `axcl` | Qwen2.5-VL-3B | Advanced multimodal reasoning (hot-swap) | — |
| `fallback` | `openai` | gpt-4o-mini | Tasks beyond local capability | — |

Each row is fully configurable — any profile can be rerouted to any enabled provider via YAML config. The orchestrator and each super agent reference profiles by name, not specific models.

**Power-Aware Profile Selection:** The Model Router subscribes to power state changes on the ZeroMQ bus (see §4.1.2). When running on battery, the router overrides `chat`/`reason`/`code` profiles to use the `quick` model (Qwen3-0.6B) instead of Qwen3-1.7B, reducing NPU power consumption. The user can manually override this via voice ("Full power mode"). See DD-040.

**Prompt Management:**
- System prompts stored as versioned templates.
- Dynamic tool schema injection — only currently relevant tools are included in context.
- Conversation history: full history passed to provider; provider truncates oldest turns if context exceeded.
- Persona/behavior configurable via web UI.

---

### 4.4 Agent Framework

**Purpose:** Enable the LLM to reason freely, plan multi-step tasks, use tools, and execute pre-authorized actions — all within the extreme constraints of a 1.7B model at 4K context.

**Design Philosophy:** *Unconstrained thinking, constrained acting.* Agents can reason, plan, and discuss without restriction using cognitive tools (read-only, safe). But when an agent needs to change the world — control a device, write a file, send a request — the action flows through a pre-authorized Action Template with parameter validation, permission gating, and audit logging.

#### 4.4.1 Three-Tier Agent Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                     USER REQUEST                             │
│              (voice / web / scheduled)                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              CORTEX ORCHESTRATOR                             │
│         Lightweight classifier (~370 tokens)                 │
│         Single LLM call → routes to agent                    │
│         Fallback: general-purpose super agent                │
└────┬──────────────┬───────────────────┬─────────────────────┘
     ▼              ▼                   ▼
┌─────────┐  ┌─────────────┐    ┌──────────────┐
│ Utility  │  │ Super Agent │    │ Super Agent  │  ...
│ Agent    │  │ (home)      │    │ (research)   │
│ (direct  │  │             │    │              │
│  action) │  │ Cognitive   │    │ Cognitive    │
│          │  │ Tools ──┐   │    │ Tools ──┐    │
│          │  │         ▼   │    │         ▼    │
│          │  │   Reason    │    │   Reason     │
│          │  │     │       │    │     │        │
│          │  │     ▼       │    │     ▼        │
│          │  │  Action     │    │  Action      │
│          │  │  Request    │    │  Request     │
└────┬─────┘  └─────┬──────┘    └──────┬───────┘
     │              │                  │
     ▼              ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    ACTION ENGINE                             │
│  YAML Templates → Permission Gate → Executor → Audit Log    │
│  (deterministic, pre-authorized, sandboxed)                  │
└─────────────────────────────────────────────────────────────┘
```

**Framework choice:** Custom lightweight agent framework (inspired by LangGraph's graph-of-functions pattern and smolagents' delegation model). Tool calling parsed via the Model Provider Layer's Tool Adapter (§4.3.2), which translates between the canonical format and provider-specific formats (NousFnCallPrompt for local Qwen3, OpenAI function calling for cloud/remote). All evaluated frameworks (CrewAI, LangGraph, AutoGen, smolagents, Swarm) were rejected for full adoption due to resource constraints — see DD-018.

#### 4.4.2 Cortex Orchestrator

The orchestrator is a **single-LLM-call classifier** — not a full agentic loop. It receives the user request, selects the best agent, and delegates. Simple direct commands (e.g., "turn off the lights") route directly to a utility agent, bypassing super agents entirely.

**Token budget:** ~370 tokens total
- System prompt (classifier instructions): ~150 tokens
- Agent descriptions (5-8 agents, ~30 tokens each): ~150-240 tokens
- User request: ~50 tokens
- Generation (agent name + parameters): ~20 tokens

**Routing logic:**
1. If request matches a utility agent's pattern (regex/keyword) → route directly (no LLM call)
2. Otherwise → single LLM call to classify intent and select super agent
3. If classification confidence < threshold (default 0.6) → request clarification before routing (see §4.6.5)
4. If no confident match even after clarification → route to general-purpose super agent
5. If super agent reports inability → escalate to user
6. Phase 4: can spawn ephemeral super agents on-the-fly for novel multi-step tasks

#### 4.4.3 Super Agents

Super agents handle complex, multi-step tasks that require reasoning and planning. Each has a focused domain, a small cognitive tool set (2-3 tools), and an independent context window.

**Characteristics:**
- Independent context window (strict 4K budget per agent)
- Small, focused tool set (2-3 cognitive tools + action request capability)
- Tool calling via Model Provider Layer's Tool Adapter (§4.3.2) — format auto-selected per active provider
- Max 3-4 LLM calls per task (configurable per agent)
- Can be persistent (pre-defined in YAML) or ephemeral (spawned by orchestrator)

**Token budget per super agent:**
```
System prompt (stripped Nous format):     ~200 tokens
Tool descriptions (2-3 tools, ~50 each): ~150 tokens
User request / delegated task:           ~50 tokens
Working space (history + generation):    ~3,600 tokens
────────────────────────────────────────────────────
Total:                                   ~4,000 tokens
```

**Built-in super agents (Phase 2):**

| Agent | Domain | Cognitive Tools | Typical Actions |
|---|---|---|---|
| `general` | Catch-all conversation | memory_query, knowledge_search | (none — pure conversation) |
| `home` | Smart home control | device_state, memory_query | set_light, set_thermostat, run_scene |
| `research` | Information gathering | web_search, knowledge_search | save_note, create_reminder |
| `system` | System administration | system_info, process_list | shell_exec, file_write, service_restart |
| `planner` | Multi-step task planning | memory_query, calendar_query | create_reminder, create_task |
| `vision` | Image understanding | image_analyze, memory_query | save_note (image description) |
| `pim` | Personal information management | calendar_query, email_query, contact_lookup | calendar_create, notification_send_external, email_send, task_sync |

**Super agent definition (YAML):**
```yaml
# config/agents/home.yaml
id: home
name: "Home Control Agent"
description: "Controls smart home devices and scenes"
persistent: true
max_llm_calls: 3
model_profile: chat  # non-thinking for speed
cognitive_tools: [device_state, memory_query]
action_templates: [set_light, set_thermostat, run_scene, lock_door]
system_prompt: |
  You are a home control agent. You can query device states
  and execute authorized home automation actions.
  Be concise. Respond in 1-2 sentences.
```

#### 4.4.4 Utility Agents

Utility agents are **pure deterministic dispatchers** — they consume **zero LLM tokens**. The orchestrator (or a super agent) provides a structured action request, and the utility agent validates parameters and dispatches to the Action Engine.

**Characteristics:**
- No LLM calls — pure parameter validation + dispatch
- One utility agent per action domain
- Fast execution (no inference latency)
- Called directly by the orchestrator for simple commands, or by super agents as the final step of a plan

**Built-in utility agents:**
- `action_dispatcher` — generic dispatcher for any action template
- `notification` — LED, LCD, speaker, push notifications
- `timer` — create/cancel timers and reminders
- `pim_dispatcher` — calendar, email, and task actions (create/update/delete events, send email, sync tasks)

#### 4.4.5 Action Engine

The Action Engine is a **custom Python workflow executor** running in-process (zero additional RAM, no external services). It provides the deterministic action layer — all world-changing operations flow through here.

**Architecture:**
- **Template Registry** — loads and caches YAML action templates from `config/actions/`
- **Permission Gate** — checks the action's tier against the 4-tier permission model (§4.5)
- **Parameter Validator** — validates input against the template's typed schema (patterns, enums, ranges)
- **Executor** — runs Python handler functions, optionally in bubblewrap sandbox
- **Audit Logger** — structured log entry for every execution (success or failure)

**Action Template format (YAML):**
```yaml
# config/actions/smart_home/set_light.yaml
id: set_light
name: "Set Light State"
description: "Turn a light on/off or set brightness"
version: 1
permission_tier: 1  # Normal — logged, auto-approved
timeout_seconds: 10
retry:
  max_attempts: 2
  backoff_seconds: 1

parameters:
  entity_id:
    type: string
    required: true
    pattern: "^light\\..+$"
  state:
    type: string
    required: true
    enum: ["on", "off"]
  brightness:
    type: integer
    required: false
    min: 0
    max: 255

handler: cortex.actions.handlers.home_assistant.set_light_state

result:
  success_template: "{{ entity_id }} turned {{ state }}"
```

**Python handler pattern:**
```python
@action_handler("home_assistant.set_light_state")
async def set_light_state(
    entity_id: str, state: str, brightness: int | None = None
) -> ActionResult:
    """Deterministic handler — no LLM, just validated API call."""
    ...
```

**Key properties:**
- Handlers are plain async Python functions — testable, debuggable, type-checked
- Each template has a fixed permission tier (set by human when template is created/approved)
- Parameter schemas prevent injection (e.g., `entity_id` must match `^light\..+$`)
- Untrusted/dynamically-created handlers run in bubblewrap sandbox
- All executions logged to audit system: template_id, parameters, caller, result, timing
- Templates are version-controlled and can be rolled back

#### 4.4.6 Cognitive Tools

Cognitive tools help super agents **think** — they are read-only, safe (Tier 0-1), and consume minimal context. They do NOT change the world.

| Tool | Purpose | Tier |
|---|---|---|
| `memory_query` | Search short-term and long-term memory | 0 |
| `knowledge_search` | Semantic search over knowledge store | 0 |
| `web_search` | Search the web (if network policy allows) | 1 |
| `device_state` | Query current state of smart home devices | 0 |
| `system_info` | CPU, memory, NPU, battery, network status | 0 |
| `calendar_query` | Read calendar/reminders | 0 |
| `file_read` | Read files in designated directories | 0 |
| `image_analyze` | Analyze image via VLM (camera, upload, or URL) | 0 |
| `clock` | Current time, date, timezone, sunrise/sunset | 0 |
| `timer_query` | Check active timers and their remaining time | 0 |
| `reminder_query` | Check upcoming reminders | 0 |
| `weather_query` | Current/forecast weather (requires network) | 1 |
| `calculator` | Evaluate mathematical expressions | 0 |
| `unit_convert` | Convert between units (temperature, distance, weight, volume, etc.) | 0 |
| `dictionary_lookup` | Word definitions, synonyms | 0 |
| `translate` | Translate text between languages (via LLM or API) | 1 |
| `list_query` | Read items from named lists (shopping, todo, etc.) | 0 |
| `email_query` | Check inbox for new/matching emails (IMAP read-only) — see §4.4.13 | 0 |
| `contact_lookup` | Look up contact info (name, phone, email) from local contacts store | 0 |

`calendar_query` has a real backend when external services (§4.4.13) are configured: CalDAV, Google Calendar API, or HA calendar via MCP. When no external service is configured, it returns only local reminders from the scheduling service.

`knowledge_search` queries the Knowledge Store (§4.4.10) — semantic search over ingested document chunks. Returns the most relevant passages for the user's query.

`clock`, `calculator`, `unit_convert`, and `dictionary_lookup` are implemented as pure Python functions — zero LLM cost, zero network, instant response. They are the fastest path for common everyday queries.

`image_analyze` accepts an image from three sources: physical camera capture, web UI upload/webcam, or a URL. It routes to the appropriate VLM profile (`vision_quick` for fast descriptions, `vision_detail` or `vision_advanced` when requested). See §4.3 Model Router for VLM profiles.

Defined in canonical (OpenAI function calling) format. The Tool Adapter (§4.3.2) translates to the active provider's format at call time (NousFnCallPrompt for local Qwen3, native format for cloud APIs).

#### 4.4.7 Agent Factory & Tool Development Pipeline (Phase 4)

The LLM can create new super agents and action templates dynamically:
- **New super agent:** LLM generates YAML agent definition → security validation → user approval (Tier 3) → registered
- **New action template:** LLM generates YAML template + Python handler → static analysis → sandbox test → user approval (Tier 3) → registered
- All dynamically created agents/templates are version-controlled and can be rolled back
- User can create, modify, and delete agents via voice or web UI

**Tool Development Pipeline** — Tools (action templates) follow a structured lifecycle before deployment:

| Stage | Actor | Output | Gate |
|---|---|---|---|
| **Specify** | User or LLM | Tool spec: name, description, inputs/outputs, permission tier, dependencies | User review |
| **Develop** | LLM (or user) | YAML action template + Python handler implementation | Automated: ruff lint, mypy type check, static security analysis |
| **Review** | Automated + User | Test results, security scan report, dependency audit | All checks pass |
| **Approve** | User (Tier 3) | Signed approval with reason | Explicit user confirmation via button or web UI |
| **Deploy** | System | Template registered, handler loaded, available to agents | Audit log entry |

- **Spec-first:** Every tool starts as a specification (what it does, what it needs, what tier it requires) before any code is written. The LLM can draft specs from natural language requests.
- **Sandbox testing:** During Review, the handler runs in a bubblewrap sandbox against synthetic inputs. Must pass without errors or policy violations.
- **Rollback:** Deployed tools are version-controlled. Any version can be rolled back or disabled instantly. Rollback is Tier 1 (auto-approved, logged).
- **Promotion path:** Tools start at Tier 2 (require approval per-use). After N successful supervised executions (configurable, default 10), the user can promote to Tier 1 (auto-approved, logged) or Tier 0 (auto, silent).
- **Discovery:** The factory exposes a tool catalog (via web UI and voice) showing all tools with status (draft/review/approved/deployed/disabled), version, usage stats, and permission tier.

#### 4.4.8 MCP Protocol Support

Cortex supports the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) as both **client** and **server**, using the Python `mcp` SDK.

**MCP Client — Consume External Tool Servers (Phase 2):**
- Super agents can discover and call tools exposed by external MCP servers
- Use cases: Home Assistant MCP server, n8n MCP bridge (if running externally), custom tool servers
- Discovered tools are classified on registration:
  - Read-only tools → registered as cognitive tools (Tier 0-1)
  - State-changing tools → registered as action templates (Tier 2 by default, user can adjust)
- Tool schemas from MCP `list_tools()` are converted to canonical format and injected into super agent prompts (Tool Adapter handles provider-specific translation)
- MCP server connections configured in `config/mcp_servers.yaml` (similar to CAAL's pattern)
- Pre-flight connectivity test before `initialize()` to avoid hangs on bad connections
- Transport: Streamable HTTP (preferred) or stdio for local tool servers

**MCP Server — Expose Cortex Capabilities (Phase 3):**
- Cortex exposes its cognitive tools and action templates as MCP tools to external clients
- External AI clients (Claude Desktop, other agents, automation scripts) can discover and call Cortex tools
- All MCP server requests go through the same permission gate and audit log as internal requests
- Exposed via Streamable HTTP transport on the existing FastAPI server (no additional port)
- Resources: conversation memory, knowledge store, system status
- Prompts: pre-defined prompt templates for common interactions

**MCP Server Configuration (YAML):**
```yaml
# config/mcp_servers.yaml
servers:
  - name: homeassistant
    url: "http://homeassistant.local:8123/mcp"
    transport: streamable_http
    timeout_seconds: 5
    tool_prefix: ha  # tools registered as ha__<tool_name>
    default_permission_tier: 2  # user can override per-tool
    enabled: true

  - name: custom_tools
    command: "python -m cortex.mcp.custom_server"
    transport: stdio
    tool_prefix: custom
    default_permission_tier: 1
    enabled: false
```

#### 4.4.9 Context Assembly & Management

Context is **provider-managed** at the truncation level (see §4.3.3), but the agent framework controls **what goes into the prompt** via the Context Assembler. This is critical for the 4K local NPU, where only 2-3 raw turns fit — memories and summaries bridge the gap.

**Context Assembly Pipeline:**

```
User speaks → ASR → text
                ↓
┌────────────────────────────────┐
│      Context Assembler         │
├────────────────────────────────┤
│  P1: System prompt (required)  │  ← versioned template
│  P2: Current request (required)│  ← user's message
│  P3: Tool descriptions         │  ← pre-cached, agent-specific
│  P4: Retrieved memories        │  ← auto-injected from long-term memory
│  P5: Conversation summary      │  ← rolling summary of earlier turns
│  P6: Recent turns              │  ← last 1-2 full exchanges
│  P7: Older history             │  ← as many as fit
└────────────┬───────────────────┘
             ↓
     Provider.complete()
             ↓
     Response → TTS → Speaker
             ↓
     Update working memory
```

Components are assembled in priority order (P1 highest). Higher-priority items are never dropped; lower-priority items are included if space permits. The provider truncates from P7 upward as a safety net.

**Token budget by provider class:**

| Component | 4K local NPU | 32K+ remote | 128K+ cloud |
|---|---|---|---|
| System prompt | ~200 | ~200 | ~200 |
| Current request | ~50-200 | ~50-200 | ~50-200 |
| Tool descriptions | ~150 | ~150 | ~300 (richer) |
| Retrieved memories | ~100-200 (2-3 facts) | ~200-400 (4-6 facts) | ~400-800 (8-12 facts) |
| Conversation summary | ~100-150 | (not needed) | (not needed) |
| Recent turns | ~200-400 (1-2 turns) | ~2,000-4,000 | Full history |
| Older history | (dropped) | ~4,000-8,000 | Full history |
| **Generation budget** | **~2,700-3,200** | **~16,000-24,000** | **Remainder** |

**Automatic memory injection (P4):** Before each LLM call, the Context Assembler embeds the user's current message on CPU (~10-20ms) and queries sqlite-vec for the top-K nearest facts from long-term memory. Results are injected as a `[Memory]` block in the system prompt. No LLM call required — total latency ~20-40ms.

**Prompt construction per agent type:**

| Agent Type | System Prompt | Tool Descs | Memories | History | Generation |
|---|---|---|---|---|---|
| Orchestrator | Classifier (~150 tok) | Agent list (~150-240 tok) | None | Current request only | Agent name (~20 tok) |
| Super Agent | Domain (~200 tok) | 2-3 tools (~150 tok) | Auto-injected (P4) | Summary + recent (P5-P7) | Multi-turn reasoning |
| Utility Agent | None | None | None | None | None (deterministic) |

- Orchestrator does NOT get memory injection (it only classifies the request — no personalization needed)
- Super agents get full context assembly: memories + summary + recent turns
- Cloud providers (>32K context): summary is skipped, full history included instead

#### 4.4.10 Memory System

Six memory tiers, from volatile to permanent:

| Type | Storage | Purpose | Retention |
|---|---|---|---|
| **Working Memory** | RAM | Current conversation + rolling summary | Session |
| **Short-term Memory** | SQLite | Completed conversation summaries | 30 days (configurable) |
| **Long-term Memory** | SQLite + sqlite-vec | Atomic facts, user preferences, learned patterns | Persistent |
| **Episodic Memory** | SQLite + sqlite-vec | Significant events, decisions, outcomes | Persistent |
| **Knowledge Store** | SQLite + sqlite-vec | Ingested documents, manuals, reference material | Persistent |
| **Tool Memory** | Filesystem | Generated tools, agent configs, action templates | Persistent |

All memory encrypted at rest (see §4.5). User can inspect, edit, and delete any memory via web UI.

**Working Memory** (RAM, session-scoped):
- Full conversation message log (all turns, regardless of what fits in context window)
- Rolling conversation summary (compact text, ~100-150 tokens)
- Active task state (current agent, pending actions)

**Rolling summary mechanism:**
- **Trigger:** After every 3 completed exchanges, or when history exceeds 6 turns.
- **Method:** Context Assembler calls the primary LLM: "Summarize this conversation in 2-3 sentences: [current summary] + [new turns]". Max generation: 100 tokens. Total call: ~640 tokens — fits easily in 4K.
- **Scheduling:** Runs **during TTS playback** — while the speaker plays the response audio, the NPU is idle. Hides latency entirely. If the user interrupts before completion, the summary is abandoned and retried after the next response.
- **Fallback:** If summary fails, the system includes only the most recent raw turns (no summary). Functional but less coherent — summary is an optimization, not a requirement.
- **Cloud providers:** Summary is still generated (stored at session end) but full history is preferred in the prompt.

**Short-term Memory** (SQLite, 30 days):
- Stores completed conversation summaries and metadata:

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `started_at` / `ended_at` | datetime | Conversation time span |
| `summary` | text | Final rolling summary from working memory |
| `turn_count` | int | Number of exchanges |
| `topics` | text[] | Keyword-extracted topic tags (no LLM cost) |
| `transcript` | text (encrypted) | Full transcript — for user review only, never injected into prompts |

- Summary is the primary stored artifact — token-efficient, searchable, injectable.
- Retention: configurable (default 30 days, max 100 conversations).

**Long-term Memory** (SQLite + sqlite-vec, persistent):
- Stores atomic facts and preferences with vector embeddings for semantic retrieval:

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `content` | text | The fact (e.g., "User prefers 22°C for thermostat") |
| `category` | enum | `fact`, `preference`, `person`, `place`, `routine` |
| `embedding` | float[384] | Vector for semantic search |
| `source_conversation` | UUID | Which conversation produced this |
| `confidence` | float | 0.0-1.0, increases with repeated confirmation |
| `created_at` / `last_referenced` | datetime | Timestamps |
| `superseded_by` | UUID | Points to replacement if updated |

- **Atomic:** Each entry is a single fact, not a paragraph. Examples: "User's name is Andrew", "Kitchen has Philips Hue lights".
- **Mutable via superseding:** New fact replaces old (old retained for audit, excluded from search).
- **Auto-injected:** Context Assembler retrieves relevant facts before each LLM call (P4 in assembly pipeline).
- **Capacity:** 10,000 entries (configurable). When limit reached, least-referenced/lowest-confidence entries are pruning candidates (user prompted).

**Episodic Memory** (SQLite + sqlite-vec, persistent):
- Stores significant events and outcomes — narrative, not atomic:

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `event` | text | What happened |
| `outcome` | text | What resulted |
| `significance` | enum | `routine`, `notable`, `milestone` |
| `created_at` | datetime | When the event occurred |
| `embedding` | float[384] | Vector for semantic search |

- **Long-term = what IS true** (facts, preferences) → auto-injected, frequently referenced.
- **Episodic = what HAPPENED** (events, decisions) → retrieved on-demand via `memory_query` cognitive tool, NOT auto-injected.

**Memory Extraction** (post-session, LLM-based):

After a conversation ends (idle timeout, configurable — default 5 minutes):
1. System calls the primary LLM with conversation summary + last turns: "Extract key facts, preferences, and events as structured JSON."
2. LLM returns: `{"facts": [...], "events": [...]}`
3. Each fact is embedded on CPU (~10-20ms each), deduplicated against existing entries (cosine similarity > 0.85), and stored in long-term memory.
4. Each event is embedded and stored in episodic memory.
5. Conversation summary stored in short-term memory.

**NPU scheduling:** Extraction runs after the conversation ends — NPU is idle, no contention.

**In-conversation pattern extraction:** Simple regex patterns catch explicit requests ("remember that...", "my name is...", "I prefer...") and create long-term entries immediately. Zero LLM cost.

**Memory Retrieval** (automatic + explicit):

*Automatic injection (every LLM call):*
1. Embed user's message on CPU (~10-20ms)
2. Query sqlite-vec for top-K nearest long-term memories (K=3 for 4K, K=6 for 32K+, K=12 for 128K+)
3. Filter: exclude superseded, apply similarity threshold (0.3)
4. Format as `[Memory]` block in system prompt

*Explicit retrieval (via `memory_query` tool):*
- Agent calls `memory_query(query, types)` to search across ALL memory types
- Returns up to 10 results including episodic memories
- Used when an agent needs to recall specific past events

**Embedding Model:**
- `all-MiniLM-L6-v2` via ONNX Runtime on CPU
- 22MB model, 384-dim embeddings, ~10-20ms per embedding on Pi 5
- CPU-only — NPU reserved for LLM/ASR/TTS
- sqlite-vec brute-force KNN is fast enough for up to 50K entries at this scale
- Shared by long-term memory, episodic memory, and knowledge store — single embedding pipeline

**Knowledge Store** (persistent, document-level):
- Ingested documents (user manuals, reference material, saved articles, personal notes, recipes)
- Documents chunked into ~200-token overlapping segments (50-token overlap for context continuity)
- Each chunk embedded via same all-MiniLM-L6-v2 pipeline on CPU, stored in sqlite-vec
- Metadata per chunk: source document, chunk index, ingestion date, document title
- The `knowledge_search` cognitive tool (§4.4.6) queries this store — semantic search over document chunks
- **With 4K context, RAG is MORE valuable:** inject one high-relevance passage (~200 tokens) instead of hoping an entire document fits in context
- Ingestion sources: web UI file upload, watched directory (`data/knowledge/`), or via MCP tool
- Supported formats: `.txt`, `.md`, `.pdf`, `.html`
- Capacity: configurable (default 100 documents, ~50K chunks)
- Deduplication: same cosine similarity threshold (0.85) as long-term memory
- Example: "What does my router manual say about port forwarding?" → retrieves the most relevant chunk from the ingested manual

**Cloud Provider Privacy:**
- When `allow_sensitive_data: false` (default for cloud providers): the `[Memory]` block and conversation summary are stripped from prompts before sending. Only system prompt, tools, recent turns, and current request are sent.
- When `allow_sensitive_data: true`: full context including memories is sent. User explicitly opted in.

#### 4.4.11 Scheduling Service

Manages time-based triggers (timers, reminders, scheduled tasks). Must survive reboots.

**Architecture:**
- Persistent storage in SQLite (`data/schedules.db`).
- On startup: load all pending schedules, calculate next fire times, register with asyncio event loop.
- Uses `asyncio` scheduling for sub-second precision.
- On Cortex restart (systemd watchdog recovery): pending schedules recovered from SQLite automatically.

**Timer Schema:**

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `label` | text (optional) | User-provided name ("pasta timer") |
| `duration_seconds` | integer | Original timer duration |
| `created_at` | datetime | When set |
| `fires_at` | datetime | When it should fire |
| `status` | enum | `active`, `fired`, `cancelled` |
| `notification_priority` | integer | Default: P2 (chime) |

**Reminder Schema:**

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `message` | text | What to remind about ("Call Mom", "Take medication") |
| `fires_at` | datetime | When it should fire |
| `recurrence` | text | `null`, `daily`, `weekly`, `weekdays`, or cron expression |
| `status` | enum | `active`, `fired`, `snoozed`, `cancelled` |
| `notification_priority` | integer | Default: P3 (spoken) |
| `snooze_count` | integer | Number of times snoozed (max 3) |

**Timer/Reminder UX Flow:**

```
User: "Set a timer for 10 minutes"
  → Orchestrator routes to timer utility agent
  → timer_set action: duration=600, label=null
  → Scheduling Service creates timer in SQLite, fires_at = now + 600s
  → Confirmation: "Timer set for 10 minutes." (spoken)
  → LCD idle screen shows timer countdown

[10 minutes later]
  → Scheduling Service fires timer
  → Notification System delivers P2 notification (chime + LCD)
  → If user is mid-conversation: badge appears, notification queued until session ends

User: "How much time is left on my timer?"
  → timer_query cognitive tool returns remaining time
  → "You have about 4 and a half minutes left."
```

**Reminder snooze:** After a reminder fires, user can say "snooze" or single-click within 30s to snooze for 10 minutes (configurable). Max 3 snoozes per reminder.

**New action templates (all Tier 1):**

| Template | Purpose | Parameters |
|---|---|---|
| `timer_set` | Create countdown timer | `duration` (seconds), `label` (optional) |
| `timer_cancel` | Cancel active timer | `timer_id` or `label` |
| `reminder_set` | Create time-based reminder | `message`, `fires_at`, `recurrence` (optional) |
| `reminder_cancel` | Cancel a reminder | `reminder_id` or `message` match |
| `list_add` | Add item to a named list | `list_name`, `item` |
| `list_remove` | Remove item from a named list | `list_name`, `item` |
| `list_create` | Create a new named list | `list_name` |

#### 4.4.12 Notification & Alert System

The notification system is the **proactive delivery mechanism** — the system initiates communication with the user rather than responding to a request. All notifications flow through a central queue with priority-based delivery.

**Notification Sources:**
- Timer completion (Scheduling Service)
- Reminder trigger (Scheduling Service)
- Smart home alerts (IoT layer — motion detected, door opened, device offline)
- Approval request timeouts (Agent Framework)
- System health alerts (HAL Health Service — low battery, thermal throttle, service failure)

**Priority Model (5 levels):**

| Priority | Delivery Channels | Behavior | Examples |
|---|---|---|---|
| **P0 — Silent** | LCD badge only | No audio, no interruption. Small icon/counter on idle screen. | Completed background tasks, low-priority HA events |
| **P1 — Visual** | LCD notification card + LED amber pulse | No audio. Card auto-dismisses after 10s. | Weather alerts, non-urgent reminders |
| **P2 — Chime** | LCD + LED + short audio tone | Brief audible alert. Does NOT interrupt active conversation. | Timer complete, approval timeout warning |
| **P3 — Spoken** | LCD + LED + TTS announcement | System speaks the notification. Waits for active conversation to finish before delivering. | Scheduled reminders, important HA alerts |
| **P4 — Interruptive** | LCD + LED + TTS (interrupts everything) | Immediately interrupts any activity including active conversation. | Critical system alerts, security events, smoke detector |

**Queueing & Delivery:**
- During active voice session: P0-P3 notifications are queued. Delivered in priority order after session ends (idle timeout or farewell).
- P4 notifications always delivered immediately, regardless of session state.
- Web UI sessions receive all notifications via WebSocket push. Browser Notification API used for P2+ when tab is not focused.

**Do Not Disturb (DND):**
- Configurable quiet hours (e.g., 22:00-07:00).
- During DND: P0-P2 silently queued. P3 downgraded to P1 (visual only). P4 still interrupts (safety-critical).
- DND toggled by voice ("quiet mode on/off"), web UI, or schedule in config.

**LCD Notification Display:**

| Display State | Notification Behavior |
|---|---|
| Idle + no notifications | Normal idle screen (clock, battery, wifi) |
| Idle + pending P0 | Small badge icon in top-right corner with count |
| Idle + pending P1+ | Notification card overlays idle screen, auto-dismiss after 10s |
| Active conversation + notification arrives | Badge appears in corner, notification queued |
| P4 arrives during conversation | Full-screen alert, conversation paused |

#### 4.4.13 External Services Integration

**Design Insight:** Push-to-talk voice interaction is fundamentally the same interaction pattern as messaging. When a user presses a button and says "What's on my calendar today?" or "Send Sarah a message", they expect the assistant to have those capabilities — just as they would in a messaging-based assistant. A voice assistant without calendar, messaging, email, and task capabilities is significantly less useful than one that has them.

**Architecture:** Each external service is a thin adapter implementing a Python `Protocol` interface (same pattern as the Model Provider Layer, §4.3.1). All services are config-driven, default disabled, with API keys stored in `.env`. When a service is disabled, the corresponding cognitive tools and action templates are hidden from agent prompts (zero token cost).

**Calendar Integration:**

| Feature | Implementation | Permission |
|---|---|---|
| Read calendar | `calendar_query` cognitive tool (§4.4.6) with CalDAV/Google/MCP backend | Tier 0 |
| Create event | `calendar_create` action template | Tier 1 |
| Update event | `calendar_update` action template | Tier 2 |
| Delete event | `calendar_delete` action template | Tier 2 |

Protocol options:
- **CalDAV** (default): Standard protocol. Works with Radicale (self-hosted, ~5MB), Nextcloud, iCloud, Google Calendar (via CalDAV bridge). Privacy-preserving when self-hosted.
- **Google Calendar API**: Direct API access for richer features (shared calendars, reminders). Requires Google Cloud credentials.
- **MCP**: If a calendar MCP server is already configured (e.g., HA calendar), `calendar_query` routes through MCP client automatically.

Typical use cases:
- "What's on my calendar today?" → `calendar_query` → lists events
- "Schedule a dentist appointment for Thursday at 2pm" → `calendar_create` → confirmation
- "Move my 3pm meeting to 4pm" → `calendar_update` (Tier 2 — approval required)

**Messaging / Notification Relay:**

For sending messages or alerts to the user's mobile when not at the Pi:

| Provider | Type | Requirements |
|---|---|---|
| **ntfy** | Self-hosted push notifications | ntfy server (or ntfy.sh cloud), mobile app |
| **Pushover** | Cloud push notifications | Pushover account, API key in `.env` |
| **Matrix** | Federated messaging | Matrix account, homeserver URL |

- `notification_send_external` action template (Tier 1)
- "Send a message to my phone" → push notification via configured provider
- "Remind me on my phone when the timer is done" → schedule + relay
- External notifications are a delivery channel for the existing notification system (§4.4.12) — any P1+ notification can optionally be relayed externally

**Email:**

| Feature | Implementation | Permission |
|---|---|---|
| Read inbox | `email_query` cognitive tool — check for new/matching emails via IMAP | Tier 0 |
| Send email | `email_send` action template — compose and send via SMTP | Tier 2 (approval required) |

- "Do I have any new emails?" → IMAP check → summarize subjects/senders
- "Send an email to Sarah about the meeting" → compose → approval prompt → SMTP send
- Email credentials in `.env` (IMAP password, SMTP password). IMAP connection uses SSL/TLS.
- Email send is Tier 2 because sending messages on behalf of the user is a non-trivial action.

**Task Sync (Optional):**

| Provider | Protocol | Use Case |
|---|---|---|
| CalDAV VTODO | CalDAV | Self-hosted task management (same server as calendar) |
| Todoist | REST API | Popular cloud task manager |

- `task_sync` action template: Tier 1 (create), Tier 2 (delete)
- "Add milk to my shopping list" → if external sync enabled, creates task in Todoist/CalDAV AND updates local list
- Local lists (§4.4.11 Scheduling Service) always work offline; external sync is additive

**Service Adapter Protocol:**
```python
class ExternalServiceAdapter(Protocol):
    """Provider-agnostic external service interface."""
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health_check(self) -> bool: ...
    @property
    def service_type(self) -> str: ...  # "calendar", "messaging", "email", "tasks"
```

Concrete implementations: `CalDAVCalendarAdapter`, `NtfyMessagingAdapter`, `IMAPEmailAdapter`, etc.

**Phase Mapping:**
- Phase 2: Read-only integration — `calendar_query` with CalDAV backend, `email_query` with IMAP
- Phase 3: Write operations — `calendar_create`, `notification_send_external`, `email_send`
- Phase 5: Full bidirectional sync — `task_sync`, recurring calendar sync, external notification relay for all priority levels

#### 4.4.14 A2A Protocol Support

Cortex supports the [Agent2Agent (A2A) protocol](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/) as both **client** and **server**, complementing MCP (§4.4.8). Where MCP provides tool/data access, A2A provides **agent-to-agent task delegation** — the ability for agents to discover each other, negotiate capabilities, and delegate entire tasks.

**Why both MCP and A2A:**

| Protocol | Purpose | Cortex Example |
|---|---|---|
| **MCP** | Tool/data access | Cortex calls HA's `get_light_state` tool |
| **A2A** | Agent task delegation | Cortex delegates "research this topic and summarize" to a more capable agent on the network |

A2A is particularly valuable for Cortex because the local 1.7B model has inherent capability limits. Rather than always falling back to a cloud LLM API (which is just raw inference), A2A allows delegating to a full *agent* running on a more powerful machine — with its own tools, memory, and reasoning loop.

**A2A Client — Delegate to External Agents (Phase 2):**
- Discover external agents via Agent Cards (JSON metadata at `/.well-known/agent.json`)
- Agent Cards describe: agent name, capabilities (skills), supported protocols, authentication requirements
- Orchestrator can delegate tasks to external agents when local capability is insufficient
- Task lifecycle: create → monitor progress → receive streaming or final result
- External agent results fed back into super agent context as tool-call responses

**A2A Server — Expose Cortex Agents (Phase 3):**
- Cortex publishes an Agent Card at `/.well-known/agent.json` on the FastAPI server
- Each super agent maps to an A2A "skill" in the Agent Card
- External AI clients (Claude Desktop, other agents, automation scripts) can discover Cortex's capabilities and delegate tasks
- All incoming A2A tasks go through the permission engine (Tier 2 by default, configurable)
- Task execution logged in audit system

**Transport:** JSON-RPC over HTTP/SSE — same FastAPI infrastructure as MCP server. No additional port.

**Python SDK:** `python-a2a` package (maintained under Linux Foundation governance).

**A2A Server Configuration:**
```yaml
# In cortex.yaml
agent:
  a2a:
    client:
      enabled: false  # Enable in Phase 2
      discovery_urls: []  # URLs to check for Agent Cards
      connect_timeout: 5
      default_permission_tier: 2
    server:
      enabled: false  # Enable in Phase 3
      expose_agents: [general, home, research, pim, planner]
```

#### 4.4.15 Proactive Intelligence Engine

Traditional voice assistants are entirely reactive — they respond only when spoken to. The Proactive Intelligence Engine enables Cortex to **initiate** useful interactions based on learned patterns, time-of-day context, and event correlations.

**Pattern Detection Sources:**

| Source | Signal | Example |
|---|---|---|
| Episodic memory | Repeated time-based actions | User checks weather every morning at 7:15 AM |
| Scheduling service | Upcoming reminders + calendar | Meeting in 30 minutes + traffic conditions |
| Smart home events | Sensor triggers + context | Doorbell rang + user has "expect package" reminder |
| Health monitoring | System state changes | Battery dropping below threshold while user is away |

**Proactive Interaction Types:**

| Type | Description | Delivery |
|---|---|---|
| **Morning briefing** | Weather, calendar summary, reminders for the day | P1-P2 notification at learned wakeup time |
| **Context correlation** | Connect related events across sources | P2-P3 notification: "Your package may have arrived — the doorbell rang" |
| **Routine suggestion** | Suggest automating detected patterns | P1 notification: "You check the weather every morning. Want me to include it in your briefing?" |
| **Anticipatory reminder** | Proactively remind based on calendar context | P2 notification: "You have a meeting in 30 minutes" |

**Implementation:**
- Scheduled "think" loop: runs every 5 minutes during idle time (no active voice session)
- Single short LLM inference using `quick` profile (Qwen3-0.6B) — minimal NPU cost when idle
- Queries episodic memory for recent patterns, checks upcoming calendar/reminders/timers
- Output: ranked notification candidates, delivered via existing notification system (§4.4.12)
- Notifications respect DND, priority levels, and conversation-aware queueing

**User Control:**
- Fully opt-in: disabled by default in config
- Morning briefing: configurable contents (weather, calendar, reminders, smart home summary)
- Routine suggestions: minimum occurrence threshold before suggesting (default 5 repetitions)
- Per-routine enable/disable via web UI
- "Stop telling me about [X]" — disables that specific proactive trigger

**Privacy:** Proactive engine operates entirely locally. Pattern detection uses on-device episodic memory. No data sent to external services for pattern analysis.

---

### 4.5 Security Architecture

**Design Philosophy:** Defense in depth. Assume every component can be compromised. Minimize blast radius.

#### 4.5.1 Tiered Permission Model

```
┌─────────────────────────────────────────────┐
│              PERMISSION TIERS                │
├──────────┬──────────────────────────────────┤
│ TIER 0   │ Always allowed, no approval      │
│ (Safe)   │ Read system info, get time,      │
│          │ general conversation, read files  │
│          │ in designated dirs, query memory  │
├──────────┼──────────────────────────────────┤
│ TIER 1   │ Allowed, logged with audit trail │
│ (Normal) │ Write files in sandbox, HTTP GET  │
│          │ to approved domains, IoT read     │
│          │ state, set timers/reminders       │
├──────────┼──────────────────────────────────┤
│ TIER 2   │ Requires explicit user approval   │
│ (Risky)  │ Shell commands, HTTP POST/PUT,    │
│          │ IoT actuator commands, file       │
│          │ writes outside sandbox, install   │
│          │ new tools, external API calls     │
├──────────┼──────────────────────────────────┤
│ TIER 3   │ Requires confirmation + reason    │
│ (Danger) │ System config changes, network    │
│          │ config, delete data, update       │
│          │ system packages, modify security  │
│          │ policy, create persistent agents  │
└──────────┴──────────────────────────────────┘
```

**Approval Mechanism:**
- Voice: System speaks the action and waits for verbal confirmation.
- Web UI: Modal dialog with action details, approve/deny/modify.
- LCD: Shows action summary, button press to confirm or deny.
- Timeout: If no response within configurable window (default 60s), action is denied.

#### 4.5.2 Sandboxed Execution

- **Tool sandbox:** All dynamically created tools run in isolated environments:
  - Option A: `nsjail` or `bubblewrap` (lightweight Linux sandboxing)
  - Option B: Minimal `podman` containers (heavier but stronger isolation)
  - Recommendation: `bubblewrap` for most tools, `podman` for tools requiring network access
- **Filesystem isolation:** Tools can only access a designated scratch directory.
- **Resource limits:** CPU time, memory, and network bandwidth caps per tool execution.
- **No privilege escalation:** Tools run as unprivileged user with seccomp-bpf profile.

#### 4.5.3 Network Security

- **Default posture:** All outbound connections blocked. System is fully functional offline.
- **Allowlist:** Domains/IPs explicitly approved by user (managed via web UI).
- **Categories:**
  - Smart home: Local network only (mDNS/IP range for IoT devices)
  - Web search: Specific search API endpoints
  - Model providers: Auto-managed based on enabled providers in config (see below)
  - System updates: OS/package repos only
- **Firewall:** `nftables` rules managed by the security service.
- **DNS:** Local DNS resolver with filtering (e.g., `dnscrypt-proxy` or `unbound`).
- **TLS:** All external connections require TLS 1.3. No cleartext HTTP.

**Model Provider Network Gating:**
When a cloud provider is enabled in `config/cortex.yaml` (e.g., `providers.openai.enabled: true`), the security service automatically:
1. Adds the provider's API endpoint to the nftables allowlist (e.g., `api.openai.com`)
2. Logs all provider API calls at **Tier 1** (logged, auto-approved) — the user enabling the provider is the authorization act
3. Removes the allowlist entry when the provider is disabled
4. LAN-only providers (e.g., `ollama` on `192.168.x.x`) are gated by the local network access policy, not the internet allowlist

| Provider | Endpoint Domains |
|---|---|
| `openai` | `api.openai.com` |
| `anthropic` | `api.anthropic.com` |
| `google` | `generativelanguage.googleapis.com` |
| `xai` | `api.x.ai` |
| `ollama` | User-configured LAN IP (no internet required) |
| `openai_compatible` | User-configured URL |

#### 4.5.4 Data Protection

- **Encryption at rest:** All persistent data (memory DB, configs, audit logs) encrypted via LUKS or application-level encryption (libsodium/age).
- **Secrets management:** API keys for cloud providers stored in `.env` file (gitignored), loaded via `pydantic-settings`. Keys encrypted at rest on the device. Never stored in YAML config files.
- **No telemetry:** Zero data leaves the device unless user explicitly initiates an action or enables a cloud provider.
- **Cloud data privacy:** Each provider config supports an `allow_sensitive_data` flag (default: `false`). When false, the Model Provider Layer strips memory context, personal information, and conversation history before sending requests to cloud APIs. Local NPU provider has no such restriction.
- **Secure boot:** Leverage AX8850 hardware security module (AES/SHA-256) where possible.

#### 4.5.5 Audit System

Every action is logged with:
- Timestamp (from PiSugar RTC for reliability)
- Action type and parameters
- Permission tier triggered
- Approval status (auto-approved, user-approved, denied, timed-out)
- Execution result (success/failure/error)
- Source (voice command, web UI, scheduled task, agent-initiated)

**Model provider calls** additionally log:
- Provider ID and model name
- Token count (input/output)
- Latency (ms)
- For cloud providers: endpoint domain, request size in bytes

Logs stored in append-only format. Queryable via web UI. Exportable as JSON/CSV.

---

### 4.6 User Interfaces

#### 4.6.1 Voice Interface (Physical Pi — Primary)

- **Button-driven interaction** — all input through the single Whisplay button (GPIO 11). No always-on microphone, no VAD.
- **Hold to talk** — audio captured only while button is held. Sent to ASR on release. Zero false activations, zero privacy concerns.
- **Double-click for vision** — captures image from USB camera and sends to VLM for analysis. Response spoken via TTS.
- Audio feedback: confirmation tones, status sounds, spoken responses via Whisplay speaker.
- Interrupt support: long press (>2s) interrupts TTS playback or cancels current operation.
- Multi-turn conversation with context retention (sliding window).
- **Approval via button** — Tier 2/3 approval requests announced via TTS and shown on LCD. Single click = approve, long press = deny.
- Vision also available via voice: "What am I looking at?" while holding button triggers camera + VLM after ASR processes the request.

#### 4.6.2 Web Interface

**Technology:** FastAPI + HTMX + Alpine.js (or lightweight Svelte). Deferred to Phase 3 (DD-013).

**Design Principle — Full Parity with Physical Pi:**
Every capability available on the physical Pi must also be available through the Web UI. The Web UI is the remote equivalent of the Whisplay HAT — same voice, vision, and approval capabilities, different input mechanisms.

| Physical Pi (Whisplay) | Web UI Equivalent |
|---|---|
| Hold button → push-to-talk | Click "Record" button (hold-to-talk or click-start/click-stop) |
| Double-click → camera capture | Click "Camera" button (browser webcam via getUserMedia) or drag-and-drop image upload |
| Single click → approve action | Click "Approve" button on action approval card |
| Long press → deny action | Click "Deny" button on action approval card |
| LCD display → status/response | Chat window with streaming text + status bar |
| Speaker → TTS audio | Browser audio playback via Web Audio API |
| RGB LED → status colors | Visual status indicator (colored dot/ring) in UI header |

**Pages/Features:**
- **Chat** — Full conversation interface with streaming responses. Includes:
  - **Record button** — hold-to-talk (mirrors physical Whisplay button) or click-to-start/click-to-stop. No VAD — user controls recording boundaries explicitly. Visual waveform during recording.
  - **Camera button** — captures frame from browser webcam (getUserMedia API) and sends to VLM. Falls back to file upload if no webcam available.
  - **Image upload** — drag-and-drop or file picker for sending images to VLM.
  - **Text input** — standard text box, bypasses voice pipeline.
  - **Approval cards** — inline Approve/Deny buttons for Tier 2/3 actions, with action description and countdown timer.
- **Dashboard** — System health (NPU temp/load, CPU, memory, battery, network), active agents, recent actions.
- **Tool Manager** — Browse, enable/disable, create, edit, and delete tools.
- **Agent Manager** — Create, configure, and monitor agents.
- **Memory Browser** — Search and manage all memory stores.
- **Security Console** — Permission tier config, network allowlist, audit log viewer.
- **Settings** — Model selection, voice settings, power management, display preferences.

**Access Control:**
- Web UI only accessible on local network.
- Authentication required (local password or PIN).
- Optional: mTLS for additional security.
- Session timeout after inactivity.

#### 4.6.3 LCD Display Interface

**Implementation:** Adapted from PiSugar whisplay-ai-chatbot display subsystem. Python-based renderer using Pillow + cairosvg for SVG emoji, running a 30 FPS render loop with SPI output at 100 MHz to the ST7789 controller.

**Architecture:**
- Cortex services send display state via ZeroMQ (replacing the reference project's TCP socket)
- Python render thread composes frames using Pillow (ImageDraw + ImageFont)
- SVG emoji rendered via cairosvg for high-quality icons at any size
- RGB565 conversion via NumPy, sent to ST7789 over SPI
- Button events sent back to Cortex via ZeroMQ
- Line-level image caching for performance; LANCZOS resampling for all images

**Display Modes:**
- **Idle:** Clock, battery level, WiFi status, ambient LED color.
- **Listening:** Animated waveform showing mic is active (button held).
- **Thinking:** Processing animation with task description.
- **Speaking:** Scrolling text of response with smooth pixel-level scroll.
- **Capturing:** Camera viewfinder flash / "Analyzing image..." animation (double-click triggered).
- **Alert:** Full-screen notification for Tier 2/3 approval requests. Shows action description and "Press = Approve / Hold = Deny" prompt.

**Button Hardware:**
Single button on GPIO 11 (active low, 50ms debounce). All interaction through gesture recognition on this one button, matching the whisplay-ai-chatbot physical design.

**Button Gesture Map:**

| Gesture | Detection | Function | Display → | LED |
|---|---|---|---|---|
| **Hold** (press > 300ms) | Press-and-hold duration | **Push-to-talk**: record audio while held, send to ASR on release | Idle → Listening → Thinking | Green while held |
| **Double-click** (2 presses < 400ms) | Inter-press timing | **Camera capture**: take photo via USB camera, send to VLM for analysis | Idle → Capturing → Thinking | White flash → Orange |
| **Single click** (press < 300ms, no second press within 400ms) | Delayed release (wait for possible double) | **Confirm / approve**: approve Tier 2/3 pending action; in idle mode, repeat last response | Alert → Thinking | Green flash |
| **Long press** (press > 2s) | Hold duration threshold | **Cancel / deny**: deny Tier 2/3 pending action; in non-idle mode, interrupt current operation | Alert → Idle, Speaking → Idle | Red flash |
| **Triple-click** (3 presses < 600ms) | Inter-press timing | **System menu**: cycle through status screens (system info, memory, active agents) | Idle → Status cycle | Blue pulse |

**Gesture Detection Notes:**
- Single-click has a 400ms delay before firing (to distinguish from double-click). This is acceptable since single-click is for confirmations, not time-critical voice input.
- Hold (push-to-talk) fires immediately on press — no delay. Audio capture begins at button-down, not button-up.
- Gestures are context-aware: in Alert mode, single click = approve and long press = deny. In Idle mode, single click = repeat last response.
- Debounce: 50ms minimum between state changes (matches whisplay-ai-chatbot).
- All gestures recognized by the Display Service in HAL and published as structured events on ZeroMQ.

**RGB LED States:**
- Dim blue (#000055): Idle / sleep
- Green (#00ff00): Listening (button held — recording)
- White (#ffffff): Camera flash (brief 200ms pulse on capture)
- Orange (#ff6800): Processing / thinking
- Blue (#0000ff): Speaking / answering
- Red (#ff0000): Alert — approval required (slow pulse)
- Red flash: Action denied / cancelled
- Green flash: Action approved
- Smooth 20-step color fading between states
- Amber pulse (#ffaa00): Notification pending (new, added by notification system)

#### 4.6.4 Voice Interaction Lifecycle

Defines the complete user-facing experience from session start to end, including interruptions, error recovery, confirmations, and capability discovery. This bridges the hardware pipeline (§4.2) with the user-facing interface.

**Session Management:**

```
First button press ──→ SESSION START
       │
  Conversation turns ──→ Active session (working memory accumulates)
       │
  Idle timeout (5 min) ─┐
  or explicit farewell ──┤──→ SESSION END
       │                 │     ├── Memory extraction triggered (DD-028)
       │                 │     └── Display returns to Idle
       │                 │
  [No explicit "start"   [Farewell: "goodbye", "that's all",
   needed — first press    "thanks I'm done" — regex-matched,
   begins session]         zero LLM cost]
```

- Session starts implicitly on first button press after idle. No explicit command needed.
- Session ends on configurable idle timeout (default 5 min, aligns with `memory.extraction.idle_timeout`) or explicit farewell patterns.
- One active voice session at a time on the physical Pi. Web UI can have concurrent sessions per authenticated user.
- Session state tracked in working memory: conversation history, rolling summary, active task state, pending approvals.

**Interruption Handling:**

| Scenario | Trigger | Behavior | Display/LED |
|---|---|---|---|
| User long-presses during TTS playback (>2s) | Long press | Stop audio immediately, cancel TTS queue, discard remaining response. No spoken feedback — the interruption IS the intent. | Speaking → Idle, LED red flash |
| User holds button during TTS (new push-to-talk) | Hold > 300ms | Stop TTS playback, transition to Listening. New utterance replaces current response. Interrupted response still added to conversation history but **marked as truncated** — system knows what was actually heard vs. what was planned (per LiveKit speech truncation pattern). | Speaking → Listening, LED green |
| User long-presses during LLM generation (no audio yet) | Long press > 2s | Cancel in-flight LLM call. Brief feedback: "Cancelled." or a cancel tone. Return to Idle. | Thinking → Idle, LED red flash |

**Error Recovery:**

| Error Condition | User Hears/Sees | System Behavior |
|---|---|---|
| ASR returns empty or low-confidence | "I didn't catch that. Could you try again?" | Log ASR failure, stay in session, re-enter Listening on next button press |
| ASR returns gibberish (confidence < threshold) | "I'm not sure I understood that. Could you say it differently?" | Same as above. LCD shows transcribed text for visual verification. |
| LLM generation fails | "I'm having trouble thinking right now. Let me try again." | Retry once with same prompt. If still fails, try fallback provider (DD-022). If all fail, apologize and suggest trying again later. |
| LLM returns empty/incoherent | "I'm not sure how to respond to that. Could you rephrase?" | Log, stay in session. |
| TTS synthesis fails | Response displayed as text on LCD (silent fallback) | Log TTS error. System remains functional — all responses are visual-only until TTS recovers. |
| Tool execution fails | "I couldn't [action] — [reason]." e.g., "I couldn't turn off the lights — the device isn't responding." | Specific error explanation spoken. Action logged as failed in audit. |
| NPU thermal throttle (sustained >30s) | "I need to cool down for a moment." | Pause inference, wait for temperature to drop. See §4.1.1 thermal zones. |
| NPU crash | "Something went wrong. Give me a moment." | Attempt NPU service restart via systemd. If fails, switch to cloud fallback if available. |

**Confirmation Feedback Patterns:**

All state-changing actions produce explicit spoken or displayed confirmation so the user knows what happened:

| Action Type | Confirmation | Example |
|---|---|---|
| Timer set | Spoken confirmation with details | "Timer set for 10 minutes." |
| Reminder set | Spoken + LCD notification | "I'll remind you to call Mom at 3 PM." |
| Device controlled | Spoken confirmation | "Kitchen lights turned off." |
| Information query | Answer IS the confirmation | (No separate confirmation needed) |
| Memory stored | Brief acknowledgment | "Got it, I'll remember that." |
| Approval granted | Spoken + LED green flash | "Approved. Running now." |
| Approval denied | Spoken + LED red flash | "Cancelled." |
| Action failed | Spoken error + reason | "I couldn't turn off the lights — the device isn't responding." |

**Capability Discovery:**

"What can you do?" / "Help" triggers a pre-defined capability summary, NOT an LLM-generated response (zero LLM cost). The summary is served from versioned templates stored in `config/prompts/capabilities.yaml` with per-persona variants:

- **Primary User:** Full capability list including admin features, tool creation, agent management.
- **Household Member:** Simplified list — questions, timers, reminders, smart home, lists.
- **Guest:** Restricted list — questions, time, weather, basic conversation only.

**System Prompt Persona Guidelines:**

The system prompt defines Cortex's conversational personality. These are the design constraints that all system prompt template versions must follow (actual prompt text is authored separately in `config/prompts/`):

| Guideline | Specification |
|---|---|
| **Name** | "Cortex" (user-configurable in config) |
| **Personality** | Helpful, concise, slightly warm but not overly chatty |
| **Brevity** | Voice responses: 1-3 sentences (~50 tokens). Web UI text: can be longer. |
| **Uncertainty** | Acknowledge: "I'm not certain, but..." — never fabricate or hallucinate. |
| **Humor** | Light and occasional, never forced. No jokes unless contextually appropriate. |
| **Formality** | Casual but not slangy. A knowledgeable friend, not a corporate assistant. |
| **Error tone** | Brief and apologetic: "Sorry, I couldn't do that" not "I sincerely apologize for the inconvenience." |
| **Memory references** | Natural integration: "You mentioned last week that..." not "According to my long-term memory store..." |
| **Tool transparency** | Tell the user what you're doing: "Let me check..." / "Setting that up now..." |
| **Response length** | Adapted per interface: voice responses target <50 tokens, web UI can be longer. Controlled by `reasoning.max_tokens` per interface. |

System prompt templates stored in `config/prompts/` directory, versioned (v1, v2, ...), referenced by `reasoning.system_prompt_version` in config. Each version contains:
- **Base persona** (shared across all contexts)
- **Agent-specific addendum** (per super agent YAML `system_prompt` field)
- **Per-persona privacy constraints** (Guest mode strips memory references and adds "Do not reference personal information about the household")

#### 4.6.5 Conversational Clarification & Repair

A 1.7B model will misunderstand intent more often than a 70B model. Having a structured clarification strategy is *more* important on constrained hardware, not less.

**Confidence-Gated Routing:**
When the orchestrator's classification confidence is below threshold (configurable, default 0.6), it does NOT silently route to the best-guess agent. Instead, it requests clarification: "I think you want to [X]. Is that right?" This prevents silent misrouting — the most frustrating failure mode for users.

**Slot Filling:**
When an action template has required parameters that the LLM could not extract from the user's utterance, the system asks specifically for the missing information rather than failing or guessing:
- "Which light?" (missing `entity_id`)
- "For how long?" (missing `duration`)
- "What time?" (missing `fires_at`)
- Slot-filling prompts use the `quick` model profile (Qwen3-0.6B) for minimal latency.

**Disambiguation:**
When multiple agents or entities match the user's request, offer options rather than guessing:
- "Did you mean the kitchen lights or the living room lights?"
- "I found both a timer and a reminder. Which do you want to check?"
- Maximum 3 options offered (configurable). If more than 3 match, ask a narrowing question instead.

**Escalating Repair Ladder:**
When the system cannot understand the user's intent after an initial attempt:

| Round | Strategy | Example |
|---|---|---|
| 1 | Rephrase / restate understanding | "I think you're asking about [X]. Is that right?" |
| 2 | Offer specific options | "I can help with A, B, or C. Which one?" |
| 3 (max) | Open acknowledgment | "I'm having trouble understanding. Could you say it differently?" |

Maximum clarification rounds per user turn: 2 (configurable via `clarification.max_rounds`). After max rounds, apologize and suggest the web UI for complex requests.

**Sentiment-Aware Adaptation:**
The system prompt includes instructions to detect frustration cues in the user's text (zero model cost — no separate sentiment model):
- If the user repeats a request verbatim, be more concise and offer direct options
- If the user's language becomes terse or includes frustration markers ("I said...", "no, not that"), skip verbose explanations and get to the point
- Never match frustration with frustration — remain calm and helpful

**Future (Phase 3+):** Simple audio feature extraction (pitch variance, speech rate, volume) on CPU during ASR as additional signal. These prosodic features correlate with urgency/frustration and can be passed as context to the LLM. Not a separate model — just NumPy analysis of the raw audio buffer.

---

### 4.7 Smart Home / IoT Integration

**Approach:** Plugin-based, protocol-agnostic.

| Phase | Protocol | Use Cases |
|---|---|---|
| Phase 1 | **MQTT** | Most IoT devices, Home Assistant bridge |
| Phase 1 | **HTTP/REST** | Smart plugs, custom devices, webhooks |
| Phase 2 | **Home Assistant API** | Full HA integration |
| Phase 3 | **Matter/Thread** | Native modern smart home protocol |
| Phase 3 | **Bluetooth LE** | Proximity-based triggers, beacons |
| Phase 5 | **Wyoming** | Local voice satellite protocol for Home Assistant (STT/TTS provider, optional satellite) |

#### 4.7.1 Wyoming Protocol Bridge

Cortex can participate in the Home Assistant voice ecosystem via the [Wyoming protocol](https://www.home-assistant.io/integrations/wyoming/) — the de facto standard for local voice satellite integration.

**Three operating modes:**

| Mode | Description | Data Flow |
|---|---|---|
| **STT Provider** | Expose SenseVoice as a Wyoming speech-to-text service | HA sends audio → Cortex ASR on NPU → returns text to HA |
| **TTS Provider** | Expose Kokoro as a Wyoming text-to-speech service | HA sends text → Cortex TTS on NPU → returns audio to HA |
| **Satellite (optional)** | Cortex acts as a Wyoming voice satellite | HA orchestrates Assist pipeline; Cortex provides mic/speaker I/O + optional local ASR/TTS |

**Implementation:**
- Uses the Python `wyoming` package (maintained by Home Assistant team)
- STT and TTS providers run as separate TCP listeners on configurable ports (default 10300/10200)
- Optional systemd service (`cortex-wyoming.service`), can be enabled/disabled independently
- Wyoming protocol is JSONL over TCP — minimal overhead, no additional dependencies
- In STT/TTS provider modes, Cortex's NPU-accelerated models replace HA's default Whisper/Piper, providing faster inference on the same network

**Relationship to Cortex's own voice pipeline:** Wyoming services share the same NPU models (SenseVoice, Kokoro) but operate independently of Cortex's voice pipeline. When Cortex is actively in a voice conversation, Wyoming requests are queued or rejected (NPU is busy). When Cortex is idle, Wyoming requests are served immediately. This allows Cortex to be both an independent voice assistant AND a high-performance voice service for the broader HA ecosystem.

---

## 5. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| OS | Debian 12 (Bookworm) | Best AXCL driver support |
| Language | Python 3.11+ | AXCL bindings, ML ecosystem |
| NPU Runtime | AXCL (C/Python) | Official M5Stack SDK |
| Model Providers | Provider Protocol abstraction layer | 7 providers: axcl (NPU), openai, anthropic, google, xai, ollama, openai_compatible. Per-profile routing with fallback chains. |
| ASR | sherpa-onnx + AXCL (default) | Proven on LLM8850; cloud ASR available via provider layer |
| LLM | AXCL native (default) | Qwen3-1.7B with Hermes tool calling; cloud/remote LLMs via provider layer |
| TTS | AXCL native + ONNX hybrid (default) | Kokoro-82M v1.0; cloud TTS available via provider layer |
| Agent Framework | Custom 3-tier + Tool Adapter | LangGraph-inspired graph-of-functions; tool calling format auto-adapted per provider |
| Action Engine | Custom Python (YAML templates + handlers) | Zero RAM overhead; replaces n8n/Node-RED for deterministic action execution |
| Tool Protocol | MCP (Python `mcp` SDK) | Standard tool interop; client (consume HA, n8n, etc.) + server (expose Cortex tools) |
| Web Framework | FastAPI + Uvicorn | Async, streaming support |
| Web Frontend | HTMX + Alpine.js | Minimal JS, server-driven |
| Embeddings | all-MiniLM-L6-v2 (ONNX on CPU) | 22MB, 384-dim, ~10-20ms/embed; semantic search for memory retrieval |
| Database | SQLite + sqlite-vec | Lightweight, vector search (brute-force KNN, sufficient for <50K entries) |
| Message Bus | ZeroMQ | Fast IPC, no broker |
| Sandboxing | bubblewrap | Lightweight namespace isolation |
| Firewall | nftables | Modern, kernel-level |
| Audio | ALSA + PipeWire | WM8960 driver support |
| Display | Pillow + cairosvg + SPI | Adapted from whisplay-ai-chatbot; 30 FPS render loop, SVG emoji, RGB565 via NumPy |
| Power | pisugar-power-manager | Official PiSugar daemon |
| Process Mgmt | systemd | Service orchestration |
| Agent Interop | A2A Protocol (Python `python-a2a` SDK) | Google A2A v0.3 for agent-to-agent delegation; client (discover/delegate) + server (expose Cortex agents) |
| Voice Satellite | Wyoming Protocol (Python `wyoming` package) | HA standard for local voice satellites; expose SenseVoice STT + Kokoro TTS to Home Assistant |
| Calendar | CalDAV / Google Calendar API | Standard calendar protocol; Radicale (self-hosted) or Google API or HA MCP |
| Messaging | ntfy / Pushover / Matrix | Lightweight push notifications to mobile; self-hosted or cloud options |

---

## 6. Phased Implementation Plan

### Phase 0 — Foundation (Weeks 1-2)
- OS installation and hardening
- AXCL driver and NPU verification
- Whisplay HAT driver and hardware tests
- PiSugar 3 Plus integration
- HAL services as systemd units
- Bus conflict verification
- **Investigation:** Speculative decoding — test if AXCL supports Qwen3-0.6B draft + Qwen3-1.7B verify pattern
- **Investigation:** Constrained generation — test if AXCL supports grammar-guided decoding for structured tool call output
- **Investigation:** Moonshine ASR — evaluate Moonshine Tiny (26MB) for streaming partial transcription during button hold
- **Investigation:** Unified multimodal — test Qwen3-VL-2B (7.80 tok/s, 3.7 GB) tool-calling accuracy as unified LLM+VLM replacement

### Phase 1 — Voice Loop (Weeks 3-5)
- Button activation (GPIO 11 hold-to-talk) on Pi
- ASR (SenseVoice) on NPU
- LLM (Qwen3-1.7B) on NPU — basic chat
- TTS (Kokoro-82M) on NPU
- End-to-end voice conversation
- Streaming voice pipeline (sentence detector, TTS queue, crossfade)
- Voice interaction lifecycle (session management, interruption handling, error recovery)
- Button gesture recognition, LCD status display
- System prompt persona v1 (`config/prompts/system_v1.txt`)
- Latency metric collection (TTFA, ASR, prefill, chunk, inter-chunk)
- Power-aware operation profiles — design and basic mains/battery detection (DD-040)
- NPU Service Protocol abstraction — hardware-agnostic interface, AXCL implementation (DD-041)

### Phase 2 — Agent Core (Weeks 6-9)
- Tool calling (Hermes templates)
- Built-in tool set + utility cognitive tools (clock, calculator, unit_convert, dictionary_lookup)
- Permission engine (4-tier)
- Approval flows (voice, LCD, web)
- Audit logging
- Conversation memory
- Sandboxed execution
- Scheduling service (timers, reminders) with SQLite persistence
- Notification system (5 priority levels, LCD integration, DND)
- List management (shopping lists, todo lists)
- Health monitoring service and `/api/health` endpoint
- Conversational clarification & repair — confidence gating, slot filling, disambiguation (DD-034)
- External services: read-only — CalDAV calendar_query backend, IMAP email_query (DD-035)
- A2A protocol client — discover and delegate to external agents (DD-036)
- Power profile auto-switching based on PiSugar charging state (DD-040)

### Phase 3 — Web UI (Weeks 10-12)
- FastAPI backend + WebSocket streaming
- Chat, dashboard, tool/agent managers
- Security console
- Authentication
- Settings
- Notification center in web UI
- WebSocket notification push + browser notifications (P2+)
- External services: write operations — calendar_create, notification_send_external, email_send (DD-035)
- A2A protocol server — Agent Card, expose Cortex agents to external clients (DD-036)
- Document upload UI for knowledge store (DD-039)

### Phase 4 — Dynamic Capabilities (Weeks 13-16)
- Tool development pipeline (specify → develop → review → approve → deploy)
- Agent factory (dynamic super agent creation)
- Long-term memory with embeddings
- Tool promotion system (Tier 2 → Tier 1 → Tier 0 after supervised use)
- Power management profiles (DD-040 — full implementation)
- Network security hardening
- Knowledge store & document RAG backend — chunking, embedding, retrieval (DD-039)
- Proactive intelligence engine — pattern detection design (DD-038)

### Phase 5 — IoT & Automation (Weeks 17-20)
- MQTT client
- Device registry
- Natural language device control
- Home Assistant API
- LLM-generated automations
- Smart home alert routing through notification system
- Weather API integration (`weather_query` cognitive tool)
- Wyoming protocol bridge — STT/TTS provider, optional satellite mode (DD-037)
- External services: full bidirectional sync, task_sync (DD-035)
- Proactive intelligence engine — implementation (DD-038)

### Phase 6 — Hardening & Polish (Weeks 21-24)
- Security audit
- Encrypted storage
- Secrets management
- Performance optimization
- Error recovery and graceful degradation testing (fault injection)
- Hardware watchdog tuning and thermal policy validation
- Documentation

---

## 7. Open Questions & Risks

### Open Questions
1. ~~Wake word engine?~~ Resolved — removed entirely (DD-025). Button-only activation.
2. NPU model hot-swapping latency?
3. External USB SSD for storage?
4. Custom 3D-printed enclosure?

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| NPU memory too tight for 3 models | Voice pipeline breaks | Profile early; smaller models; sequential loading |
| Qwen3-1.7B insufficient for complex tasks | Poor tool calling | Structured prompts, constrained generation, cloud fallback |
| Power budget exceeds PiSugar capacity | System brownout | Aggressive power gating; mains power for inference |
| AXCL ecosystem immaturity | Missing features | Pin versions; abstract NPU backend |
| Sandbox overhead on Pi 5 | Latency increase | bubblewrap is near-zero overhead |
| I2C conflicts (Whisplay + PiSugar) | Hardware malfunction | Disable PiSugar AUTO switch |
| External service availability (CalDAV, IMAP, ntfy) | PIM features degraded | All external services optional, graceful degradation, local-only mode always works |
| A2A protocol maturity (v0.3) | Breaking changes | Pin SDK version; A2A is additive, core functionality independent |
| Hailo/AXCL divergence | NPU lock-in | NPU Service Protocol abstraction (DD-041) isolates implementation |

---

## 8. Success Criteria

- Time-to-first-audio < 5 seconds for typical voice queries (streaming pipeline)
- Fully offline core voice assistant
- Dynamic tool creation end-to-end
- All Tier 2/3 actions require explicit approval
- Full audit trail
- Stable 24+ hour operation
- Battery: 1+ hour active / 4+ hours idle
- Timer/reminder delivery within 1 second of scheduled time
- Health endpoint responds within 100ms
- System auto-recovers from service crash within 10 seconds (systemd restart)
- All error states produce user-friendly feedback (never raw errors via voice or LCD)
- Clarification triggers when orchestrator confidence < threshold (never silent misrouting)
- Calendar query returns results within 2 seconds for local CalDAV
- External notification delivery (ntfy/Pushover) within 5 seconds of trigger
- Knowledge store retrieval adds < 50ms to prompt construction latency
- Power profile transitions within 5 seconds of charging state change
- NPU Service Protocol has zero AXCL-specific type imports at the interface level
- Wyoming STT/TTS services pass Home Assistant compatibility tests

---

## 9. Design Decisions Log

| ID | Decision | Date | Rationale |
|---|---|---|---|
| DD-001 | Python as primary language | 2026-02-27 | AXCL Python bindings, ML ecosystem, rapid prototyping |
| DD-002 | Local-first with optional external access | 2026-02-27 | Privacy-first while maintaining flexibility |
| DD-003 | Tiered autonomy (4-tier permissions) | 2026-02-27 | Safe actions auto, risky actions need approval |
| DD-004 | General-purpose assistant focus | 2026-02-27 | Avoids premature domain-specific optimization |
| DD-005 | Qwen3-1.7B as primary model | 2026-02-27 | Confirmed: 7.38 tok/s, 3.3 GB CMM, 4K context on M.2 + Pi 5. Best balance of speed, memory, and capability. Qwen3-4B rejected (3.65 tok/s, 6.2 GB CMM, fills NPU, see DD-029). Native Hermes tool calling. |
| DD-011 | Kokoro-82M as TTS engine (replacing MeloTTS) | 2026-02-27 | 2x faster on NPU (RTF 0.067 vs 0.125), #1 HuggingFace TTS Arena quality, 54 voices, 237MB NPU vs 800MB estimated for MeloTTS, actively maintained, already proven on LLM-8850 |
| DD-012 | Adapt whisplay-ai-chatbot for LCD display | 2026-02-27 | Proven 30 FPS Pillow+cairosvg renderer on this exact hardware; SVG emoji, smooth scrolling, LED fading; adapt and extend rather than rewrite |
| DD-013 | Defer web UI framework decision to Phase 3 | 2026-02-27 | Web UI is secondary to voice interface; evaluate HTMX+DaisyUI vs NiceGUI vs Svelte when implementation begins |
| DD-014 | Custom Python action engine | 2026-02-27 | Zero RAM overhead, in-process, YAML templates + Python handlers; all external engines (n8n 200-860MB, Node-RED 40-80MB, Temporal 2-4GB, Windmill 2-3GB) too heavy for Pi 5 |
| DD-015 | 3-tier agent hierarchy | 2026-02-27 | Orchestrator (classifier, ~370 tok) → Super Agents (reasoning, 4K context) → Utility Agents (deterministic, 0 LLM tokens); optimized for 1.7B model at 15 tok/s |
| DD-016 | Unconstrained thinking, constrained acting | 2026-02-27 | Agents reason freely with cognitive tools (read-only); world-changing actions go through pre-authorized YAML templates with permission gating and audit logging |
| DD-017 | Qwen-Agent as library only | 2026-02-27 | NousFnCallPrompt for Qwen3-native tool-call parsing; full frameworks rejected (see DD-018) |
| DD-018 | Custom framework over CrewAI/LangGraph/AutoGen | 2026-02-27 | CrewAI: 32GB RAM, ChromaDB dep; AutoGen: conversation paradigm fills 4K in 2-3 exchanges; LangGraph: closest but langchain-core bloat for ~500 LOC of graph execution; smolagents: prompt bloat; Swarm: deprecated |
| DD-019 | MCP protocol support (client + server) | 2026-02-27 | Standard tool interop via Python `mcp` SDK; client discovers external tools (HA, n8n) and maps to cognitive tools or action templates with permission gating; server exposes Cortex tools to external AI clients via Streamable HTTP on FastAPI |
| DD-020 | Tiered VLM vision system | 2026-02-27 | SmolVLM2-500M always resident (~500MB) for quick image descriptions; hot-swap to InternVL3-1B or Qwen2.5-VL-3B for detailed analysis (unloads LLM temporarily). Three input sources: USB camera (physical), webcam (web UI), image upload (web UI). |
| DD-021 | Button-first interaction with Web UI parity | 2026-02-27 | Physical Pi uses Whisplay button (GPIO 11) as sole input — hold=push-to-talk, double-click=camera capture, single-click=approve, long-press=deny/cancel, triple-click=system menu. No VAD anywhere (eliminates false activations and privacy concerns). Web UI provides full parity via software equivalents (record button, webcam/upload, approve/deny buttons). |
| DD-022 | Configurable model provider layer | 2026-02-27 | All model interactions (LLM, ASR, TTS, VLM) routed through provider-agnostic Protocol interfaces. Seven provider types: axcl (local NPU), openai, anthropic, google, xai, ollama, openai_compatible. Per-profile provider chains with automatic fallback and circuit breaker. Tool calling format adapted transparently per provider via Tool Adapter. Context budgets scale dynamically with provider context window. API keys in .env, cloud calls auto-gated by security layer. Default config is fully offline (axcl only) — cloud/remote providers are opt-in. |
| DD-023 | SenseVoice-Small as primary ASR engine | 2026-02-27 | Non-autoregressive architecture gives 10-20x lower latency than Whisper-Small on AX8850 NPU (~50-75ms vs ~800-1800ms per utterance). English WER comparable (~3-4% vs 3.4%). Same NPU memory (~500MB). Single axmodel vs Whisper's 3 (faster load/swap). 5 languages vs 99+ (sufficient for primary use). Faster Whisper rejected (CPU-only, can't use NPU). Both SenseVoice and Whisper-Small to be tested in Phase 0 for final confirmation. |
| DD-024 | CSI camera via libcamera/picamera2 | 2026-02-27 | Freenove/Raspberry Pi camera modules use CSI connector, not USB. picamera2 is the standard Python interface on Raspberry Pi OS. |
| DD-025 | No wake word — button-only activation | 2026-02-27 | With button-first interaction (DD-021) and no VAD, wake word serves no purpose. Removed entirely rather than deferred. Simplifies system — no always-on mic, no background audio processing, no power drain from continuous listening. |
| DD-026 | Provider-managed context — no central Context Manager | 2026-02-27 | Each provider knows its own context window limits. The agent framework passes full conversation to the provider; the provider handles truncation if needed. Eliminates artificial token budget scaling that was over-engineering for the multi-provider design (DD-022). Local NPU still effectively limited by 4K practical window; cloud providers use their natural capacity. |
| DD-027 | Tool Development Pipeline | 2026-02-27 | Structured lifecycle for tool creation: Specify (requirements YAML) → Develop (LLM-generated or human-written code) → Review (static analysis, sandbox test, security scan) → Approve (Tier 3 human approval) → Deploy (registered in tool registry). Tools remain in "draft" state until approved. Unapproved tools can be tested in sandbox but cannot affect real systems. |
| DD-028 | Conversation context assembly and memory system | 2026-02-27 | Context Assembler builds prompts in priority order: system prompt → current request → tools → auto-injected memories → rolling summary → recent turns → older history. Rolling summary (generated during TTS playback, hidden latency) maintains coherence on 4K local NPU. Six memory tiers (DD-039 added Knowledge Store): working (RAM, session), short-term (SQLite, conversation summaries), long-term (SQLite + sqlite-vec, atomic facts with embeddings), episodic (events), tool (filesystem). Post-session LLM extraction captures facts/events. Automatic semantic retrieval injects relevant memories into every prompt (~20-40ms, CPU-only embedding via all-MiniLM-L6-v2). Cloud providers get full history + memories; local NPU gets summary + recent turns + memories. Memory stripped from cloud calls unless `allow_sensitive_data` enabled. |
| DD-029 | Qwen3-1.7B confirmed as primary LLM (4B rejected) | 2026-02-27 | Confirmed benchmarks on M.2 + Pi 5: Qwen3-1.7B uses 3.3 GB CMM at 7.38 tok/s (4K context). Qwen3-4B uses 6.2 GB CMM at 3.65 tok/s (2,559 max tokens) — only 691 MB remaining, cannot co-reside with ANY other model. Qwen3-4B is not viable as primary (half the speed, less context, requires serial model swapping for every ASR/TTS call). Qwen3-4B noted as future hot-swap option for heavy local reasoning (requires Pulsar2 v4.2, not yet released). AXERA-TECH catalog (148 models) provides additional options: Qwen3-VL-4B-GPTQ-Int4 as combined LLM+VLM hot-swap, DeepSeek-R1-Distill-Qwen-1.5B as alternative reasoning model. |
| DD-030 | Voice interaction lifecycle | 2026-03-01 | Complete user-facing interaction model. Session auto-starts on first button press, ends on 5-min idle or explicit farewell (regex-matched, zero LLM cost). Interruption: long-press stops TTS immediately, new push-to-talk interrupts and replaces (interrupted response marked as truncated in history — system tracks what was actually heard vs planned). ASR errors get spoken retry prompts, LLM failures retry then fallback to cloud, TTS failures fall back to LCD text. All state-changing actions get spoken confirmations. "What can you do?" served from pre-defined per-persona templates (zero LLM cost). System prompt persona "Cortex": concise, warm, honest about uncertainty, voice responses <50 tokens. Prompt templates versioned in `config/prompts/`. |
| DD-031 | Streaming voice pipeline | 2026-03-01 | Sentence-boundary streaming TTS to achieve <5s time-to-first-audio despite 7.38 tok/s LLM speed. Sentence Detector buffers LLM tokens, flushes on sentence-ending punctuation (min 8, max 96 tokens matching Kokoro axmodel limit). TTS Queue synthesizes each sentence via Kokoro as it arrives (~200ms per short sentence at RTF 0.067). LLM and TTS co-resident on NPU — model multiplexing enables parallel generation and synthesis (Phase 0 verification required). Audio chunks played sequentially with 10ms crossfade. Metrics: TTFA, ASR latency, prefill latency, chunk latency, inter-chunk gap. Falls back to sequential mode if NPU multiplexing proves too slow. |
| DD-032 | Utility tools, scheduling, and notification system | 2026-03-01 | 9 new cognitive tools: clock, timer_query, reminder_query, weather_query, calculator, unit_convert, dictionary_lookup, translate, list_query (pure Python where possible, zero LLM cost). 7 new action templates: timer_set/cancel, reminder_set/cancel, list CRUD (all Tier 1). Scheduling Service: SQLite-backed persistent timers and reminders (`data/schedules.db`), survives reboots, asyncio-based sub-second precision, reminder snooze (max 3). Notification system: 5 priority levels (P0 silent LCD badge → P4 interruptive TTS), delivery via LCD + LED + audio + TTS + web push. Notifications queued during active conversations (except P4). DND mode with quiet hours (P3→P1 during DND, P4 always delivers). |
| DD-033 | System resilience and health monitoring | 2026-03-01 | HAL-level health monitoring service: NPU temp/CMM, CPU, RAM, storage, battery, network, systemd units — published on ZeroMQ bus. `GET /api/health` endpoint returns component status (healthy/degraded/critical), loaded models, uptime. Four-zone NPU thermal policy: normal (<65°C), warm (65-75°C log), throttle (75-85°C reduce speed), shutdown (>85°C emergency unload). systemd watchdog (30s heartbeat, auto-restart, max 3 in 5min). Graceful degradation matrix: NPU overheat → cool-down pause, all LLM fail → rule-based regex commands only, TTS fail → LCD text fallback, ASR fail → web UI text only, low battery → power saving → clean shutdown. Error UX: never raw errors to user, always human-readable, LCD always shows something even in catastrophic failure. |
| DD-034 | Conversational clarification & repair | 2026-03-02 | Confidence-gated orchestrator responses: when classification confidence < threshold (default 0.6), ask "I think you want to [X]. Is that right?" instead of silently misrouting. Slot filling for missing action template parameters ("Which light?", "For how long?"). Disambiguation when multiple matches ("Kitchen or living room lights?"). Escalating repair ladder: rephrase → offer options → "Could you say it differently?" All clarification uses `quick` profile (Qwen3-0.6B) for minimal latency. Text-based sentiment awareness in system prompt (zero model cost): detect frustration cues, respond more concisely. Max 2 clarification rounds per user turn (configurable). |
| DD-035 | External services integration (PIM) | 2026-03-02 | PTT voice interaction is fundamentally the same interaction pattern as messaging — users expect calendar, messaging, email, and task management. Calendar: CalDAV protocol (Radicale self-hosted, Google Calendar API, or HA calendar MCP); `calendar_query` cognitive tool gets real backend; new action templates `calendar_create` (Tier 1), `calendar_update`/`calendar_delete` (Tier 2). Messaging relay: ntfy (self-hosted), Pushover, or Matrix for push notifications to mobile. Email: IMAP read via `email_query` cognitive tool (Tier 0), SMTP send via `email_send` action template (Tier 2 — approval required). Task sync: CalDAV VTODO or Todoist API (optional). Service Adapter Protocol (Python `Protocol` class, same pattern as Model Provider Layer). All services config-driven, default disabled, API keys in `.env`. New super agent: `pim` (personal information management). Phase 2 (read), Phase 3 (write), Phase 5 (full bidirectional sync). |
| DD-036 | A2A protocol support | 2026-03-02 | Google Agent2Agent protocol (v0.3, Linux Foundation, 150+ organizations). Complementary to MCP: MCP = tool/data access, A2A = agent-to-agent task delegation. Client (Phase 2): discover external agents via Agent Cards (JSON metadata), delegate tasks exceeding 1.7B capacity to more capable remote agents. Server (Phase 3): expose Cortex super agents as discoverable A2A agents, Agent Card at `/.well-known/agent.json`. JSON-RPC over HTTP/SSE — same FastAPI infrastructure as MCP server. Python `python-a2a` SDK. All incoming A2A tasks go through permission engine (Tier 2 by default). |
| DD-037 | Wyoming protocol bridge | 2026-03-02 | Home Assistant's standard protocol for local voice satellites (JSONL over TCP). Cortex exposes SenseVoice as a Wyoming STT provider and Kokoro as a Wyoming TTS provider, enabling HA to use Cortex's NPU for voice processing. Optional satellite mode: HA orchestrates the Assist pipeline, Cortex provides audio I/O + local ASR/TTS. Python `wyoming` package (HA-maintained). Runs as optional systemd service alongside Cortex. Phase 5 alongside existing HA integration. |
| DD-038 | Proactive intelligence engine | 2026-03-02 | System initiates interactions based on learned patterns rather than waiting for user input. Pattern detection from episodic memory + scheduling service + calendar. Time-of-day routines: morning briefing at learned wakeup time. Context-aware correlations: smart home events + reminders + calendar. Routine suggestions: "You check the weather every morning. Want me to include it automatically?" Scheduled idle-time "think" loop: single short LLM inference using `quick` profile (Qwen3-0.6B), zero cost when NPU is idle. Delivery via existing notification system (P1-P3 depending on urgency). Fully opt-in, configurable per-routine via web UI. Phase 4 (design), Phase 5 (implementation). |
| DD-039 | Knowledge store & document RAG | 2026-03-02 | Sixth memory tier: ingested documents (manuals, references, personal notes, saved articles) chunked into ~200-token overlapping segments, embedded via same all-MiniLM-L6-v2 CPU pipeline, stored in sqlite-vec. `knowledge_search` cognitive tool (already defined) gets this as its real backend. With 4K context, RAG is MORE valuable than with large context windows — inject one high-relevance passage instead of hoping it fits. Ingestion: web UI upload or watched directory (`data/knowledge/`). Supported formats: txt, md, pdf, html. Capacity: configurable (default 100 documents). Phase 4. |
| DD-040 | Power-aware operation profiles | 2026-03-02 | Four profiles: `mains` (full capability — Qwen3-1.7B, full polling, full brightness), `battery` (reduced — Qwen3-0.6B, half polling frequency, 50% brightness), `low_battery` (<15% — minimal polling, 30% brightness), `critical` (<5% — regex-only commands, no LLM inference, LCD text only). Auto-transition via Power Service ZeroMQ events based on PiSugar charging state. Model Router already supports profile switching (§4.3.5). Manual override via voice command. Phase 1 (design), Phase 2 (auto-switching implementation). |
| DD-041 | NPU hardware abstraction | 2026-03-02 | NPU Service Protocol defined as Python `Protocol` class: `load_model`, `unload_model`, `infer`, `get_status`, `capabilities`. No AXCL-specific types at the interface level — all AXCL specifics isolated inside `AxclNpuService` implementation. Generic numpy array I/O for tensors. Enables future `HailoNpuService` (Raspberry Pi AI HAT+ 2, Hailo-10H, 40 TOPS, 2.5W) and `MockNpuService` (testing) without changing any higher-layer code. Design discipline enforced from Phase 1 when writing the NPU Service. |

*Document version: 0.1.12 — External services (PIM), A2A/Wyoming protocols, conversational clarification, proactive intelligence, knowledge store, power profiles, NPU abstraction*
*Status: DRAFT*
