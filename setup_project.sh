#!/usr/bin/env bash
# =============================================================================
# Project Cortex — Bootstrap Script
# Creates project directory structure and populates initial documentation
# 
# Usage: bash setup_project.sh
# =============================================================================

set -euo pipefail

BASE="/Users/andrew.graydon/Documents/Code/Python/Cortex"

echo "🧠 Project Cortex — Setting up project structure..."
echo "   Base directory: $BASE"
echo ""

# --- Directory Structure ---
dirs=(
    "docs/design"
    "docs/guides"
    "docs/architecture"
    "docs/decisions"
    "docs/runbooks"
    "context"
    "src/cortex/hal"
    "src/cortex/voice"
    "src/cortex/reasoning"
    "src/cortex/agent"
    "src/cortex/agent/tools/builtin"
    "src/cortex/agent/tools/dynamic"
    "src/cortex/agent/agents"
    "src/cortex/security"
    "src/cortex/memory"
    "src/cortex/web/api"
    "src/cortex/web/frontend"
    "src/cortex/display"
    "src/cortex/iot"
    "src/cortex/utils"
    "tests/unit"
    "tests/integration"
    "tests/hardware"
    "config"
    "scripts"
    "models"
    "data/memory"
    "data/audit"
    "data/tools"
    "data/agents"
)

for d in "${dirs[@]}"; do
    mkdir -p "$BASE/$d"
done

echo "✅ Directory structure created"

# =============================================================================
# DOCUMENT: Project README
# =============================================================================
cat > "$BASE/README.md" << 'DOCEOF'
# Project Cortex

**Agentic Local LLM Voice Assistant**

A fully local, privacy-first, voice-and-web AI assistant running on a Raspberry Pi 5 with M5Stack LLM-8850 NPU acceleration. The system operates autonomously for safe tasks, requests approval for risky operations, can dynamically create its own tools and agents, and maintains comprehensive audit trails — all while keeping data local by default with optional secure external access.

## Hardware Platform

| Component | Role |
|---|---|
| Raspberry Pi 5 (8GB) | Host orchestrator |
| M5Stack LLM-8850 (AX8850) | NPU inference (24 TOPS, 8GB) |
| PiSugar Whisplay HAT | Voice I/O, LCD, buttons, LEDs |
| PiSugar 3 Plus | Battery / UPS |

## Architecture

Seven-layer stack:
1. **HAL** — Hardware abstraction (NPU, audio, display, power)
2. **Voice Pipeline** — Wake word → VAD → ASR → LLM → TTS → Speaker
3. **Reasoning Core** — Qwen3-1.7B with tool calling
4. **Agent Framework** — Planning, tools, dynamic agent creation
5. **Security Layer** — 4-tier permissions, sandboxing, audit
6. **Web UI** — FastAPI + HTMX dashboard and chat
7. **Display UI** — Whisplay LCD status and interaction

## Project Structure

```
Cortex/
├── docs/              # All documentation
│   ├── design/        # Scope, architecture documents
│   ├── guides/        # Setup and operational guides
│   ├── architecture/  # Detailed layer specifications
│   ├── decisions/     # Architecture Decision Records (ADRs)
│   └── runbooks/      # Operational procedures
├── context/           # AI assistant context files for continuity
├── src/cortex/        # Main application source
│   ├── hal/           # Hardware Abstraction Layer
│   ├── voice/         # Voice pipeline (VAD, ASR, TTS)
│   ├── reasoning/     # LLM core, model router, prompt management
│   ├── agent/         # Agent framework, tools, memory
│   ├── security/      # Permissions, sandbox, audit, crypto
│   ├── memory/        # Memory management (short/long-term)
│   ├── web/           # Web UI (FastAPI backend + frontend)
│   ├── display/       # Whisplay LCD interface
│   ├── iot/           # Smart home / IoT integrations
│   └── utils/         # Shared utilities
├── tests/             # Test suites
├── config/            # Configuration files
├── scripts/           # Utility and deployment scripts
├── models/            # Local model storage (gitignored)
└── data/              # Runtime data (gitignored)
```

## Status

- **Current Phase:** Phase 0 — Hardware Foundation
- **Implementation Language:** Python 3.11+
- **Primary LLM:** Qwen3-1.7B (on NPU)
- **Target OS:** Debian 12 (Bookworm) / Raspberry Pi OS

## Documentation

