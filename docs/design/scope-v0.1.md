# Project Cortex — Agentic Local LLM Voice Assistant
## System Design Scope Document v0.1.7

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
- **Camera Service** — Manages USB camera via V4L2/libcamera. Provides single-frame capture on demand (not continuous streaming). Supports resolution negotiation and format conversion (JPEG/PNG). Camera is optional hardware — system operates fully without it.

**Key Design Decisions:**
- All HAL services run as systemd units with dedicated service accounts (no root).
- Hardware access controlled via udev rules and Linux capability sets.
- HAL exposes a unified event bus (e.g., ZeroMQ or D-Bus) for hardware events (button press, low battery, NPU thermal throttle).

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

**Model Allocation on NPU (8GB budget):**

| Model | Purpose | Est. NPU Memory | Est. Performance |
|---|---|---|---|
| Whisper-small or SenseVoice | ASR (Speech-to-Text) | ~500MB | RTF < 0.1 (faster than real-time) |
| Qwen3-1.7B (w8a16) | Reasoning / conversation | ~3.5GB | ~12-15 tok/s |
| Kokoro-82M (v1.0, axmodel) | TTS (Text-to-Speech) | ~237MB | RTF 0.067 (15x real-time) |
| Wake word (custom/Porcupine) | Always-on trigger (Phase 4) | ~10MB | Real-time on Pi CPU |
| SmolVLM2-500M | Vision (always resident) | ~500MB | TBD (Phase 0 testing) |
| **Total estimated (with VLM)** | | **~4.75GB** | Leaves ~2.3GB headroom |

**Vision model hot-swap pool (loaded on demand, replaces Qwen3-1.7B temporarily):**

| Model | Purpose | Est. NPU Memory | Notes |
|---|---|---|---|
| InternVL3-1B | Detailed image analysis | ~1.5GB (est.) | Best quality; requires unloading LLM |
| Qwen2.5-VL-3B-Instruct | Advanced multimodal reasoning | ~3GB (est.) | Largest; requires unloading LLM + possibly ASR |

**Activation Modes:**
1. **Button push-to-talk (physical Pi, default)** — Whisplay button (GPIO 11) held down; audio captured while held, sent to ASR on release. Zero false activations.
2. **Button push-to-talk (Web UI)** — Browser record button mirrors physical button: hold-to-talk or click-to-start/click-to-stop. User controls recording boundaries explicitly. No VAD needed.
3. **Wake word (Phase 4, optional)** — Always-on lightweight detector on Pi CPU, NPU wakes for ASR. Can coexist with push-to-talk.
4. **Text input (Web UI)** — Bypasses voice pipeline entirely.

