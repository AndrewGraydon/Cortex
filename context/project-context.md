# Project Cortex — AI Assistant Context File
# Last updated: 2026-03-03 (Session 18)

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
- **Multimodal:** InternVL3-1B, Qwen2.5-VL-3B-Instruct, FastVLM-0.5B (selected, DD-045), SmolVLM2-500M
- **ASR:** Whisper, SenseVoice
- **TTS:** Kokoro-82M (selected), MeloTTS, CosyVoice2
- **Vision:** YOLO11, Depth-Anything-V2, Real-ESRGAN
- **Other:** CLIP, 3D-Speaker-MT, LivePortrait, Stable Diffusion 1.5

### NPU Performance (Phase 0 measured on M.2 + Pi 5, AXCL v3.6.5)
- Qwen3-0.6B (w8a16): **13.74 tok/s**, 2,011 MiB CMM (includes KV cache for 2,047 tokens)
- Qwen3-1.7B (w8a16): **7.70 tok/s**, 3,375 MiB CMM, 2,047 max tokens
- Qwen3-4B (w8a16): 3.65 tok/s, ~6.2 GB CMM (691 MB remaining — can't co-reside), max 2,559 tokens (vendor benchmark)
- Qwen3-VL-2B (w8a16): 7.80 tok/s, ~3.7 GB CMM (vendor benchmark)
- SenseVoice RTF: **0.028** (36x faster than real-time), 251 MiB CMM
- Kokoro-82M RTF: **0.115** (9x real-time, Python/pyaxengine path), 232 MiB CMM
- FastVLM-0.5B: 792 MiB CMM, excellent image descriptions (Python/pyaxengine path)
- **Total 4-model co-resident budget: ~4.95 GB of 7.04 GB (29.7% headroom)**
- Source: [AXERA-TECH HuggingFace](https://huggingface.co/AXERA-TECH) (149+ models total), [M5Stack NPU Benchmark](https://docs.m5stack.com/en/guide/ai_accelerator/llm-8850/m5_llm_8850_npu_benchmark)

## Design Decisions Made

| ID | Decision | Rationale |
|---|---|---|
| DD-001 | Python 3.11+ as primary language | AXCL Python bindings, ML ecosystem |
| DD-002 | Local-first with optional secure external | Privacy + flexibility |
| DD-003 | 4-tier permission model | Tiered autonomy: safe=auto, risky=approval |
| DD-004 | General-purpose assistant | No premature domain optimization |
| DD-005 | Qwen3-1.7B primary model | Measured Phase 0: 7.70 tok/s, 3,375 MiB CMM. Qwen3-4B rejected (3.65 tok/s, 6.2 GB fills NPU). See DD-029. |
| DD-006 | FastAPI + HTMX for web UI | Lightweight, async, server-driven |
| DD-007 | SQLite + sqlite-vec for memory | No separate DB server, vector search support |
| DD-008 | ZeroMQ for IPC | Fast, brokerless, simple |
| DD-009 | bubblewrap for sandboxing | Lightweight, no daemon, fine-grained |
| DD-010 | systemd for service management | Standard, watchdog, dependencies |
| DD-011 | Kokoro-82M as TTS engine | RTF 0.115 (Python path, measured), 232 MiB CMM; #1 TTS Arena quality, already proven on LLM-8850. No C++ AXCL aarch64 binary — Python/pyaxengine required. |
| DD-012 | Adapt whisplay-ai-chatbot for LCD | Proven Pillow+cairosvg renderer on this hardware; 30 FPS, SVG emoji, smooth scrolling |
| DD-013 | Defer web UI framework to Phase 3 | Voice-first; evaluate HTMX+DaisyUI vs NiceGUI vs Svelte later |
| DD-014 | Custom Python action engine | Zero RAM, in-process, YAML templates + Python handlers; n8n/Node-RED/Temporal too heavy |
| DD-015 | 3-tier agent hierarchy | Orchestrator (~370 tok) → Super Agents (4K context) → Utility Agents (0 LLM tokens) |
| DD-016 | Unconstrained thinking, constrained acting | Free reasoning with cognitive tools; actions through pre-authorized templates |
| DD-017 | Qwen-Agent as library only | NousFnCallPrompt for Qwen3-native tool-call parsing |
| DD-018 | Custom framework over CrewAI/LangGraph/AutoGen | All too heavy/bloated for Pi 5 + 1.7B model constraints |
| DD-019 | MCP protocol support (client + server) | Standard tool interop; external tools mapped to cognitive tools or action templates with permission gating |
| DD-020 | Tiered VLM vision system | FastVLM-0.5B always resident (792 MiB, DD-045); hot-swap to InternVL3-1B/Qwen2.5-VL-3B for detail; camera + webcam + upload |
| DD-021 | Button-first interaction with Web UI parity | Physical Pi uses Whisplay button (GPIO 11) as sole input via gestures (hold/double-click/single-click/long-press/triple-click); no VAD anywhere; Web UI has full parity via software equivalents |
| DD-022 | Configurable model provider layer | All model interactions via provider-agnostic Protocol interfaces; 7 providers (axcl, openai, anthropic, google, xai, ollama, openai_compatible); per-profile provider chains with fallback; tool calling auto-adapted; default offline, cloud opt-in |
| DD-023 | SenseVoice-Small as ASR engine | Non-autoregressive (single-pass) — 50-75ms per utterance vs Whisper-Small 800-1800ms (autoregressive). 10-20x faster on same NPU. Comparable accuracy for English. Faster Whisper can't use NPU (CPU-only via CTranslate2). Both to be tested Phase 0. |
| DD-024 | CSI camera via libcamera/picamera2 | Freenove camera module uses CSI connector, not USB. picamera2 is the standard Pi camera interface. |
| DD-025 | No wake word — button-only activation | With button-first (DD-021) and no VAD, wake word serves no purpose. Removed entirely. No always-on mic, no background audio processing. |
| DD-026 | Provider-managed context | No centralized context budget scaling. Each provider knows its own limits; agent framework passes full ideal prompt, provider handles truncation. Simplifies architecture. |
| DD-027 | Tool development pipeline | Structured lifecycle: Specify → Develop → Review → Approve → Deploy. Tools start at Tier 2, promote after supervised use. Sandbox testing, version control, rollback. |
| DD-028 | Context assembly & memory system | Context Assembler builds prompts in priority order (system → request → tools → memories → summary → history). Rolling summary during TTS playback for 4K NPU coherence. 5 memory tiers with post-session LLM extraction. Automatic semantic retrieval (~20-40ms, CPU embedding) injects memories into prompts. all-MiniLM-L6-v2 + sqlite-vec. |
| DD-029 | Qwen3-1.7B confirmed, 4B rejected | Phase 0 measured: 1.7B = 7.70 tok/s, 3,375 MiB CMM; 0.6B = 13.74 tok/s, 2,011 MiB. 4B = 3.65 tok/s, 6.2 GB (fills NPU, can't co-reside). 4B as future hot-swap only. AXERA-TECH catalog (149+ models). |
| DD-030 | Voice interaction lifecycle | Session management (idle timeout, farewell detection), interruption handling (long-press stop, new-utterance replace), error recovery table (8 failure scenarios), confirmation feedback patterns, capability discovery (per-persona zero-LLM templates), system prompt persona guidelines |
| DD-031 | Streaming voice pipeline | Sentence-boundary streaming with parallel TTS to mitigate 7.70 tok/s latency. Sentence detector buffers tokens until punctuation, Kokoro synthesizes in parallel via NPU multiplexing (confirmed DD-048). TTFA target <5s. |
| DD-032 | Utility tools, scheduling & notifications | 9 new cognitive tools (clock, calculator, weather, etc.), SQLite-backed scheduling service for timers/reminders (survives reboots), 5-level notification priority system (P0 silent → P4 interruptive) with DND mode and conversation-aware queueing |
| DD-033 | System resilience & health monitoring | Health monitoring service (7 components, ZeroMQ bus), /api/health endpoint, 4-zone NPU thermal management, systemd watchdog, graceful degradation matrix (8 failure scenarios with defined UX), error UX principles |
| DD-034 | Conversational clarification & repair | Confidence-gated orchestrator (threshold 0.6) triggers clarification instead of misrouting. Slot filling for missing parameters, disambiguation with 2-3 options, escalating repair ladder (rephrase → options → explicit help). Max 2 clarification rounds. Sentiment-aware adaptation via system prompt (zero model cost). |
| DD-035 | External services integration (PIM) | PTT voice = messaging pattern — users expect calendar, messaging, email, tasks. CalDAV calendar backend, ntfy/Pushover/Matrix messaging relay, IMAP/SMTP email, CalDAV VTODO/Todoist task sync. Service Adapter Protocol. New `pim` super agent. Phase 3 read+write, Phase 5 full bidirectional sync. |
| DD-036 | A2A protocol support | Google Agent2Agent protocol (v0.3, Linux Foundation). Complementary to MCP: MCP = tool/data access, A2A = agent-to-agent task delegation. Client + Server (Phase 3): discover external agents via Agent Cards, expose Cortex super agents. JSON-RPC over HTTP/SSE, python-a2a SDK. |
| DD-037 | Wyoming protocol bridge | Home Assistant's standard for local voice satellites (JSONL over TCP). Three modes: STT Provider (SenseVoice), TTS Provider (Kokoro), Satellite (optional, HA orchestrates). Python `wyoming` package. Phase 5. |
| DD-038 | Proactive intelligence engine | Pattern detection from episodic memory + scheduling + calendar. Time-of-day routines (morning briefing at learned wakeup time), context-aware connections, routine suggestions. Idle-time "think" loop using Qwen3-0.6B. Fully opt-in, per-routine configurable. Phase 4 design, Phase 5 implementation. |
| DD-039 | Knowledge store & document RAG | Sixth memory tier: Knowledge Store (SQLite + sqlite-vec, persistent). Document ingestion via web UI upload or watched directory. ~200-token chunks with 50-token overlap, same all-MiniLM-L6-v2 embedding. knowledge_search tool gets real backend. Supported formats: txt, md, pdf, html. Phase 4. |
| DD-040 | Power-aware operation profiles | 4 profiles: mains (1.7B, full polling), battery (0.6B, 2x intervals), low_battery (0.6B, 4x intervals), critical (regex-only, no LLM). Auto-transition via Power Service ZeroMQ events. Manual override via voice. Phase 1 design, Phase 2 auto-switching. |
| DD-041 | NPU hardware abstraction | NpuService Protocol class with generic numpy I/O. No AXCL-specific types at interface level. All AXCL specifics isolated inside AxclNpuService. Phase 1: MockNpuService for off-Pi development/testing. Future: HailoNpuService (Pi AI HAT+ 2). Design discipline enforced from Phase 1. |
| DD-042 | Web authentication & session management | Phase 1-2: no auth on LAN. Phase 3: bcrypt password + HTTP-only session cookie. Phase 3+: HTTPS (Caddy) + optional TOTP 2FA. Server-side sessions in SQLite. Persona mapping via auth state. No JWT/OAuth (overkill for single-user). |
| DD-043 | Process & service architecture | Single main process (cortex-core.service, asyncio/uvloop) + separate HAL processes (cortex-npu, cortex-audio, cortex-display). All IPC via ZeroMQ (JSON, topic convention {service}.{event_type}). Minimizes RAM and IPC latency. |
| DD-044 | Operational lifecycle | git clone + pip install deployment. Lightweight SQL migration system (numbered files, no Alembic). Backup/restore scripts (data/ + config/ + .env, excludes models/). structlog JSON → stdout → systemd journal. |
| DD-045 | FastVLM-0.5B replaces SmolVLM2-500M | Phase 0 tested: 6x faster image encoding than InternVL2.5-1B, 792 MiB CMM, excellent descriptions. No C++ AXCL aarch64 binary — Python/pyaxengine path only. Total 4-model budget ~4.95 GB (29.7% headroom). |
| DD-046 | Mixed NPU invocation architecture | LLM uses C++ binary (`main_axcl_aarch64`) + tokenizer HTTP server (port 12345). ASR/TTS/VLM use pyaxengine `InferenceSession` directly. FastVLM's `InferManager` proves pure-Python LLM inference possible (future optimization). |
| DD-047 | 2,047 token hard limit confirmed | Baked into compiled axmodel. Tokenizer says 131K (irrelevant). config.json is 0 bytes. Requires Pulsar2 recompile to change. Context budget: ~1,200 input + ~800 generation tokens. |
| DD-048 | NPU multiplexing confirmed (~0ms switch) | Co-resident models interleave with negligible overhead. Tested 10 rounds: SenseVoice 128.6ms + Kokoro 18.6ms alternating. Streaming pipeline (DD-031) confirmed feasible. |
| DD-050 | Script-based tools (progressive disclosure) | Self-contained tool folders (TOOL.yaml + scripts/) as alternative to Python handler classes. 3-level progressive disclosure for 2,047-token budget. Scripts handle deterministic validation/formatting (saves tokens). Phase 3: loader + MCP workflow templates. Phase 4: user-created tools + bubblewrap sandbox. Inspired by Anthropic's Claude Skills architecture. |
| DD-049 | Audio via sounddevice + ALSA default device | Capture: 16kHz mono via ALSA `default` device (plug→dsnoop handles stereo WM8960 hw). WM8960 hw requires 2-channel capture — do NOT use `hw:0,0` with channels=1. Playback: ALSA `default` (dmix resamples 24kHz→48kHz). DC offset removal in software (~300-600 ADC bias). Mixer: Capture=55, Boost=2(+20dB), ALC=OFF, HPF=on, NoiseGate=on. Verified with SenseVoice ASR: transcribes accurately at these levels (0.17s inference). |

## Architecture
Seven-layer stack:
1. HAL (NPU, Audio, Display, Power, Camera services)
2. Voice Pipeline (Button/Wake → ASR → LLM → TTS → Speaker)
3. Reasoning Core (Model Provider Layer → Model Router → Prompt Management)
4. Agent Framework (3-tier: Orchestrator → Super Agents → Utility Agents, Action Engine, memory)
5. Security (4-tier permissions, bubblewrap sandbox, audit log, crypto)
6. Web UI (FastAPI + HTMX chat, dashboard, tool/agent management)
7. Display UI (Whisplay LCD states, button mapping, LED status)

## Implementation Phases
- **Phase 0** — Hardware foundation (COMPLETE)
- **Phase 1** — Voice loop (COMPLETE — all milestones 1.1-4.4, 121 tests passing)
- **Phase 2** — Agent core (COMPLETE — all milestones 2.1-2.8, 487 tests passing, validated on Pi)
- **Phase 3** — Web UI (NEXT)
- **Phase 4** — Dynamic capabilities (tool pipeline, agent factory, long-term memory)
- **Phase 5** — IoT integration (MQTT, Home Assistant)
- **Phase 6** — Hardening and polish

## Key Technical Findings
- Qwen3 has native Hermes-style tool calling; Qwen-Agent NousFnCallPrompt used for parsing
- AXCL driver installs via M5Stack apt repo; Python + C APIs available
- sherpa-onnx has AXCL backend for ASR (SenseVoice proven on this hardware)
- PiSugar 3 Plus connects via pogo pins (back), does NOT occupy GPIO
- Whisplay HAT uses GPIO header (top), SPI for LCD, I2S/I2C for audio
- Existing reference: PiSugar whisplay-ai-chatbot (TypeScript, basic chatbot)
- Model loading on NPU uses CMM (compute memory), separate from system memory
- Kokoro-82M TTS: RTF 0.115 measured (Python/pyaxengine on Pi host), RTF 0.067 native (C++ on NPU CPU). 232 MiB CMM. No C++ AXCL aarch64 binary available — must use Python path. Voice file format: .npy (not .pt). Heavy Python deps required (kokoro, misaki, pypinyin, pyopenjtalk, etc.)
- Kokoro proven on LLM-8850: see https://github.com/AndrewGraydon/kokoro.LM8850
- **Measured NPU memory budget (Phase 0):** SenseVoice (251 MiB) + Qwen3-1.7B (3,375 MiB) + Kokoro (232 MiB) + FastVLM-0.5B (792 MiB) = ~4.95 GB of 7.04 GB (29.7% headroom). Qwen3-4B rejected — 6.2GB fills NPU, can't co-reside with any other model.
- whisplay-ai-chatbot LCD architecture: TypeScript brain + Python display over TCP socket; Pillow + cairosvg rendering at 30 FPS; SPI at 100MHz; SVG emoji, LANCZOS resampling, line caching
- Cortex will adapt this approach, replacing TCP socket IPC with ZeroMQ to match the rest of the stack
- CAAL (CoreWorxLab) is a single-agent voice pipeline, not a multi-agent framework — but the concept of separating reasoning from action execution via pre-defined workflows is sound
- Agent framework research (8 frameworks evaluated): CrewAI (32GB RAM, ChromaDB dep), AutoGen (conversation paradigm fills 4K in 2-3 turns), LangGraph (closest match but langchain-core bloat), smolagents (prompt bloat), Swarm (deprecated), Qwen-Agent (best for tool-call parsing only), ReAct (reasoning overhead for 1.7B)
- Workflow engine research (8 engines): n8n (200-860MB), Node-RED (40-80MB+leaks), Temporal (2-4GB), Prefect (500MB+), Windmill (no ARM64), Dagu (Go binary), pypyr (right pattern). All external engines too heavy for Pi — custom in-process Python action engine selected
- Token budgets for 4K context: Orchestrator ~370 tokens (single classifier call), Super Agent ~4000 tokens (200 system + 150 tools + 3600 working), Utility Agent 0 tokens (deterministic)
- MCP (Model Context Protocol) supported via Python `mcp` SDK: client mode discovers tools from external servers (HA, n8n), server mode exposes Cortex tools to external AI clients; Streamable HTTP transport on existing FastAPI server. n8n as external MCP tool server: n8n runs on NAS/Docker (not Pi — DD-014 rejected on-Pi), exposes workflows via MCP, Cortex discovers and registers them as action templates. Users build automations in n8n's visual editor, invoke by voice. Similar to CAAL's approach but decoupled via MCP.
- Unified tool discovery lifecycle: all three tool sources (Python handlers, script-based TOOL.yaml, MCP servers) share same ToolRegistry discovery flow. Discovery triggers: startup scan, SIGHUP hot-reload, MCP reconnect, web UI upload, tool pipeline deploy, config change. MCP-discovered tools can have trigger patterns and keywords (via config overrides) for zero-LLM routing — same as script-based tools. Agents interact through unified Tool protocol interface regardless of tool backing.
- Tiered VLM vision: FastVLM-0.5B always resident (792 MiB, DD-045, replaces SmolVLM2-500M); hot-swap to InternVL3-1B or Qwen2.5-VL-3B for detailed analysis (unloads LLM temporarily, voice pipeline pauses). No C++ AXCL aarch64 binary — Python/pyaxengine path. Three image sources: CSI camera via picamera2 (physical Pi), webcam (web UI), file upload (web UI)
- Whisplay HAT button hardware: single button on pin 11 (**active HIGH** — pressed=1, not active-low as initially assumed), RGB LEDs on pins 22/18/16. Uses RPi.GPIO BOARD pin numbering (not BCM, not gpiod). PWM cleanup has cosmetic TypeError bug in python3-rpi-lgpio (non-blocking). **RPi.GPIO fires callbacks on background thread** — must use `asyncio.run_coroutine_threadsafe()`, not `asyncio.ensure_future()`, for async scheduling from GPIO callbacks.
- Button-first interaction: hold=push-to-talk (record while held, ASR on release), double-click=camera capture+VLM, single-click=approve/confirm, long-press=deny/cancel, triple-click=system menu. No VAD anywhere — both Pi and Web UI use explicit button control for recording boundaries.
- Web UI parity: every physical Pi capability has a software equivalent — record button (hold-to-talk or click-start/click-stop), webcam/upload for vision, approve/deny buttons for Tier 2/3, status indicator for LED state.
- Model Provider Layer: provider-agnostic Protocol interfaces for LLM, ASR, TTS, VLM. Seven providers: axcl (local NPU), openai, anthropic, google, xai, ollama, openai_compatible. Per-profile provider chains with fallback and circuit breaker. Tool calling format auto-adapted per provider (NousFnCallPrompt for Qwen3, OpenAI function calling for cloud, etc.). Context is provider-managed — each provider handles its own limits, no centralized budget scaling. API keys in .env, cloud calls gated by security layer with auto nftables management. Default: fully offline (axcl only).
- SenseVoice-Small ASR: non-autoregressive single-pass inference, 50-75ms per utterance on NPU (10-20x faster than Whisper-Small's 800-1800ms autoregressive decoding). Comparable English accuracy. Faster Whisper cannot use NPU (CPU-only via CTranslate2).
- Tool development pipeline: Specify → Develop → Review → Approve → Deploy lifecycle. Tools start at Tier 2, promote to Tier 1/0 after supervised successful executions. Sandbox testing via bubblewrap, version-controlled with rollback.
- Six memory tiers: working (RAM), short-term (SQLite summaries), long-term (sqlite-vec facts), episodic (events/outcomes), tool (filesystem), knowledge store (document RAG via sqlite-vec). Knowledge store uses ~200-token chunks with 50-token overlap, same all-MiniLM-L6-v2 embedding pipeline.
- Context Assembly Pipeline: prompts built in priority order (P1 system → P2 request → P3 tools → P4 auto-injected memories → P5 rolling summary → P6 recent turns → P7 older history). On 4K local NPU: ~200+150+150+200+150+400 = ~1,250 tok overhead, leaving ~2,750 for generation. Cloud providers skip summary, include full history.
- Rolling conversation summary: generated during TTS playback (NPU idle), ~100 tokens, updated every 3 exchanges. Hides latency. Abandoned if user interrupts — fallback to raw recent turns. Not required for correctness.
- Memory extraction: post-session LLM call extracts atomic facts + events from conversation summary → embeds on CPU → stores in sqlite-vec. Dedup via cosine similarity > 0.85. Also: regex-based in-conversation capture for explicit "remember..." requests.
- Embedding model: all-MiniLM-L6-v2 via ONNX Runtime on CPU (~22MB, 384-dim, ~10-20ms/embed). sqlite-vec brute-force KNN sufficient for <50K entries. NPU reserved for LLM/ASR/TTS.
- Streaming voice pipeline: sentence-boundary detection buffers LLM tokens until `.!?:;—` + whitespace (min 8, max 96 tokens per chunk). Kokoro TTS synthesizes sentence N while LLM generates sentence N+1 via NPU model multiplexing. 10ms crossfade between audio chunks. TTFA ~4.4s for typical 3-sentence response (ASR 0.5s + prefill 1s + first sentence gen 2.5s + TTS 0.2s).
- Voice session lifecycle: starts on first button press, ends on 5-min idle timeout or farewell regex match. One active voice session; web UI concurrent per auth user. Interruption: long-press during TTS stops audio, new press during TTS replaces response (interrupted text marked as truncated in history, per LiveKit pattern).
- User personas: Primary User (full admin, voice+web), Household Member (Tier 0-1 auto, never sees config), Guest (Tier 0 only, no memory injection, no IoT, time-limited), Remote User (full access via authenticated web UI).
- Notification priority: P0 silent (LCD badge), P1 visual (LCD+LED), P2 chime (LCD+LED+tone), P3 spoken (waits for conversation end), P4 interruptive (immediate, safety-only). DND mode downgrades P3→P1. Notifications queued during active conversation (P0-P3).
- Scheduling service: SQLite-backed timers and reminders (data/schedules.db), asyncio scheduling, survives reboots. Snooze up to 3 times. Timer countdown shown on LCD idle screen.
- Health monitoring: 7 components polled at 5-60s intervals, metrics on ZeroMQ bus, /api/health endpoint (no auth on LAN). NPU thermal zones: <65°C normal, 65-75°C warn, 75-85°C throttle, >85°C emergency shutdown. Watchdog: systemd 30s, max 3 restarts in 5 min.
- Graceful degradation: LLM fail → regex-matched utility commands still work; TTS fail → LCD text; ASR fail → web UI text input; network down → transparent for local; battery <15% → reduce brightness; battery <5% → clean shutdown; storage full → disable logging/extraction.
- Industry comparison (Session 9): Cortex compared against Alexa, Google Home, Siri, Home Assistant Voice, OVOS, Willow, Pipecat, LiveKit Agents, Jan.ai, AnythingLLM, LangGraph, CrewAI, OpenAI Agents SDK. Architecture is solid; gaps were in moment-to-moment user experience (now addressed by DD-030-033).
- Second-pass gap analysis (Session 10): 12 gaps found comparing against 2025-2026 landscape and OpenClaw. 8 became design decisions (DD-034-041), 4 became Phase 0 investigation items (speculative decoding, constrained generation, Moonshine ASR, unified multimodal).
- Script-based tools (DD-050): Anthropic's Claude Skills architecture analysis revealed pattern directly applicable to Cortex. Skills = self-contained instruction folders (SKILL.md + scripts/ + references/). Key insight: MCP provides connectivity (what tools exist), skills/scripts provide workflow knowledge (how to use them). Progressive disclosure maps perfectly to 2,047-token budget — short descriptions always in context, full instructions only when tool selected, reference docs never in LLM context. Script-based tools complement Python handler classes: TOOL.yaml defines schema + optional `triggers` (regex for zero-LLM routing) + optional `keywords` (for pre-filtering large tool libraries), scripts/ provide deterministic execution via subprocess (JSON stdin/stdout). Auto-discovery: ToolRegistry scans `tools/*/TOOL.yaml` at startup + hot-reload — new tools available without code changes. Three routing paths: regex trigger (0 tokens), keyword pre-filter + LLM (~200-400 tokens), full LLM selection (~400-800 tokens). Phase 3: ToolRegistry loads script tools alongside Python tools. Phase 4: user-created script tools via tool development pipeline with bubblewrap sandbox.
- PTT-as-messaging insight: push-to-talk voice is fundamentally the same interaction pattern as messaging (OpenClaw-style). Users saying "What's on my calendar?" or "Send Sarah a message" expect it to work. Requires real service backends (CalDAV, IMAP, ntfy), not just LLM tool stubs.
- External services use Service Adapter Protocol pattern (same as Model Provider Layer): Python Protocol class, config-driven, default disabled, API keys in .env. Providers: CalDAV/Google/MCP for calendar, ntfy/Pushover/Matrix for messaging, IMAP/SMTP for email, CalDAV VTODO/Todoist for tasks.
- A2A protocol (v0.3, Google/Linux Foundation, 150+ orgs) is complementary to MCP: MCP provides tool/data access, A2A provides agent-to-agent task delegation. JSON-RPC over HTTP/SSE, same FastAPI infrastructure.
- Wyoming protocol: Home Assistant's standard for local voice satellites (JSONL over TCP). Exposes SenseVoice as STT provider and Kokoro as TTS provider to HA ecosystem. Python `wyoming` package (HA-maintained).
- Conversational clarification: confidence-gated orchestrator (threshold 0.6) asks for clarification instead of misrouting. Escalating repair ladder: rephrase question → offer options → explicit help request. Max 2 rounds per turn.
- Power-aware profiles: 4 tiers (mains/battery/low_battery/critical) auto-switch model, polling intervals, and display brightness based on PiSugar power state. Critical mode = regex-only, no LLM.
- NPU hardware abstraction: NpuService Protocol class with numpy I/O, no AXCL types at interface. Enables future HailoNpuService (Pi AI HAT+ 2) without changing higher layers.
- Web authentication (DD-042): Phase 1-2 no auth on LAN (trusted network). Phase 3: bcrypt-hashed password + secure HTTP-only session cookie, server-side in SQLite. Phase 3+ remote: HTTPS via Caddy reverse proxy, optional TOTP 2FA (pyotp). No JWT (overkill), no OAuth (unnecessary for self-hosted). Persona mapping: authenticated session → Primary/Remote User, unauthenticated LAN → Household Member (Tier 0-1), Guest → manual toggle. API: /api/health unauthenticated, all other endpoints require session or API key.
- Process & service architecture (DD-043): Single main process (cortex-core.service) runs Python asyncio/uvloop with FastAPI + agent framework + voice pipeline + scheduling + memory. Separate HAL processes: cortex-npu.service (AXCL runtime), cortex-audio.service (ALSA), cortex-display.service (LCD/buttons/LEDs). Optional cortex-wyoming.service. All IPC via ZeroMQ with JSON messages, topic convention {service}.{event_type}. Single main process minimizes RAM and IPC latency.
- Operational lifecycle (DD-044): Deployment via git clone + pip install -e . in virtualenv. Updates via scripts/update.sh (git pull + pip + restart). Lightweight SQL migration: numbered files in data/migrations/, schema_version table, applied on startup (no Alembic). Backup via scripts/backup.sh (tarball of data/ + config/ + .env, excludes models/). Logging: structlog JSON → stdout → systemd journal.
- Contact store: Local SQLite (data/contacts.db) backing contact_lookup cognitive tool. Schema: id, name, phone, email, notes, timestamps. Input via voice regex capture, web UI form (Phase 3), optional CardDAV sync (Phase 5). Privacy: local-only, never sent to cloud.
- Voice user identification limitation: Cortex does NOT perform speaker identification in Phases 1-5. All voice treated as Primary User unless Guest Mode manually activated. Household Member restrictions only via authenticated Web UI (Phase 3+). Multi-speaker voice ID is Phase 6+ stretch goal.
- Design audit findings (Session 11): 6 genuine gaps (auth, voice ID, contact store, Phase 0 tests, process architecture, ops lifecycle), 3 internal inconsistencies (missing DD-006-010, USB→CSI, IoT phase table), and several minor detail gaps. All addressed in v0.1.13.
- Phase readiness review (Session 11): Phase 0 guide missing peripheral tests (LCD, LEDs, button, speaker, standalone 1.7B). Phase 1 missing project scaffolding and MockNpuService for off-Pi dev. Phase 2 overloaded (15 items) — moved external services (DD-035) and A2A (DD-036) to Phase 3. All phases now have measurable exit criteria. Testing approach: pytest + MockNpuService + pre-commit hooks, no CI server. Scope doc v0.1.14.
- **Phase 0 hardware validation (Session 12):** All hardware tested and validated on Pi 5 (10.10.0.129). AXCL runtime installed (`sudo apt install axclhost`, package is `axclhost` not `axcl-smi`). PiSugar 3 Plus not physically connected (pogo pins not in contact) — pisugar-server disabled. All peripherals verified: LCD (ST7789 240x280 SPI, color cycling), RGB LEDs (PWM), button (active-HIGH), speaker (440Hz tone), microphone (record/playback). All 4 NPU models tested with measured benchmarks. Investigations: speculative decoding not supported by AXCL binary, constrained generation limited to stop tokens via post_config.json, Moonshine ASR not needed (SenseVoice has streaming axmodel), unified multimodal not needed (separate models more flexible). FastVLM-0.5B selected over SmolVLM2-500M (DD-045).
- **AXCL runtime gotchas (Phase 0):** Package name is `axclhost` (single package, not separate tools). DKMS builds 6 kernel modules. Tools at `/usr/bin/axcl/`. LLM inference requires separate tokenizer HTTP server on port 12345 (per-model Python script). HuggingFace CLI is now `hf` (not `huggingface-cli`) in huggingface_hub v1.5+. PEP 668 on Bookworm requires venv for pip packages (`~/.venvs/axllm/`). Some models only have AX650 native binaries (no AXCL aarch64 for Pi host) — must use Python pyaxengine path. Kokoro and FastVLM both require Python path; SenseVoice and Qwen3 have C++ AXCL aarch64 binaries.

## Open Questions (to resolve during Phase 0)
1. ~~Can SenseVoice + Qwen3-1.7B + Kokoro + VLM all co-reside in 8GB NPU CMM?~~ **Resolved (Phase 0 measured):** SenseVoice (251 MiB) + Qwen3-1.7B (3,375 MiB) + Kokoro (232 MiB) + FastVLM-0.5B (792 MiB) = ~4.95 GB, fits with 29.7% headroom.
2. NPU model hot-swap latency? (Not yet tested — requires loading/unloading under load)
3. ~~Wake word engine choice?~~ Resolved: removed entirely (DD-025). Button-only activation.
4. Need USB SSD for extended storage?
5. Enclosure design?
6. ~~PiSugar 3 Plus integration?~~ Deferred: hardware not physically connected (pogo pins). Service disabled. Will revisit when mechanically attached.

## File Structure
```
Cortex/
├── docs/design/             # Scope and architecture docs
├── docs/guides/             # Setup and operational guides
├── context/                 # This file and other context docs
├── src/cortex/              # Application source (~83 source files)
│   ├── config.py            # Pydantic config loading cortex.yaml
│   ├── cli.py               # Click CLI (cortex run/config/version)
│   ├── core/                # Main service orchestrator
│   │   └── service.py       # CortexService + run_cortex()
│   ├── hal/                 # Hardware Abstraction Layer
│   │   ├── protocols.py     # NpuService, AudioService, DisplayService, ButtonService
│   │   ├── types.py         # ModelHandle, InferenceIO, AudioData, DisplayState, etc.
│   │   ├── npu/             # NPU service (mock + real)
│   │   │   ├── mock.py      # MockNpuService (realistic timing, error injection)
│   │   │   ├── axcl.py      # AxclNpuService (Pi NPU, mixed invocation)
│   │   │   ├── main.py      # cortex-npu systemd entry point
│   │   │   └── runners/     # Per-model-type runners (llm, asr, tts, vlm)
│   │   ├── audio/           # Audio service (mock + ALSA)
│   │   │   ├── mock.py      # MockAudioService
│   │   │   ├── service.py   # AlsaAudioService (sounddevice)
│   │   │   └── main.py      # cortex-audio systemd entry point
│   │   └── display/         # Display, button, LED service
│   │       ├── mock.py      # MockDisplayService + MockButtonService
│   │       ├── service.py   # WhisplayDisplayService (ST7789 LCD)
│   │       ├── button.py    # ButtonStateMachine + GpioButtonService
│   │       ├── led.py       # GpioLedController (PWM)
│   │       └── main.py      # cortex-display systemd entry point
│   ├── voice/               # Voice pipeline
│   │   ├── types.py         # VoiceSession, ASRResult, LatencyMetrics, etc.
│   │   ├── pipeline.py      # VoicePipeline (button→ASR→LLM→TTS→speaker)
│   │   ├── sentence_detector.py # Streaming sentence boundary detection
│   │   └── metrics.py       # Latency metrics logging
│   ├── agent/               # Agent framework (Phase 2)
│   │   ├── types.py         # ToolCall, ToolResult, AgentResponse, IntentMatch
│   │   ├── protocols.py     # Tool, ActionHandler, AgentProcessor Protocols
│   │   ├── router.py        # IntentRouter (regex, zero-LLM cost)
│   │   ├── processor.py     # AgentProcessor (routes ASR→handler or LLM)
│   │   ├── action_engine.py # ActionEngine (permission-gated tool execution)
│   │   ├── scheduling.py    # SchedulingService (SQLite timers, reboot recovery)
│   │   ├── notifications.py # NotificationService (5-level priority, DND)
│   │   ├── health.py        # HealthMonitor (CPU/memory/storage/NPU)
│   │   └── tools/           # Tool registry + built-in tools
│   │       ├── registry.py  # ToolRegistry + ActionEngine
│   │       └── builtin/     # clock, calculator, system_info, timer, memory_tool
│   ├── reasoning/           # Reasoning core (Phase 2)
│   │   ├── types.py         # ToolSchema, ContextBudget, AssembledPrompt
│   │   ├── protocols.py     # ContextAssembler, ToolCallParser Protocols
│   │   ├── tool_parser.py   # HermesToolCallParser (<tool_call> XML extraction)
│   │   ├── context_assembler.py # Token-budgeted prompt building (P1-P7)
│   │   ├── token_counter.py # Word-based token estimator (~1.3x)
│   │   └── prompt_templates.py  # System prompt templates (Hermes format)
│   ├── security/            # Security layer (Phase 2)
│   │   ├── types.py         # PermissionTier, AuditEntry, ApprovalStatus
│   │   ├── protocols.py     # PermissionEngine, AuditLog Protocols
│   │   ├── permissions.py   # PermissionEngine (4-tier model)
│   │   ├── audit.py         # SqliteAuditLog (append-only)
│   │   └── approval.py      # ApprovalManager (button-driven approval)
│   ├── memory/              # Memory system (Phase 2)
│   │   ├── types.py         # MemoryEntry, MemoryCategory, ConversationSummary
│   │   ├── protocols.py     # MemoryStore, EmbeddingService Protocols
│   │   ├── store.py         # SqliteMemoryStore (conversations + facts + embeddings)
│   │   ├── embedding.py     # MockEmbeddingService (SHA-256 hash-seeded 384-dim)
│   │   ├── extraction.py    # MemoryExtractor (regex-based fact capture)
│   │   ├── retrieval.py     # MemoryRetriever (embed→search→format for context)
│   │   └── working.py       # WorkingMemory (wraps VoiceSession)
│   ├── ipc/                 # ZeroMQ message bus
│   │   ├── messages.py      # CortexMessage (JSON + ZMQ multipart)
│   │   └── bus.py           # MessageBus (pub/sub)
│   └── utils/               # Shared utilities
│       └── logging.py       # Centralized structlog configuration
├── tests/                   # Test suites (487 passing)
│   ├── unit/                # Off-Pi tests (475 tests)
│   ├── integration/         # Integration tests (12 tests — Phase 2 exit criteria)
│   └── hardware/            # Pi-only tests (17 tests, pytest -m hardware)
├── config/                  # Config files
│   ├── cortex.yaml.template # Config template
│   ├── prompts/             # System prompts
│   │   └── system_v1.txt    # Default voice assistant prompt
│   └── systemd/             # Service unit files
│       ├── cortex-core.service
│       ├── cortex-npu.service
│       ├── cortex-audio.service
│       ├── cortex-display.service
│       └── cortex.target
├── scripts/                 # Utility scripts
│   ├── dev-setup.sh
│   └── install-services.sh
├── Makefile                 # dev, lint, format, test, test-hw
├── models/                  # Local model storage (gitignored)
└── data/                    # Runtime data (gitignored)
```

## Conversation History Summary
- **Session 1 (2026-02-27):** Defined full project scope, hardware validation, 7-layer architecture, 4-tier security model, 6-phase implementation plan. Created scope document v0.1 and Phase 0 hardware setup guide. Decided on Python, local-first networking, tiered autonomy, general-purpose focus.
- **Session 2 (2026-02-27):** Created private GitHub repo (AndrewGraydon/Cortex). Evaluated MeloTTS vs Kokoro-82M for TTS — selected Kokoro (DD-011). Evaluated LCD display approaches — adapting whisplay-ai-chatbot Pillow+cairosvg renderer (DD-012). Deferred web UI framework choice to Phase 3 (DD-013). Revised NPU memory budget from ~4.8GB to ~4.25GB.
- **Session 3 (2026-02-27):** Refined agent architecture (Layer 4). Researched CAAL (single-agent, not multi-agent as expected), 8 agent frameworks (Qwen-Agent, smolagents, Swarm, ReAct, CrewAI, LangGraph, AutoGen), and 8 workflow engines (n8n, Node-RED, Temporal, Prefect, Windmill, Dagu, pypyr, custom). Designed 3-tier agent hierarchy: Orchestrator (classifier) → Super Agents (reasoning with cognitive tools) → Utility Agents (zero-LLM deterministic dispatch). Core principle: "unconstrained thinking, constrained acting." Custom Python action engine replaces n8n. Qwen-Agent used as library only for NousFnCallPrompt. Updated scope doc to v0.1.3 (DD-014 through DD-018).
- **Session 4 (2026-02-27):** Continued from Session 3. Added MCP protocol support — client discovers external tools, server exposes Cortex tools (DD-019). Added tiered VLM vision — SmolVLM2-500M always resident, hot-swap to larger VLMs, three image sources (DD-020). Redesigned interaction model to button-first — physical Pi uses Whisplay button (GPIO 11) with gesture recognition (hold=talk, double-click=camera, single-click=approve, long-press=deny, triple-click=menu), no VAD on Pi. Established Web UI parity principle: every physical capability has a software equivalent (DD-021). Updated scope doc to v0.1.6.
- **Session 5 (2026-02-27):** Added configurable model provider layer (DD-022). All model interactions (LLM, ASR, TTS, VLM) routed through provider-agnostic Protocol interfaces with 7 backend types (axcl, openai, anthropic, google, xai, ollama, openai_compatible). Per-profile provider chains with fallback and circuit breaker. Tool calling format auto-adapted per provider. Security layer updated for cloud provider network gating and data privacy controls. Default: fully offline (axcl only), cloud/remote opt-in. Updated scope doc to v0.1.7.
- **Session 6 (2026-02-27):** Five design corrections: (1) Camera service changed from USB/V4L2 to CSI/libcamera/picamera2 (DD-024). (2) SenseVoice ASR rationale documented — 10-20x faster than Whisper on NPU due to non-autoregressive architecture (DD-023). (3) Wake word removed entirely — unnecessary with button-first and no VAD (DD-025). (4) Context management simplified to provider-managed — no centralized budget scaling (DD-026). (5) Tool development pipeline added to Agent Factory — Specify→Develop→Review→Approve→Deploy lifecycle with promotion system (DD-027). Fixed stale Phase 1 (VAD→button, MeloTTS→Kokoro) and Phase 4 (wake word→tool pipeline) references. Updated scope doc to v0.1.8.
- **Session 7 (2026-02-27):** Designed complete conversation context and memory system (DD-028). Context Assembly Pipeline builds prompts in priority order with 7 tiers. Rolling conversation summary generated during TTS playback for 4K NPU coherence. Five memory tiers detailed: working (RAM), short-term (SQLite conversation summaries), long-term (sqlite-vec atomic facts with embeddings), episodic (events/outcomes), tool (filesystem). Post-session LLM-based extraction captures facts/events. Automatic semantic retrieval (~20-40ms, CPU-only embedding via all-MiniLM-L6-v2) injects relevant memories into every prompt. Cloud provider privacy: memories stripped unless allow_sensitive_data enabled. Updated scope doc to v0.1.9.
- **Session 8 (2026-02-27):** Confirmed NPU benchmarks from AXERA-TECH and M5Stack docs (DD-029). Qwen3-1.7B confirmed as primary: 7.38 tok/s, 3.3 GB CMM, 4K context. Qwen3-4B evaluated and rejected as primary: 3.65 tok/s, 6.2 GB CMM (fills NPU, only 691 MB remaining — can't co-reside with any model). Noted as future hot-swap option (Pulsar2 v4.2 required). Discovered AXERA-TECH catalog (148 models on HuggingFace) — broader than M5Stack's official list. Updated model allocation tables with confirmed benchmarks, corrected latency budget (7.38 tok/s, not 12-15). Added Qwen3-VL-4B-GPTQ-Int4 to vision hot-swap pool. Updated scope doc to v0.1.10.
- **Session 9 (2026-02-27):** Comprehensive industry comparison — evaluated Cortex design against commercial (Alexa, Google, Siri), open-source (Home Assistant Voice, OVOS, Willow, Pipecat, LiveKit), and framework (LangGraph, CrewAI, OpenAI Agents SDK) systems. Architecture found solid but user-facing interaction had gaps. Created 4 user personas (Primary User, Household Member, Guest, Remote User). Added DD-030: Voice interaction lifecycle (sessions, interruptions, error recovery, confirmations, capability discovery, persona guidelines). DD-031: Streaming voice pipeline (sentence-boundary TTS streaming, TTFA <5s target, NPU multiplexing). DD-032: Utility tools, scheduling & notifications (9 new cognitive tools, SQLite timer/reminder service, 5-level notification priority with DND). DD-033: System resilience & health monitoring (7-component monitoring, /api/health, thermal zones, watchdog, graceful degradation matrix). Updated phases 1-6 and success criteria. Updated scope doc to v0.1.11.

- **Session 10 (2026-03-02):** Second-pass gap analysis comparing Cortex v0.1.11 against 2025-2026 AI assistant landscape and OpenClaw. Found 12 gaps — 8 became design decisions, 4 became Phase 0 investigation items. Key user insight: PTT voice is fundamentally the same interaction pattern as messaging — when users say "What's on my calendar?" they expect it to work. Added DD-034: Conversational clarification & repair (confidence-gated orchestrator, slot filling, disambiguation, repair ladder). DD-035: External services integration / PIM (CalDAV calendar, ntfy/Pushover messaging, IMAP/SMTP email, task sync — new `pim` super agent). DD-036: A2A protocol support (client+server, complementary to MCP). DD-037: Wyoming protocol bridge (expose SenseVoice/Kokoro to Home Assistant). DD-038: Proactive intelligence engine (pattern detection, morning briefings, think loop). DD-039: Knowledge store & document RAG (sixth memory tier). DD-040: Power-aware operation profiles (4 tiers, auto-switching). DD-041: NPU hardware abstraction (NpuService Protocol, no AXCL at interface). Phase 0 investigations added: speculative decoding, constrained generation, Moonshine ASR, unified multimodal. Updated scope doc to v0.1.12.

- **Session 11 (2026-03-02):** Comprehensive design audit of v0.1.12 (44 DDs, 1849 lines). Found 6 genuine gaps, 3 internal inconsistencies, and several minor detail gaps. Fixed all inconsistencies: recovered missing DD-006–010 in §9 log, changed "USB camera" → "CSI camera" (2 locations), aligned IoT phase table with phase plan (MQTT/REST/HA → Phase 5, Matter/BLE → Future), corrected DD-015 "15 tok/s" → "7.38 tok/s", fixed HAL "gRPC or Unix socket" → "ZeroMQ". Added DD-042: Web authentication & session management (bcrypt + session cookie, phase-gated, persona mapping). DD-043: Process & service architecture (single main process + separate HAL services, ZeroMQ IPC). DD-044: Operational lifecycle (deployment, migration, backup/restore, logging). Added contact store spec, voice user identification limitation note. Updated Phase 0 guide with Tests 7-9 (Kokoro TTS, SmolVLM2-500M vision, CSI camera) and 4 investigation procedures (speculative decoding, constrained generation, Moonshine ASR, unified multimodal). Updated config template (auth details, contacts section, ZeroMQ topic convention). Updated scope doc to v0.1.13. Phase readiness review: added peripheral test procedures to Phase 0 guide (speaker, LCD, button, LEDs, standalone Qwen3-1.7B). Added project scaffolding and MockNpuService to Phase 1. Rebalanced Phase 2→3: moved external services (DD-035) and A2A (DD-036) from Phase 2 to Phase 3 (reduces Phase 2 from 15→12 items). Added measurable exit criteria for all 7 phases. Added §6.2 Testing Approach (pytest, MockNpuService, per-phase expectations). Updated scope doc to v0.1.14.

- **Session 12 (2026-03-02):** Phase 0 hardware validation — complete. Installed AXCL runtime. Verified all peripherals and all 4 NPU models. Total 4-model co-resident: ~4.95 GB (29.7% headroom). Added DD-045. Updated scope to v0.1.15.

- **Session 13 (2026-03-02):** Phase 1 begun — Milestones 1.1, 1.2, 2.1 complete (scaffolding, types/protocols, MockNpuService). 68 tests passing.

- **Session 14 (2026-03-02):** Completed all four Pi hardware investigations (0A-0D). DD-046 (mixed NPU invocation), DD-047 (2,047 token hard limit), DD-048 (NPU multiplexing ~0ms switch), DD-049 (audio via sounddevice). Updated scope to v0.1.16.

- **Session 15 (2026-03-02):** Phase 1 completed — all milestones 4.1-4.4 built, tested, verified. 121 unit tests passing. All 6 exit criteria met.

- **Session 16 (2026-03-02):** Phase 1 hardware validation on Pi. Pushed code to Pi, ran all 121 unit tests (pass). Fixed 3 critical hardware issues: **(1) Button GPIO thread-safety:** RPi.GPIO fires callbacks on background thread with no event loop — `asyncio.ensure_future()` failed. Fixed `ButtonStateMachine._schedule()` to detect calling context and use `run_coroutine_threadsafe()` from GPIO threads. **(2) ASR provider mismatch:** SenseVoice defaults to `AxEngineExecutionProvider` but AXCL runtime has `AXCLRTExecutionProvider`. Fixed asr.py to auto-detect providers. **(3) Audio capture device [ROOT CAUSE]:** Using `hw:0,0` with `channels=1` produced garbage — WM8960 hardware requires 2-channel capture. Changed `DEFAULT_CAPTURE_DEVICE` from `hw:0,0` to `default`, which routes through ALSA `plug→dsnoop` chain in `/etc/asound.conf`. Confirmed with whisplay-ai-chatbot reference (same approach). Tuned mixer: Capture=55/63, Boost=2(+20dB), ALC=OFF, HPF=on, NoiseGate=on. DC offset removal in software. **End-to-end ASR verified:** Captured speech → SenseVoice NPU transcription = "This is a test." in 0.17s. Audio quality confirmed sufficient for ASR. Updated DD-049, scope doc to v0.1.17.

- **Session 17 (2026-03-03):** Phase 2 — Agent Core — COMPLETE. All 8 milestones (2.1-2.8) implemented in a single marathon session. **Milestone 2.1:** Foundation types and protocols — ToolCall, ToolResult, AgentResponse, IntentMatch, RoutingDecision; Tool, ActionHandler, AgentProcessor Protocol interfaces; PermissionTier, AuditEntry, ApprovalStatus; MemoryEntry, MemoryCategory; ToolSchema, ContextBudget, AssembledPrompt; AgentConfig, SecurityConfig, MemoryConfig Pydantic models. **Milestone 2.2:** Permission engine (4-tier: SAFE auto, NORMAL logged, RISKY button approval, DANGER requires confirmation) + SQLite append-only audit log + ApprovalManager (button-driven, SINGLE_CLICK=approve, LONG_PRESS=deny, timeout=deny). **Milestone 2.3:** HermesToolCallParser (extracts `<tool_call>` XML from Qwen3 output, handles malformed JSON), ContextAssembler (token-budgeted P1-P7 priority prompt building within 2,047 limit), word-based token estimator (~1.3x word count). **Milestone 2.4:** 5 built-in tools (clock, calculator, system_info, timer_set/query, memory_save/query), ToolRegistry, ActionEngine with permission gating and audit logging. Calculator uses safe AST evaluation. **Milestone 2.5:** IntentRouter (regex patterns for known intents — zero LLM cost) + AgentProcessor (routes ASR text to utility handler or LLM). Wired into VoicePipeline. Added `set_asr_text()` to MockNpuService for pipeline tests. **Milestone 2.6:** SqliteMemoryStore (conversations + facts + brute-force numpy cosine similarity embedding search), MockEmbeddingService (SHA-256 hash-seeded deterministic 384-dim vectors), MemoryExtractor (regex patterns: "remember that...", "my name is...", "I live in..."), MemoryRetriever (embed query → search → format as [Memory] block for P4 injection), WorkingMemory (wraps VoiceSession). Memory tools wired to real backend via `set_memory_backend()`. **Milestone 2.7:** SchedulingService (SQLite-persisted timers, asyncio scheduling, reboot recovery — fires past-due timers on startup), NotificationService (5-level P0-P4 priority queue, DND mode, session-aware queueing — P4 always interrupts, P0-P3 queued during voice sessions). **Milestone 2.8:** HealthMonitor (CPU/memory/storage/NPU health checks, overall status computation), integration tests verifying all 6 exit criteria. **Testing:** 487 unit + integration tests passing on dev machine. Full suite run on Pi: 497 passed (including 10 peripheral hardware tests), 7 expected failures (6 NPU context tests needing AXCL init, 1 button press timeout — nobody pressed it). Zero Phase 2 regressions. Lint (ruff) + mypy strict clean throughout. Updated scope doc to v0.1.18.

- **Session 18 (2026-03-03):** Pre-Phase 3 analysis. Reviewed Anthropic's "Complete Guide to Building Skills for Claude" PDF — comprehensive architecture for instruction-based tool enhancement. Identified strong parallels with Cortex: progressive disclosure maps to 2,047-token context budget (P1-P7), MCP+Skills pattern maps to MCP+action templates, 5 skill patterns (sequential workflow, multi-MCP coordination, iterative refinement, context-aware selection, domain-specific intelligence) map to agent hierarchy. Added DD-050: Script-based tools with progressive disclosure — self-contained TOOL.yaml + scripts/ folders as alternative to Python handler classes. Updated scope doc §4.4.5 (Action Engine) with full script tool specification, §4.4.7 (Tool Development Pipeline) to support both Python and script formats, Phase 3 deliverables (script tool loader + MCP workflow templates), Phase 4 deliverables (user-created script tools + bubblewrap sandbox + new exit criterion). Updated scope doc to v0.1.19.

### NEXT SESSION — Resume Here
**Topic:** Phase 3 — Web UI begins.
- Web UI framework decision needed (DD-013): HTMX+DaisyUI vs NiceGUI vs Svelte
- FastAPI backend + WebSocket streaming for chat
- Authentication system (bcrypt + session cookies, DD-042)
- Script-based tool loader for ToolRegistry (DD-050)
- YAML workflow templates for MCP tool orchestration (DD-050)
- External services: CalDAV calendar, IMAP/SMTP email, ntfy messaging (DD-035)
- A2A protocol: client discovery + server Agent Card (DD-036)

---

*To resume a design session, share this file and state which phase/layer you want to work on.*