- [Scope Document](docs/design/scope-v0.1.md)
- [Phase 0 Setup Guide](docs/guides/phase-0-hardware-setup.md)
- [Project Context](context/project-context.md)
DOCEOF

echo "✅ README.md"

# =============================================================================
# DOCUMENT: Scope Document v0.1
# =============================================================================
cat > "$BASE/docs/design/scope-v0.1.md" << 'DOCEOF'
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
| MeloTTS or CosyVoice2 | TTS (Text-to-Speech) | ~800MB | Near real-time |
| Silero VAD | Voice Activity Detection | ~5MB | Real-time on Pi CPU |
| Wake word (custom/Porcupine) | Always-on trigger | ~10MB | Real-time on Pi CPU |
| **Total estimated** | | **~4.8GB** | Leaves ~3GB headroom |

**Activation Modes:**
1. **Push-to-talk** — Whisplay button held down, immediate ASR activation.
2. **Wake word** — Always-on lightweight detector on Pi CPU, NPU wakes for ASR.
3. **Web UI** — Text input bypasses voice pipeline entirely.

**Latency Budget (voice round-trip target: < 3 seconds):**
- VAD + ASR: < 500ms for typical utterance
- LLM inference (50-token response @ 15 tok/s): ~3.3s
- TTS synthesis: < 500ms (with streaming, first audio < 200ms)
- **Stretch goal:** Stream TTS while LLM is still generating (token-by-token TTS).

**NPU Memory Management Strategy:**
- Models can be hot-swapped. ASR loads → runs → partially unloads during LLM inference.
- Alternatively, keep all three resident if memory allows (~4.8GB fits in 8GB).
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

**Display Modes:**
- **Idle:** Clock, battery level, WiFi status, ambient LED color.
- **Listening:** Animated waveform showing mic is active.
- **Thinking:** Processing animation with task description.
- **Speaking:** Scrolling text of response, or avatar animation.
- **Alert:** Full-screen notification for Tier 2/3 approval requests.

**Button Mapping:**
- Single press: Push-to-talk / confirm action
- Double press: Cancel / deny action
- Long press: Cycle display mode / enter settings

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
| TTS | AXCL native | MeloTTS or CosyVoice2 |
| Agent Framework | Custom (inspired by Qwen-Agent) | Tight hardware integration needed |
| Web Framework | FastAPI + Uvicorn | Async, streaming support |
| Web Frontend | HTMX + Alpine.js | Minimal JS, server-driven |
| Database | SQLite + sqlite-vec | Lightweight, vector search |
| Message Bus | ZeroMQ | Fast IPC, no broker |
| Sandboxing | bubblewrap | Lightweight namespace isolation |
| Firewall | nftables | Modern, kernel-level |
| Audio | ALSA + PipeWire | WM8960 driver support |
| Display | Pillow + SPI driver | Direct LCD control |
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

*Document version: 0.1 — Initial scope definition*
*Status: DRAFT*
DOCEOF

echo "✅ docs/design/scope-v0.1.md"

# =============================================================================
# DOCUMENT: Phase 0 Hardware Setup Guide
# =============================================================================
cat > "$BASE/docs/guides/phase-0-hardware-setup.md" << 'DOCEOF'
# Project Cortex — Phase 0: Hardware Foundation Setup Guide

## Goal
Get all hardware assembled, verified, and communicating. Establish the base OS, driver stack, and confirm there are no bus conflicts between components. Profile actual power and memory budgets.

---

## 0.1 Prerequisites & Important Warnings

### Power Architecture (CRITICAL)

```
                  ┌──────────────────────┐
  USB-C PD ──────►│  M5Stack PiHat OR    │──── 3.3V ──►  LLM-8850 NPU
  (27W min)       │  RPi M.2 HAT+       │──── 5V ────►  Raspberry Pi 5
  9V@3A           └──────────────────────┘
                                                │
                                          ┌─────┴─────┐
                                          │ PiSugar 3 │ ◄── UPS / portable
                                          │   Plus    │     mode only
                                          └───────────┘
```

**Rules:**
- **Primary power (mains):** Feed through NPU adapter's USB-C PD (≥27W, 9V@3A).
- **PiSugar 3 Plus:** UPS and portable mode only. NOT for sustained NPU inference.
- **Never power from Pi 5's USB-C when NPU PiHat is connected.**
- Add `PSU_MAX_CURRENT=5000` to `/boot/firmware/config.txt` if powering from non-PD source.

