# Project Cortex — Agentic Local LLM Voice Assistant
## System Design Scope Document v0.1

---

## 1. Vision Statement

A fully local, privacy-first, voice-and-web AI assistant running on a Raspberry Pi 5 with NPU acceleration. The system operates autonomously for safe tasks, requests approval for risky operations, can dynamically create its own tools and agents, integrates with smart home/IoT devices, and maintains comprehensive audit trails — all while keeping data local by default with optional secure external access.

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
│   Wake Word → VAD → ASR → [LLM] → TTS → Speaker        │
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

**Key Design Decisions:**
- All HAL services run as systemd units with dedicated service accounts (no root).
- Hardware access controlled via udev rules and Linux capability sets.
- HAL exposes a unified event bus (e.g., ZeroMQ or D-Bus) for hardware events (button press, low battery, NPU thermal throttle).

---

### 4.2 Voice Pipeline

**Purpose:** Real-time voice interaction loop, fully local.

**Pipeline Stages:**

```
[Always-on]     [On activation]
Mic → VAD ──→ ASR ──→ Intent/LLM ──→ TTS ──→ Speaker
       │                                        │
  Wake Word                                  LCD Update
  or Button
```

**Model Allocation on NPU (8GB budget):**

| Model | Purpose | Est. NPU Memory | Est. Performance |
|---|---|---|---|
| Whisper-small or SenseVoice | ASR (Speech-to-Text) | ~500MB | RTF < 0.1 (faster than real-time) |
| Qwen3-1.7B (w8a16) | Reasoning / conversation | ~3.5GB | ~12-15 tok/s |
| Kokoro-82M (v1.0, axmodel) | TTS (Text-to-Speech) | ~237MB | RTF 0.067 (15x real-time) |
| Silero VAD | Voice Activity Detection | ~5MB | Real-time on Pi CPU |
| Wake word (custom/Porcupine) | Always-on trigger | ~10MB | Real-time on Pi CPU |
| **Total estimated** | | **~4.25GB** | Leaves ~3.5GB headroom |

**Activation Modes:**
1. **Push-to-talk** — Whisplay button held down, immediate ASR activation.
2. **Wake word** — Always-on lightweight detector on Pi CPU, NPU wakes for ASR.
3. **Web UI** — Text input bypasses voice pipeline entirely.