**Latency Budget (voice round-trip target: < 3 seconds):**
- ASR: < 500ms for typical utterance (button release triggers immediate ASR — no VAD delay on any interface)
- LLM inference (50-token response @ 15 tok/s): ~3.3s
- TTS synthesis: < 500ms (with streaming, first audio < 200ms)
- **Stretch goal:** Stream TTS while LLM is still generating (sentence-level chunking via Kokoro's native generator pipeline).

**NPU Memory Management Strategy:**
- Models can be hot-swapped. ASR loads → runs → partially unloads during LLM inference.
- Alternatively, keep all three resident if memory allows (~4.25GB fits in 8GB with ~3.5GB headroom).
- Kokoro uses a hybrid pipeline: 3 axmodel parts on NPU + ONNX vocoder on CPU, reducing NPU memory pressure.
- Monitor via NPU Service; degrade gracefully (e.g., smaller ASR model) if memory pressure detected.
- **Vision hot-swap:** SmolVLM2-500M stays resident for quick image descriptions (~500MB). For detailed analysis, unload Qwen3-1.7B, load InternVL3-1B or Qwen2.5-VL-3B, process image, then swap back. Voice pipeline pauses during hot-swap.

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

#### 4.3.3 Context Window Adaptation

Agent token budgets adapt dynamically based on the active provider's context window:

| Provider Context | Orchestrator Budget | Super Agent Budget | Strategy |
|---|---|---|---|
| 4K (local NPU, effective) | ~370 tok | ~4,000 tok | Current budgets — strict, optimized for speed |
| 32K+ (Ollama, remote LLM) | ~500 tok | ~8,000 tok | Relaxed — more history, richer tool descriptions |
| 128K+ (cloud APIs) | ~500 tok | ~16,000 tok | Full history retention, detailed tool descriptions |

The Context Manager queries `provider.capabilities.context_window` and scales budgets proportionally. Local NPU budgets are always the minimum floor — cloud models get more room but never less than what works locally.

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

**Prompt Management:**
- System prompts stored as versioned templates.
- Dynamic tool schema injection — only currently relevant tools are included in context.
- Conversation history managed with sliding window + summarization, scaled by provider context window.
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
3. If no confident match → route to general-purpose super agent
4. If super agent reports inability → escalate to user
5. Phase 4: can spawn ephemeral super agents on-the-fly for novel multi-step tasks

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

`image_analyze` accepts an image from three sources: physical camera capture, web UI upload/webcam, or a URL. It routes to the appropriate VLM profile (`vision_quick` for fast descriptions, `vision_detail` or `vision_advanced` when requested). See §4.3 Model Router for VLM profiles.

Defined in canonical (OpenAI function calling) format. The Tool Adapter (§4.3.2) translates to the active provider's format at call time (NousFnCallPrompt for local Qwen3, native format for cloud APIs).

#### 4.4.7 Agent Factory (Phase 4)

The LLM can create new super agents and action templates dynamically:
- **New super agent:** LLM generates YAML agent definition → security validation → user approval (Tier 3) → registered
- **New action template:** LLM generates YAML template + Python handler → static analysis → sandbox test → user approval (Tier 3) → registered
- All dynamically created agents/templates are version-controlled and can be rolled back
- User can create, modify, and delete agents via voice or web UI

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

#### 4.4.9 Context Management

Per-agent token budgets enforced by a Context Manager, **scaled dynamically based on the active provider's context window** (see §4.3.3):

**Base budgets (local NPU, 4K effective context):**

| Agent Type | System Prompt | Tool Descs | Working Space | Total |
|---|---|---|---|---|
| Orchestrator | 150 | 150-240 | 20 (gen) | ~370 |
| Super Agent | 200 | 150 | 3,600 | ~4,000 |
| Utility Agent | 0 | 0 | 0 | 0 |

**Scaled budgets (when provider context > 4K):**

| Provider Context | Super Agent Total | History Turns | Tool Desc Detail |
|---|---|---|---|
| 4K (local NPU) | ~4,000 tok | 2-3 turns | Minimal |
| 32K+ (Ollama, remote) | ~8,000 tok | 5-8 turns | Standard |
| 128K+ (cloud APIs) | ~16,000 tok | 15-20 turns | Full with examples |

- Conversation history: sliding window, turn count scaled by available context
- Cross-turn context: summarize prior turns only when multi-step planning requires it
- Tool descriptions: pre-computed and cached, detail level scales with context budget
- Orchestrator passes only the relevant user request to the selected agent, not the full orchestrator context
- The Context Manager always uses local NPU budgets as the minimum floor

#### 4.4.10 Memory System

| Type | Storage | Purpose | Retention |
|---|---|---|---|
| **Working Memory** | RAM | Current conversation context | Session |
| **Short-term Memory** | SQLite | Recent conversations, task results | 30 days (configurable) |
| **Long-term Memory** | SQLite + embeddings | Key facts, user preferences, learned patterns | Persistent |
| **Episodic Memory** | SQLite | Significant events, decisions, outcomes | Persistent |
| **Tool Memory** | Filesystem | Generated tools, agent configs, action templates | Persistent |

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
| Model Providers | Provider Protocol abstraction layer | 7 providers: axcl (NPU), openai, anthropic, google, xai, ollama, openai_compatible. Per-profile routing with fallback chains. |
| ASR | sherpa-onnx + AXCL (default) | Proven on LLM8850; cloud ASR available via provider layer |
| LLM | AXCL native (default) | Qwen3-1.7B with Hermes tool calling; cloud/remote LLMs via provider layer |
| TTS | AXCL native + ONNX hybrid (default) | Kokoro-82M v1.0; cloud TTS available via provider layer |
| Agent Framework | Custom 3-tier + Tool Adapter | LangGraph-inspired graph-of-functions; tool calling format auto-adapted per provider |
| Action Engine | Custom Python (YAML templates + handlers) | Zero RAM overhead; replaces n8n/Node-RED for deterministic action execution |
| Tool Protocol | MCP (Python `mcp` SDK) | Standard tool interop; client (consume HA, n8n, etc.) + server (expose Cortex tools) |
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
| DD-014 | Custom Python action engine | 2026-02-27 | Zero RAM overhead, in-process, YAML templates + Python handlers; all external engines (n8n 200-860MB, Node-RED 40-80MB, Temporal 2-4GB, Windmill 2-3GB) too heavy for Pi 5 |
| DD-015 | 3-tier agent hierarchy | 2026-02-27 | Orchestrator (classifier, ~370 tok) → Super Agents (reasoning, 4K context) → Utility Agents (deterministic, 0 LLM tokens); optimized for 1.7B model at 15 tok/s |
| DD-016 | Unconstrained thinking, constrained acting | 2026-02-27 | Agents reason freely with cognitive tools (read-only); world-changing actions go through pre-authorized YAML templates with permission gating and audit logging |
| DD-017 | Qwen-Agent as library only | 2026-02-27 | NousFnCallPrompt for Qwen3-native tool-call parsing; full frameworks rejected (see DD-018) |
| DD-018 | Custom framework over CrewAI/LangGraph/AutoGen | 2026-02-27 | CrewAI: 32GB RAM, ChromaDB dep; AutoGen: conversation paradigm fills 4K in 2-3 exchanges; LangGraph: closest but langchain-core bloat for ~500 LOC of graph execution; smolagents: prompt bloat; Swarm: deprecated |
| DD-019 | MCP protocol support (client + server) | 2026-02-27 | Standard tool interop via Python `mcp` SDK; client discovers external tools (HA, n8n) and maps to cognitive tools or action templates with permission gating; server exposes Cortex tools to external AI clients via Streamable HTTP on FastAPI |
| DD-020 | Tiered VLM vision system | 2026-02-27 | SmolVLM2-500M always resident (~500MB) for quick image descriptions; hot-swap to InternVL3-1B or Qwen2.5-VL-3B for detailed analysis (unloads LLM temporarily). Three input sources: USB camera (physical), webcam (web UI), image upload (web UI). |
| DD-021 | Button-first interaction with Web UI parity | 2026-02-27 | Physical Pi uses Whisplay button (GPIO 11) as sole input — hold=push-to-talk, double-click=camera capture, single-click=approve, long-press=deny/cancel, triple-click=system menu. No VAD on physical Pi (eliminates false activations and privacy concerns). Web UI provides full parity via software equivalents (record button with VAD, webcam/upload, approve/deny buttons). |
| DD-022 | Configurable model provider layer | 2026-02-27 | All model interactions (LLM, ASR, TTS, VLM) routed through provider-agnostic Protocol interfaces. Seven provider types: axcl (local NPU), openai, anthropic, google, xai, ollama, openai_compatible. Per-profile provider chains with automatic fallback and circuit breaker. Tool calling format adapted transparently per provider via Tool Adapter. Context budgets scale dynamically with provider context window. API keys in .env, cloud calls auto-gated by security layer. Default config is fully offline (axcl only) — cloud/remote providers are opt-in. |

*Document version: 0.1.7 — Configurable model provider layer (multi-backend support)*
*Status: DRAFT*