### Checklist Before Starting
- [ ] Raspberry Pi 5 (8GB)
- [ ] M5Stack LLM-8850 card + M.2 adapter (PiHat or RPi HAT+)
- [ ] PCIe FPC ribbon cable
- [ ] PiSugar 3 Plus + battery
- [ ] PiSugar Whisplay HAT
- [ ] microSD card (64GB+, Class A2)
- [ ] USB-C PD power supply (≥27W)
- [ ] Ethernet or WiFi credentials
- [ ] Optional: USB SSD for extended storage

---

## 0.2 OS Installation & Hardening

### Flash OS
Raspberry Pi Imager → **Raspberry Pi OS (64-bit, Debian 12 Bookworm)**

Pre-configure in Imager:
- Hostname: `cortex`
- SSH: Enable (key-based preferred)
- WiFi: Configure if needed
- Locale/timezone: Set correctly

### First Boot (Pi only, no HATs)

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y \
    git curl wget htop tmux vim \
    python3-pip python3-venv python3-dev \
    build-essential cmake \
    i2c-tools spi-tools \
    alsa-utils \
    sqlite3 libsqlite3-dev \
    nftables \
    bubblewrap
sudo reboot
```

### SSH Hardening

```bash
# After confirming key auth works:
sudo nano /etc/ssh/sshd_config
# PermitRootLogin no
# PasswordAuthentication no
# MaxAuthTries 3
sudo systemctl restart sshd
```

### Firewall

```bash
sudo systemctl enable nftables
sudo nft flush ruleset
sudo nft -f - <<'EOF'
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif lo accept
        tcp dport 22 accept
        tcp dport 8080 accept
        tcp dport 8421 accept
        ip protocol icmp accept
        ip6 nexthdr icmpv6 accept
        log prefix "nftables-drop: " drop
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
EOF
sudo nft list ruleset | sudo tee /etc/nftables.conf
```

### Service Account

```bash
sudo useradd -r -s /usr/sbin/nologin -m -d /opt/cortex cortex
sudo usermod -aG i2c,spi,gpio,audio cortex
```

### Enable Interfaces

```bash
sudo raspi-config
# Enable: I2C, SPI, PCIe/M.2
# Verify after reboot:
ls /dev/i2c-*
ls /dev/spidev*
```

---

## 0.3 Assembly & Verification

**⚠️ Power off completely before each hardware change.**

### Order: PiSugar (back) → NPU adapter (PCIe) → Whisplay HAT (GPIO top)

### Verify after power on:

```bash
# I2C devices
sudo i2cdetect -y 1
# Expected: 0x1a (WM8960), 0x57 (PiSugar EEPROM), 0x68 (RTC), 0x75 (PiSugar MCU)

# PCIe
lspci
# Expected: Axera AX8850 or similar
```

---

## 0.4 Drivers

### PiSugar Power Manager

```bash
wget https://cdn.pisugar.com/release/pisugar-power-manager.sh
bash pisugar-power-manager.sh -c release
# Verify: http://cortex.local:8421
# IMPORTANT: Disable AUTO switch to avoid I2C conflicts
```

### Whisplay HAT

```bash
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay/Driver
sudo bash install_wm8960_drive.sh
sudo reboot
# Verify: aplay -l (should show wm8960)
# Test: cd ~/Whisplay/example && sudo bash run_test.sh
```

### AXCL Runtime (NPU)

```bash
sudo wget -qO /etc/apt/keyrings/StackFlow.gpg \
    https://repo.llm.m5stack.com/m5stack-apt-repo/key/StackFlow.gpg
echo 'deb [signed-by=/etc/apt/keyrings/StackFlow.gpg] \
    https://repo.llm.m5stack.com/m5stack-apt-repo axclhost main' | \
    sudo tee /etc/apt/sources.list.d/axclhost.list