**Latency Budget (voice round-trip target: < 3 seconds):**
- VAD + ASR: < 500ms for typical utterance
- LLM inference (50-token response @ 15 tok/s): ~3.3s
- TTS synthesis: < 500ms (with streaming, first audio < 200ms)
- **Stretch goal:** Stream TTS while LLM is still generating (sentence-level chunking via Kokoro's native generator pipeline).

**NPU Memory Management Strategy:**
- Models can be hot-swapped. ASR loads → runs → partially unloads during LLM inference.
- Alternatively, keep all three resident if memory allows (~4.25GB fits in 8GB with ~3.5GB headroom).
- Kokoro uses a hybrid pipeline: 3 axmodel parts on NPU + ONNX vocoder on CPU, reducing NPU memory pressure.
- Monitor via NPU Service; degrade gracefully (e.g., smaller ASR model) if memory pressure detected.

---

### 4.3 Reasoning Core

**Purpose:** The "brain" — language understanding, planning, tool dispatch.

**Primary Model:** Qwen3-1.7B (w8a16 quantization on AX8850)
- Native Hermes-style tool calling support
- Thinking/non-thinking mode switching (thinking for complex tasks, non-thinking for quick responses)
- 32K native context window

**Model Router:**
The system should support multiple model profiles for different task types:

| Profile | Model | Use Case | Mode |
|---|---|---|---|
| `chat` | Qwen3-1.7B | General conversation | Non-thinking |
| `reason` | Qwen3-1.7B | Complex planning, multi-step tasks | Thinking |
| `code` | Qwen3-1.7B | Tool/agent code generation | Thinking |
| `quick` | Qwen3-0.6B | Simple commands, slot filling | Non-thinking |
| `vision` | InternVL3-1B | Image understanding (if camera attached) | — |
| `fallback` | Cloud API (optional) | Tasks beyond local capability | — |

**Prompt Management:**
- System prompts stored as versioned templates.
- Dynamic tool schema injection — only currently relevant tools are included in context.
- Conversation history managed with sliding window + summarization to stay within context limits.
- Persona/behavior configurable via web UI.

---

### 4.4 Agent Framework

**Purpose:** Enable the LLM to plan, use tools, and create new tools/agents dynamically.

#### 4.4.1 Core Architecture

```
┌──────────────────────────────────────────┐
│              AGENT RUNTIME               │
│                                          │
│  ┌──────────┐  ┌──────────────────────┐  │
│  │ Planner  │  │   Execution Engine   │  │
│  │          │──│                      │  │
│  │ Decomposes  │  Runs tool calls     │  │
│  │ tasks into  │  sequentially or     │  │
│  │ steps       │  with dependencies   │  │
│  └──────────┘  └──────────────────────┘  │
│        │                │                │
│  ┌─────┴────┐    ┌──────┴───────┐        │
│  │  Memory   │    │Tool Registry │        │
│  │  Manager  │    │             │        │
│  │           │    │ Built-in    │        │
│  │ Short-term│    │ Dynamic     │        │
│  │ Long-term │    │ External    │        │
│  │ Episodic  │    │             │        │
│  └──────────┘    └─────────────┘        │
└──────────────────────────────────────────┘
```

#### 4.4.2 Tool System

**Built-in Tools (ship with the system):**
- `file_read`, `file_write`, `file_list` — Local filesystem operations (sandboxed)
- `shell_exec` — Execute shell commands (sandboxed, high-risk, requires approval)
- `http_request` — Make HTTP requests (governed by network policy)
- `timer_set`, `reminder_create` — Scheduling and reminders
- `system_info` — Query system status (battery, CPU, NPU, memory, network)
- `knowledge_store` — CRUD operations on local vector/document store
- `smart_home` — IoT device control (see §4.7)
- `notification` — Send alerts via display, LED, speaker, or push notification

**Dynamic Tool Creation:**
The LLM can generate new tools at runtime:
1. LLM generates a Python function with docstring, type hints, and JSON schema.
2. Security layer validates the code (static analysis, no forbidden imports/syscalls).
3. Tool is registered in a sandboxed execution environment.
4. Tool persists across sessions if approved by user.
5. Tools are versioned and can be rolled back.

**Agent Factory:**
For complex, multi-step workflows, the system can spawn sub-agents:
- Each agent has a defined goal, tool subset, and context window.
- Agents can be persistent (e.g., "morning briefing agent") or ephemeral.
- Agent definitions are stored as YAML/JSON configs.
- User can create, modify, and delete agents via voice or web UI.

#### 4.4.3 Memory System

| Type | Storage | Purpose | Retention |
|---|---|---|---|
| **Working Memory** | RAM | Current conversation context | Session |
| **Short-term Memory** | SQLite | Recent conversations, task results | 30 days (configurable) |
| **Long-term Memory** | SQLite + embeddings | Key facts, user preferences, learned patterns | Persistent |
| **Episodic Memory** | SQLite | Significant events, decisions, outcomes | Persistent |
| **Tool Memory** | Filesystem | Generated tools, agent configs | Persistent |

- All memory encrypted at rest (see §4.5).
- Embedding-based retrieval for long-term memory (small embedding model on NPU or CPU).
- User can inspect, edit, and delete any memory via web UI.

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

- **Default posture:** All outbound connections blocked.
- **Allowlist:** Domains/IPs explicitly approved by user (managed via web UI).
- **Categories:**
  - Smart home: Local network only (mDNS/IP range for IoT devices)
  - Web search: Specific search API endpoints
  - Cloud LLM fallback: Specific provider API endpoints
  - System updates: OS/package repos only
- **Firewall:** `nftables` rules managed by the security service.
- **DNS:** Local DNS resolver with filtering (e.g., `dnscrypt-proxy` or `unbound`).
- **TLS:** All external connections require TLS 1.3. No cleartext HTTP.

#### 4.5.4 Data Protection

- **Encryption at rest:** All persistent data (memory DB, configs, audit logs) encrypted via LUKS or application-level encryption (libsodium/age).
- **Secrets management:** API keys, tokens stored in encrypted keyring, never in plaintext config.
- **No telemetry:** Zero data leaves the device unless user explicitly initiates an action.
- **Secure boot:** Leverage AX8850 hardware security module (AES/SHA-256) where possible.

#### 4.5.5 Audit System

Every action is logged with:
- Timestamp (from PiSugar RTC for reliability)
- Action type and parameters
- Permission tier triggered
- Approval status (auto-approved, user-approved, denied, timed-out)
- Execution result (success/failure/error)
- Source (voice command, web UI, scheduled task, agent-initiated)

Logs stored in append-only format. Queryable via web UI. Exportable as JSON/CSV.

---

### 4.6 User Interfaces

#### 4.6.1 Voice Interface (Primary)

- Natural conversational interaction via Whisplay mic/speaker.
- Audio feedback: confirmation tones, status sounds, spoken responses.
- Interrupt support: user can interrupt TTS playback to issue new command.
- Multi-turn conversation with context retention.
- Voice-based approval for Tier 2/3 actions.

#### 4.6.2 Web Interface

**Technology:** FastAPI + HTMX + Alpine.js (or lightweight Svelte).

**Pages/Features:**
- **Chat** — Full text-based conversation interface with streaming responses.
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
- **Listening:** Animated waveform showing mic is active.
- **Thinking:** Processing animation with task description.
- **Speaking:** Scrolling text of response with smooth pixel-level scroll.
- **Alert:** Full-screen notification for Tier 2/3 approval requests.

**Button Mapping:**
- Single press: Push-to-talk / confirm action
- Double press: Cancel / deny action
- Long press: Cycle display mode / enter settings

**RGB LED States:**
- Blue (#000055): Idle / sleep
- Green (#00ff00): Listening
- Orange (#ff6800): Processing / thinking
- Blue (#0000ff): Speaking / answering
- Red: Alert / approval required
- Smooth 20-step color fading between states

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

---

## 5. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| OS | Debian 12 (Bookworm) | Best AXCL driver support |
| Language | Python 3.11+ | AXCL bindings, ML ecosystem |
| NPU Runtime | AXCL (C/Python) | Official M5Stack SDK |
| ASR | sherpa-onnx + AXCL | Proven on LLM8850 |
| LLM | AXCL native | Qwen3-1.7B with Hermes tool calling |
| TTS | AXCL native + ONNX (hybrid) | Kokoro-82M v1.0 (3 axmodel NPU + ONNX vocoder CPU) |
| Agent Framework | Custom (inspired by Qwen-Agent) | Tight hardware integration needed |
| Web Framework | FastAPI + Uvicorn | Async, streaming support |
| Web Frontend | HTMX + Alpine.js | Minimal JS, server-driven |
| Database | SQLite + sqlite-vec | Lightweight, vector search |
| Message Bus | ZeroMQ | Fast IPC, no broker |
| Sandboxing | bubblewrap | Lightweight namespace isolation |
| Firewall | nftables | Modern, kernel-level |
| Audio | ALSA + PipeWire | WM8960 driver support |
| Display | Pillow + cairosvg + SPI | Adapted from whisplay-ai-chatbot; 30 FPS render loop, SVG emoji, RGB565 via NumPy |
| Power | pisugar-power-manager | Official PiSugar daemon |
| Process Mgmt | systemd | Service orchestration |

---

## 6. Phased Implementation Plan

### Phase 0 — Foundation (Weeks 1-2)
- OS installation and hardening
- AXCL driver and NPU verification
- Whisplay HAT driver and hardware tests
- PiSugar 3 Plus integration
- HAL services as systemd units
- Bus conflict verification

### Phase 1 — Voice Loop (Weeks 3-5)
- VAD (Silero) on Pi CPU
- ASR (SenseVoice/Whisper) on NPU
- LLM (Qwen3-1.7B) on NPU — basic chat
- TTS (MeloTTS) on NPU
- End-to-end voice conversation
- Push-to-talk, LCD status display
- Latency profiling

### Phase 2 — Agent Core (Weeks 6-9)
- Tool calling (Hermes templates)
- Built-in tool set
- Permission engine (4-tier)
- Approval flows (voice, LCD, web)
- Audit logging
- Conversation memory
- Sandboxed execution

### Phase 3 — Web UI (Weeks 10-12)
- FastAPI backend + WebSocket streaming
- Chat, dashboard, tool/agent managers
- Security console
- Authentication
- Settings

### Phase 4 — Dynamic Capabilities (Weeks 13-16)
- Dynamic tool creation
- Agent factory
- Long-term memory with embeddings
- Wake word detection
- Power management profiles
- Network security hardening

### Phase 5 — IoT & Automation (Weeks 17-20)
- MQTT client
- Device registry
- Natural language device control
- Home Assistant API
- LLM-generated automations

### Phase 6 — Hardening & Polish (Weeks 21-24)
- Security audit
- Encrypted storage
- Secrets management
- Performance optimization
- Error recovery
- Documentation

---

## 7. Open Questions & Risks

### Open Questions
1. Wake word engine: Porcupine vs OpenWakeWord vs custom?
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

---

## 8. Success Criteria

- Voice round-trip < 4 seconds for simple queries
- Fully offline core voice assistant
- Dynamic tool creation end-to-end
- All Tier 2/3 actions require explicit approval
- Full audit trail
- Stable 24+ hour operation
- Battery: 1+ hour active / 4+ hours idle

---

## 9. Design Decisions Log

| ID | Decision | Date | Rationale |
|---|---|---|---|
| DD-001 | Python as primary language | 2026-02-27 | AXCL Python bindings, ML ecosystem, rapid prototyping |
| DD-002 | Local-first with optional external access | 2026-02-27 | Privacy-first while maintaining flexibility |
| DD-003 | Tiered autonomy (4-tier permissions) | 2026-02-27 | Safe actions auto, risky actions need approval |
| DD-004 | General-purpose assistant focus | 2026-02-27 | Avoids premature domain-specific optimization |
| DD-005 | Qwen3-1.7B as primary model | 2026-02-27 | Best balance of capability and NPU performance; native tool calling |
| DD-011 | Kokoro-82M as TTS engine (replacing MeloTTS) | 2026-02-27 | 2x faster on NPU (RTF 0.067 vs 0.125), #1 HuggingFace TTS Arena quality, 54 voices, 237MB NPU vs 800MB estimated for MeloTTS, actively maintained, already proven on LLM-8850 |
| DD-012 | Adapt whisplay-ai-chatbot for LCD display | 2026-02-27 | Proven 30 FPS Pillow+cairosvg renderer on this exact hardware; SVG emoji, smooth scrolling, LED fading; adapt and extend rather than rewrite |
| DD-013 | Defer web UI framework decision to Phase 3 | 2026-02-27 | Web UI is secondary to voice interface; evaluate HTMX+DaisyUI vs NiceGUI vs Svelte when implementation begins |

*Document version: 0.1.2 — LCD display approach, web UI deferred*
*Status: DRAFT*