sudo apt update
sudo apt install axcl-smi axcl-run
source ~/.bashrc
axcl-smi  # Should show NPU with ~7040 MiB CMM
```

---

## 0.5 Validation Tests

### Test 1: Quick LLM (Qwen3-0.6B)
```bash
cd ~ && mkdir -p models && cd models
git clone https://huggingface.co/M5Stack/Qwen3-0.6B-ax650 --depth 1
# Run and record: tokens/sec, TTFT, NPU memory
```

### Test 2: ASR (SenseVoice)
```bash
git clone https://huggingface.co/M5Stack/SenseVoiceSmall-axmodel --depth 1
# Run with test audio, record: RTF, accuracy, memory
```

### Test 3: Mic → ASR Pipeline
```bash
arecord -D plughw:<CARD>,0 -f S16_LE -r 16000 -c 1 -d 5 test_mic.wav
# Feed to SenseVoice, verify end-to-end
```

### Test 4: Multi-Model Memory Budget (CRITICAL)
```bash
# Monitor: watch -n 1 axcl-smi
# Load SenseVoice → record CMM
# Load Qwen3-1.7B → record CMM
# Load MeloTTS → record CMM
# Can all 3 co-exist? Total < 6.5GB?
```

### Test 5: Battery Under Load
```bash
# Full charge → sustained inference → record drain rate
# Check for under-voltage: dmesg | grep -i voltage
```

### Test 6: I2C Health Under Load
```bash
# During NPU inference: sudo i2cdetect -y 1
# All addresses still visible?
```

---

## 0.6 Completion Checklist

```
HARDWARE VALIDATION
[ ] All components assembled, no bus conflicts
[ ] NPU detected via lspci and axcl-smi
[ ] Whisplay LCD, mic, speaker, buttons, LEDs all working
[ ] PiSugar reports battery and charging state

NPU METRICS (fill in actual values)
Total CMM:           _______ MiB
SenseVoice size:     _______ MiB
Qwen3-1.7B size:     _______ MiB
MeloTTS size:        _______ MiB
All 3 co-resident:   YES / NO (total: _______ MiB)
Qwen3-0.6B tok/s:    _______
Qwen3-1.7B tok/s:    _______
SenseVoice RTF:      _______
NPU idle temp:       _______°C
NPU load temp:       _______°C

POWER METRICS
Battery capacity:    _______ mAh
Active drain:        _______% / min → _______ min runtime
Idle drain:          _______% / min → _______ min runtime
Under-voltage:       YES / NO
Stable under load:   YES / NO

SYSTEM
OS:                  _______
Kernel:              _______
AXCL driver:         _______
Python:              _______
Free disk:           _______ GB
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `lspci` empty | Reseat FPC cable, enable PCIe in raspi-config |
| I2C all `UU` | Disable PiSugar AUTO switch |
| No sound | Specify WM8960 card number explicitly |
| Under-voltage | Use mains power; battery for light tasks |
| NPU > 75°C | Check fan, add ventilation |
| `axcl-smi` not found | `source ~/.bashrc` or re-login |
DOCEOF

echo "✅ docs/guides/phase-0-hardware-setup.md"

# =============================================================================
# DOCUMENT: Project Context (for AI assistant continuity)
# =============================================================================
cat > "$BASE/context/project-context.md" << 'DOCEOF'
# Project Cortex — AI Assistant Context File
# Last updated: 2026-02-27

## Purpose
This file captures the full project context so that design conversations can be resumed across sessions. Feed this file to the AI assistant at the start of a new conversation.

---

## Project Summary
Building an agentic local LLM voice assistant on Raspberry Pi 5 with M5Stack LLM-8850 NPU. Privacy-first, local-first, with optional secure external access.

## Hardware

| Component | Specs | Status |
|---|---|---|
| Raspberry Pi 5 | 8GB RAM, BCM2712 | Owned |
| M5Stack LLM-8850 | AX8850 SoC, 24 TOPS INT8, 8GB LPDDR4x | Owned |
| PiSugar Whisplay HAT | 1.69" LCD, dual mics, speaker (WM8960), LEDs, buttons | Owned |
| PiSugar 3 Plus | 5000mAh LiPo, UPS, RTC, USB-C charging | Owned |

### Key Hardware Constraints
- NPU memory budget: 8GB total (~7040 MiB CMM usable)
- PCIe 2.0 x1 bandwidth to NPU: ~500 MB/s
- Cannot share PCIe with NVMe SSD
- Combined power draw ~19W exceeds PiSugar output (3A @ 5V = 15W)
- Must disable PiSugar AUTO switch to avoid I2C conflicts with Whisplay
- NPU adapter PiHat requires ≥27W USB-C PD power input

### NPU Supported Models (confirmed)
- **LLM:** Qwen3-0.6B, Qwen3-1.7B, Qwen2.5-0.5B/1.5B-Instruct, DeepSeek-R1-Distill-Qwen-1.5B, MiniCPM4-0.5B
- **Multimodal:** InternVL3-1B, Qwen2.5-VL-3B-Instruct, SmolVLM2-500M
- **ASR:** Whisper, SenseVoice
- **TTS:** MeloTTS, CosyVoice2
- **Vision:** YOLO11, Depth-Anything-V2, Real-ESRGAN
- **Other:** CLIP, 3D-Speaker-MT, LivePortrait, Stable Diffusion 1.5

### NPU Performance (from benchmarks/reviews)
- Qwen3-0.6B: ~12.88 tok/s (w8a16)
- Qwen2.5-1.5B-Instruct: ~15.03 tok/s
- Qwen3-1.7B: TBD (Phase 0 testing)
- SenseVoice RTF: ~0.015 (67x faster than real-time)
- User reports: ~20 tok/s for optimized smaller models

## Design Decisions Made

| ID | Decision | Rationale |
|---|---|---|
| DD-001 | Python 3.11+ as primary language | AXCL Python bindings, ML ecosystem |
| DD-002 | Local-first with optional secure external | Privacy + flexibility |
| DD-003 | 4-tier permission model | Tiered autonomy: safe=auto, risky=approval |
| DD-004 | General-purpose assistant | No premature domain optimization |
| DD-005 | Qwen3-1.7B primary model | Best capability/speed on this NPU; native Hermes tool calling |
| DD-006 | FastAPI + HTMX for web UI | Lightweight, async, server-driven |
| DD-007 | SQLite + sqlite-vec for memory | No separate DB server, vector search support |
| DD-008 | ZeroMQ for IPC | Fast, brokerless, simple |
| DD-009 | bubblewrap for sandboxing | Lightweight, no daemon, fine-grained |
| DD-010 | systemd for service management | Standard, watchdog, dependencies |

## Architecture
Seven-layer stack:
1. HAL (NPU, Audio, Display, Power services)
2. Voice Pipeline (Wake → VAD → ASR → LLM → TTS → Speaker)
3. Reasoning Core (Qwen3-1.7B, model router, prompt management)
4. Agent Framework (planner, tool registry, agent factory, memory)
5. Security (4-tier permissions, bubblewrap sandbox, audit log, crypto)
6. Web UI (FastAPI + HTMX chat, dashboard, tool/agent management)
7. Display UI (Whisplay LCD states, button mapping, LED status)

## Implementation Phases
- **Phase 0** — Hardware foundation (CURRENT)
- **Phase 1** — Voice loop (VAD + ASR + LLM + TTS end-to-end)
- **Phase 2** — Agent core (tools, permissions, audit, sandbox)
- **Phase 3** — Web UI
- **Phase 4** — Dynamic capabilities (tool creation, agent factory, wake word)
- **Phase 5** — IoT integration (MQTT, Home Assistant)
- **Phase 6** — Hardening and polish

## Key Technical Findings
- Qwen3 has native Hermes-style tool calling; Qwen-Agent recommended for agentic use
- AXCL driver installs via M5Stack apt repo; Python + C APIs available
- sherpa-onnx has AXCL backend for ASR (SenseVoice proven on this hardware)
- PiSugar 3 Plus connects via pogo pins (back), does NOT occupy GPIO
- Whisplay HAT uses GPIO header (top), SPI for LCD, I2S/I2C for audio
- Existing reference: PiSugar whisplay-ai-chatbot (TypeScript, basic chatbot)
- Model loading on NPU uses CMM (compute memory), separate from system memory

## Open Questions (to resolve during Phase 0)
1. Can SenseVoice + Qwen3-1.7B + MeloTTS all co-reside in 8GB NPU CMM?
2. NPU model hot-swap latency?
3. Wake word engine choice (Porcupine vs OpenWakeWord)?
4. Need USB SSD for extended storage?
5. Enclosure design?

## File Structure
```
Cortex/
├── docs/design/         # Scope and architecture docs
├── docs/guides/         # Setup and operational guides
├── docs/architecture/   # Detailed layer specs (to be created)
├── docs/decisions/      # ADRs (to be created)
├── context/             # This file and other context docs
├── src/cortex/          # Application source (to be created)
├── tests/               # Test suites (to be created)
├── config/              # Config files (to be created)
├── scripts/             # Utility scripts
├── models/              # Local model storage (gitignored)
└── data/                # Runtime data (gitignored)
```

## Conversation History Summary
- **Session 1 (2026-02-27):** Defined full project scope, hardware validation, 7-layer architecture, 4-tier security model, 6-phase implementation plan. Created scope document v0.1 and Phase 0 hardware setup guide. Decided on Python, local-first networking, tiered autonomy, general-purpose focus.

---

*To resume a design session, share this file and state which phase/layer you want to work on.*
DOCEOF

echo "✅ context/project-context.md"

# =============================================================================
# DOCUMENT: Hardware Research Notes
# =============================================================================
cat > "$BASE/context/hardware-research.md" << 'DOCEOF'
# Hardware Research Notes
# Compiled: 2026-02-27

## M5Stack LLM-8850 (AX8850)

### Specifications
- SoC: Axera AX8850
- NPU: 24 TOPS @ INT8
- CPU: Octa-core Cortex-A55 @ 1.7 GHz (on the NPU card itself)
- Memory: 8GB LPDDR4x, 64-bit, 4266 Mbps
- Storage: 32 Mbit SPI NOR Flash (bootloader only)
- Video: 8K@30fps H.264/H.265 encode, 8K@60fps decode, 16-ch 1080p parallel decode
- Security: AES/DES/3DES/SHA-256 hardware security module
- Form factor: M.2 M-Key 2242
- Interface: PCIe 2.0 x2 (backward compatible x1 for RPi)
- Power: 7W @ 3.3V max
- Cooling: Onboard turbo fan + CNC aluminum heatsink, EC-controlled
- Operating temp: 0-60°C
- Weight: 14.7g
- Dimensions: 42.6 x 24.0 x 9.7 mm

### Software
- OS support: Ubuntu 20.04/22.04/24.04, Debian 12 (NO Windows/macOS/WSL)
- Runtime: AXCL with C and Python APIs
- Driver: axcl-smi (apt package from M5Stack repo)
- Model framework: Native AXCL for optimized models, sherpa-onnx for ASR
- Model format: .axmodel (converted via Pulsar2 toolchain)

### Key Findings
- Pi 5 connects via PCIe 2.0 x1 (~500 MB/s)
- Cannot share PCIe bus with NVMe SSD
- M5Stack PiHat Kit requires ≥27W USB-C PD, powers both NPU and Pi
- RPi M.2 HAT+ also works, powered via Pi's USB-C (5V@5A)
- NPU has its own 8-core CPU — runs inference independently
- CMM (Compute Memory) is the NPU's memory pool, ~7040 MiB usable
- AXCL-SMI shows: Memory-Usage (system) and CMM-Usage (models/compute)
- User reviews report ~20 tok/s for smaller models, one noted TOPS rating feels inflated
- Pulsar2 toolchain can convert custom ONNX models to axmodel format

### Performance Benchmarks (from wiki/reviews)
- Qwen3-0.6B (w8a16): 12.88 tok/s
- Qwen2.5-1.5B-Instruct: 15.03 tok/s
- Qwen2.5-VL-3B (image inference): 4.81 tok/s
- SenseVoice (7s audio): RTF 0.015 (0.105s processing time)
- Competitor: RPi AI HAT+ 2 gets 6.74 tok/s on same Qwen2.5-1.5B

### Important Warnings
- Do NOT use PD adapters with bare M.2 card (use non-PD 5V@3A)
- M5Stack PiHat Kit REQUIRES PD adapter (≥9V@3A)
- Device gets hot under load — do not touch during operation
- Third-party M.2 adapters may have compatibility issues
- Waveshare PCIe-to-dual-lane adapter confirmed NOT supported

## PiSugar Whisplay HAT

### Specifications
- Display: 1.69" IPS LCD, 240x280 pixels (ST7789 controller)
- Audio codec: WM8960
- Microphones: Dual MEMS mics
- Speaker: Built-in mono, supports external via XH2.0 connector
- LEDs: RGB indicator lights
- Buttons: Programmable push buttons
- Interfaces: I2C (audio), SPI (LCD), I2S (audio)
- Compatible: RPi Zero/Zero 2 W/RPi 5

### Software
- Driver: install_wm8960_drive.sh from GitHub repo
- Python library: whisplay.py (auto-detects platform)
- GitHub: https://github.com/PiSugar/Whisplay
- Reference chatbot: https://github.com/PiSugar/whisplay-ai-chatbot

### Key Findings
- LCD is glass — fragile, handle by PCB edges
- Button side aligns with Pi's USB port side
- On RPi OS 2025-11-24+, new sound cards NOT set as default
- Must specify card number explicitly in ALSA commands
- If using with PiSugar 3 Plus, disable AUTO switch to prevent I2C conflicts
- External speaker: mono only, XH2.0 connector
- Test suite included: run_test.sh (LCD, buttons, LEDs, audio)

## PiSugar 3 Plus

### Specifications
- Battery: 5000mAh LiPo (magnetic attach)
- Output: 5V @ 2.5-3A max
- Input: 5V @ 3A max (USB-C or Micro-USB)
- RTC: DS3231-compatible, >1 year standby
- MCU: Independent power management
- I2C addresses: 0x57 (EEPROM), 0x68 (RTC), 0x75 (MCU)
- Connection: Pogo pins (back of Pi) — does NOT occupy GPIO
- Features: UPS, soft shutdown, watchdog, custom button, OTA firmware
- Web UI: http://<ip>:8421

### Software
- Power manager: pisugar-power-manager (Rust + Vue2.0)
- Install: wget + bash script from cdn.pisugar.com
- API: UDP/UDS/WebSocket (e.g., `echo "get battery" | nc -U /tmp/pisugar-server.sock`)
- Status: Battery %, charging state, voltage, external power detection

### Key Findings
- Max 3A output is insufficient for Pi 5 + NPU at full load (~4A+ needed)
- Viable as UPS and for portable light-duty use
- Pi 5 under-voltage warnings likely when running NPU on battery
- Anti-mistaken-touch enabled by default (click & hold to power on)
- RTC can be used for reliable audit timestamps
- Watchdog can auto-restart crashed Pi
- I2C address configurable to avoid conflicts
DOCEOF

echo "✅ context/hardware-research.md"

# =============================================================================
# DOCUMENT: .gitignore
# =============================================================================
cat > "$BASE/.gitignore" << 'DOCEOF'
# Project Cortex .gitignore

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/
env/

# Models (large binary files)
models/

# Runtime data
data/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Secrets
.env
*.key
*.pem
config/secrets.yaml

# Logs
*.log
logs/

# Temporary
tmp/
temp/
DOCEOF

echo "✅ .gitignore"

# =============================================================================
# DOCUMENT: Initial Python package structure
# =============================================================================

# Create __init__.py files for Python package structure
touch "$BASE/src/__init__.py"
touch "$BASE/src/cortex/__init__.py"

for pkg in hal voice reasoning agent agent/tools agent/tools/builtin agent/tools/dynamic agent/agents security memory web web/api web/frontend display iot utils; do
    touch "$BASE/src/cortex/$pkg/__init__.py"
done

touch "$BASE/tests/__init__.py"
touch "$BASE/tests/unit/__init__.py"
touch "$BASE/tests/integration/__init__.py"
touch "$BASE/tests/hardware/__init__.py"

echo "✅ Python package __init__.py files"

# =============================================================================
# DOCUMENT: pyproject.toml (initial)
# =============================================================================
cat > "$BASE/pyproject.toml" << 'DOCEOF'
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "cortex"
version = "0.1.0"
description = "Agentic local LLM voice assistant for Raspberry Pi 5 + NPU"
requires-python = ">=3.11"
license = {text = "MIT"}

dependencies = [
    # Core
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "websockets>=12.0",
    # IPC
    "pyzmq>=25.0",
    # Database
    "aiosqlite>=0.19.0",
    # Audio (Pi-side processing)
    "numpy>=1.26.0",
    # Utilities
    "pyyaml>=6.0",
    "pydantic>=2.5.0",
    "python-dotenv>=1.0.0",
    "structlog>=23.2.0",
    "rich>=13.7.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.1.0",
    "mypy>=1.7.0",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
DOCEOF

echo "✅ pyproject.toml"

# =============================================================================
# DOCUMENT: Initial config template
# =============================================================================
cat > "$BASE/config/cortex.yaml.template" << 'DOCEOF'
# Project Cortex — Configuration Template
# Copy to cortex.yaml and customize

system:
  hostname: cortex
  log_level: INFO  # DEBUG, INFO, WARNING, ERROR
  data_dir: /opt/cortex/data
  timezone: UTC  # Set to your timezone

hal:
  npu:
    device_id: 0
    axcl_json: /etc/axcl.json
    thermal_throttle_temp: 75  # °C
    thermal_shutdown_temp: 85  # °C
  audio:
    card_name: wm8960sound  # From aplay -l
    sample_rate: 16000
    channels: 1
    format: S16_LE
    volume: 80  # 0-100
  display:
    brightness: 80  # 0-100
    idle_timeout: 30  # seconds before dimming
    orientation: 0  # 0, 90, 180, 270
  power:
    pisugar_socket: /tmp/pisugar-server.sock
    low_battery_threshold: 15  # %
    critical_battery_threshold: 5  # %
    sleep_on_battery_idle: 300  # seconds

voice:
  activation_mode: push_to_talk  # push_to_talk, wake_word, always_on
  wake_word: cortex
  vad:
    engine: silero
    threshold: 0.5
    min_speech_duration: 0.25  # seconds
    max_speech_duration: 30  # seconds
    silence_timeout: 1.5  # seconds after speech ends
  asr:
    model: sensevoice  # sensevoice, whisper
    language: en
  tts:
    model: melotts  # melotts, cosyvoice2
    voice: default
    speed: 1.0
  latency_budget:
    asr_max_ms: 500
    tts_first_audio_ms: 200

reasoning:
  primary_model: qwen3-1.7b
  fallback_model: qwen3-0.6b
  default_mode: non_thinking  # thinking, non_thinking
  max_tokens: 512
  temperature: 0.7
  context_window: 4096  # Effective context (subset of 32K for speed)
  system_prompt_version: v1

agent:
  max_plan_steps: 10
  tool_timeout: 30  # seconds per tool execution
  max_concurrent_tools: 1  # Pi CPU limitation
  dynamic_tools:
    enabled: true
    auto_persist: false  # Require user approval to save
    sandbox: bubblewrap
    max_memory_mb: 256
    max_cpu_seconds: 30

security:
  tier_0_auto: true
  tier_1_log: true
  tier_2_require_approval: true
  tier_3_require_confirmation_and_reason: true
  approval_timeout: 60  # seconds
  default_deny_on_timeout: true
  audit:
    enabled: true
    retention_days: 90
    format: jsonl  # jsonl, sqlite
  network:
    default_policy: deny
    allowed_domains: []  # Populated by user
    local_network_access: true  # For IoT
    tls_minimum: "1.3"
  sandbox:
    engine: bubblewrap  # bubblewrap, podman
    scratch_dir: /opt/cortex/data/sandbox

memory:
  short_term:
    max_conversations: 100
    retention_days: 30
  long_term:
    enabled: true
    embedding_model: cpu  # cpu (small model) or npu
    max_entries: 10000
  encryption:
    enabled: true
    algorithm: aes-256-gcm

web:
  host: "0.0.0.0"  # Will be restricted by nftables
  port: 8080
  auth:
    enabled: true
    # password_hash set via setup script
  session_timeout: 3600  # seconds
  cors_origins: []  # Restrict to specific origins if needed

iot:
  enabled: false  # Enable in Phase 5
  mqtt:
    broker: ""  # e.g., localhost or HA IP
    port: 1883
    username: ""
    password: ""
  homeassistant:
    url: ""  # e.g., http://homeassistant.local:8123
    token: ""  # Long-lived access token
DOCEOF

echo "✅ config/cortex.yaml.template"

# =============================================================================
# Finalize
# =============================================================================

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "🧠 Project Cortex — Setup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Directory: $BASE"
echo ""
echo "Key files created:"
echo "  📄 README.md                           — Project overview"
echo "  📄 docs/design/scope-v0.1.md           — Full scope document"
echo "  📄 docs/guides/phase-0-hardware-setup.md — Hardware setup guide"
echo "  📄 context/project-context.md           — AI session context"
echo "  📄 context/hardware-research.md         — Hardware research notes"
echo "  📄 pyproject.toml                       — Python project config"
echo "  📄 config/cortex.yaml.template          — Configuration template"
echo "  📄 .gitignore                           — Git ignore rules"
echo "  📁 src/cortex/                          — Source code skeleton"
echo "  📁 tests/                               — Test skeleton"
echo ""
echo "Next steps:"
echo "  1. cd $BASE"
echo "  2. git init && git add -A && git commit -m 'Initial project structure'"
echo "  3. python3 -m venv .venv && source .venv/bin/activate"
echo "  4. pip install -e '.[dev]'"
echo "  5. Start Phase 0 hardware setup (see docs/guides/)"
echo "  6. To resume design: share context/project-context.md with Claude"
echo ""
