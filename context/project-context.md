# Project Cortex — AI Assistant Context File
# Last updated: 2026-02-27 (Session 8)

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
- **TTS:** Kokoro-82M (selected), MeloTTS, CosyVoice2
- **Vision:** YOLO11, Depth-Anything-V2, Real-ESRGAN
- **Other:** CLIP, 3D-Speaker-MT, LivePortrait, Stable Diffusion 1.5

### NPU Performance (confirmed benchmarks on M.2 + Pi 5)
- Qwen3-0.6B (w8a16): 12.88 tok/s, ~2.0 GB CMM
- Qwen3-1.7B (w8a16): **7.38 tok/s**, ~3.3 GB CMM, ~4K context
- Qwen3-4B (w8a16): 3.65 tok/s, ~6.2 GB CMM (691 MB remaining — can't co-reside), max 2,559 tokens
- Qwen3-VL-2B (w8a16): 7.80 tok/s, ~3.7 GB CMM
- SenseVoice RTF: ~0.015 (67x faster than real-time)
- Source: [AXERA-TECH HuggingFace](https://huggingface.co/AXERA-TECH) (148 models total), [M5Stack NPU Benchmark](https://docs.m5stack.com/en/guide/ai_accelerator/llm-8850/m5_llm_8850_npu_benchmark)

## Design Decisions Made

| ID | Decision | Rationale |
|---|---|---|
| DD-001 | Python 3.11+ as primary language | AXCL Python bindings, ML ecosystem |
| DD-002 | Local-first with optional secure external | Privacy + flexibility |
| DD-003 | 4-tier permission model | Tiered autonomy: safe=auto, risky=approval |
| DD-004 | General-purpose assistant | No premature domain optimization |
| DD-005 | Qwen3-1.7B primary model | Confirmed: 7.38 tok/s, 3.3 GB CMM, 4K context. Qwen3-4B rejected (3.65 tok/s, 6.2 GB fills NPU). See DD-029. |
| DD-006 | FastAPI + HTMX for web UI | Lightweight, async, server-driven |
| DD-007 | SQLite + sqlite-vec for memory | No separate DB server, vector search support |
| DD-008 | ZeroMQ for IPC | Fast, brokerless, simple |
| DD-009 | bubblewrap for sandboxing | Lightweight, no daemon, fine-grained |
| DD-010 | systemd for service management | Standard, watchdog, dependencies |
| DD-011 | Kokoro-82M as TTS engine | 2x faster than MeloTTS on NPU, #1 TTS Arena quality, 237MB NPU, already proven on LLM-8850 |
| DD-012 | Adapt whisplay-ai-chatbot for LCD | Proven Pillow+cairosvg renderer on this hardware; 30 FPS, SVG emoji, smooth scrolling |
| DD-013 | Defer web UI framework to Phase 3 | Voice-first; evaluate HTMX+DaisyUI vs NiceGUI vs Svelte later |
| DD-014 | Custom Python action engine | Zero RAM, in-process, YAML templates + Python handlers; n8n/Node-RED/Temporal too heavy |
| DD-015 | 3-tier agent hierarchy | Orchestrator (~370 tok) → Super Agents (4K context) → Utility Agents (0 LLM tokens) |
| DD-016 | Unconstrained thinking, constrained acting | Free reasoning with cognitive tools; actions through pre-authorized templates |
| DD-017 | Qwen-Agent as library only | NousFnCallPrompt for Qwen3-native tool-call parsing |
| DD-018 | Custom framework over CrewAI/LangGraph/AutoGen | All too heavy/bloated for Pi 5 + 1.7B model constraints |
| DD-019 | MCP protocol support (client + server) | Standard tool interop; external tools mapped to cognitive tools or action templates with permission gating |
| DD-020 | Tiered VLM vision system | SmolVLM2-500M always resident; hot-swap to InternVL3-1B/Qwen2.5-VL-3B for detail; camera + webcam + upload |
| DD-021 | Button-first interaction with Web UI parity | Physical Pi uses Whisplay button (GPIO 11) as sole input via gestures (hold/double-click/single-click/long-press/triple-click); no VAD anywhere; Web UI has full parity via software equivalents |
| DD-022 | Configurable model provider layer | All model interactions via provider-agnostic Protocol interfaces; 7 providers (axcl, openai, anthropic, google, xai, ollama, openai_compatible); per-profile provider chains with fallback; tool calling auto-adapted; default offline, cloud opt-in |
| DD-023 | SenseVoice-Small as ASR engine | Non-autoregressive (single-pass) — 50-75ms per utterance vs Whisper-Small 800-1800ms (autoregressive). 10-20x faster on same NPU. Comparable accuracy for English. Faster Whisper can't use NPU (CPU-only via CTranslate2). Both to be tested Phase 0. |
| DD-024 | CSI camera via libcamera/picamera2 | Freenove camera module uses CSI connector, not USB. picamera2 is the standard Pi camera interface. |
| DD-025 | No wake word — button-only activation | With button-first (DD-021) and no VAD, wake word serves no purpose. Removed entirely. No always-on mic, no background audio processing. |
| DD-026 | Provider-managed context | No centralized context budget scaling. Each provider knows its own limits; agent framework passes full ideal prompt, provider handles truncation. Simplifies architecture. |
| DD-027 | Tool development pipeline | Structured lifecycle: Specify → Develop → Review → Approve → Deploy. Tools start at Tier 2, promote after supervised use. Sandbox testing, version control, rollback. |
| DD-028 | Context assembly & memory system | Context Assembler builds prompts in priority order (system → request → tools → memories → summary → history). Rolling summary during TTS playback for 4K NPU coherence. 5 memory tiers with post-session LLM extraction. Automatic semantic retrieval (~20-40ms, CPU embedding) injects memories into prompts. all-MiniLM-L6-v2 + sqlite-vec. |
| DD-029 | Qwen3-1.7B confirmed, 4B rejected | Confirmed benchmarks: 1.7B = 7.38 tok/s, 3.3 GB CMM. 4B = 3.65 tok/s, 6.2 GB (fills NPU, can't co-reside with anything). 4B as future hot-swap only. AXERA-TECH catalog (148 models) noted for Phase 0 evaluation. |

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
- **Phase 0** — Hardware foundation (CURRENT)
- **Phase 1** — Voice loop (button activation + ASR + LLM + TTS end-to-end)
- **Phase 2** — Agent core (tools, permissions, audit, sandbox)
- **Phase 3** — Web UI
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
- Kokoro-82M TTS: RTF 0.067 on AX8850 (15x real-time), 237MB CMM, hybrid pipeline (3 axmodel NPU + ONNX vocoder CPU)
- Kokoro proven on LLM-8850: see https://github.com/AndrewGraydon/kokoro.LM8850
- Confirmed NPU memory budget: SenseVoice (~500MB) + Qwen3-1.7B (~3.3GB) + Kokoro (~237MB) + SmolVLM2-500M (~500MB) = ~4.5GB of 7.0GB (fits with ~2.5GB headroom). Qwen3-4B rejected — 6.2GB fills NPU, can't co-reside with any other model.
- whisplay-ai-chatbot LCD architecture: TypeScript brain + Python display over TCP socket; Pillow + cairosvg rendering at 30 FPS; SPI at 100MHz; SVG emoji, LANCZOS resampling, line caching
- Cortex will adapt this approach, replacing TCP socket IPC with ZeroMQ to match the rest of the stack
- CAAL (CoreWorxLab) is a single-agent voice pipeline, not a multi-agent framework — but the concept of separating reasoning from action execution via pre-defined workflows is sound
- Agent framework research (8 frameworks evaluated): CrewAI (32GB RAM, ChromaDB dep), AutoGen (conversation paradigm fills 4K in 2-3 turns), LangGraph (closest match but langchain-core bloat), smolagents (prompt bloat), Swarm (deprecated), Qwen-Agent (best for tool-call parsing only), ReAct (reasoning overhead for 1.7B)
- Workflow engine research (8 engines): n8n (200-860MB), Node-RED (40-80MB+leaks), Temporal (2-4GB), Prefect (500MB+), Windmill (no ARM64), Dagu (Go binary), pypyr (right pattern). All external engines too heavy for Pi — custom in-process Python action engine selected
- Token budgets for 4K context: Orchestrator ~370 tokens (single classifier call), Super Agent ~4000 tokens (200 system + 150 tools + 3600 working), Utility Agent 0 tokens (deterministic)
- MCP (Model Context Protocol) supported via Python `mcp` SDK: client mode discovers tools from external servers (HA, n8n), server mode exposes Cortex tools to external AI clients; Streamable HTTP transport on existing FastAPI server
- Tiered VLM vision: SmolVLM2-500M always resident (~500MB, total NPU ~4.75GB); hot-swap to InternVL3-1B or Qwen2.5-VL-3B for detailed analysis (unloads LLM temporarily, voice pipeline pauses). Three image sources: CSI camera via picamera2 (physical Pi), webcam (web UI), file upload (web UI)
- Whisplay HAT button hardware: single button on GPIO 11 (active low), 50ms debounce. RGB LEDs on GPIO 22/18/16. Same physical design as whisplay-ai-chatbot.
- Button-first interaction: hold=push-to-talk (record while held, ASR on release), double-click=camera capture+VLM, single-click=approve/confirm, long-press=deny/cancel, triple-click=system menu. No VAD anywhere — both Pi and Web UI use explicit button control for recording boundaries.
- Web UI parity: every physical Pi capability has a software equivalent — record button (hold-to-talk or click-start/click-stop), webcam/upload for vision, approve/deny buttons for Tier 2/3, status indicator for LED state.
- Model Provider Layer: provider-agnostic Protocol interfaces for LLM, ASR, TTS, VLM. Seven providers: axcl (local NPU), openai, anthropic, google, xai, ollama, openai_compatible. Per-profile provider chains with fallback and circuit breaker. Tool calling format auto-adapted per provider (NousFnCallPrompt for Qwen3, OpenAI function calling for cloud, etc.). Context is provider-managed — each provider handles its own limits, no centralized budget scaling. API keys in .env, cloud calls gated by security layer with auto nftables management. Default: fully offline (axcl only).
- SenseVoice-Small ASR: non-autoregressive single-pass inference, 50-75ms per utterance on NPU (10-20x faster than Whisper-Small's 800-1800ms autoregressive decoding). Comparable English accuracy. Faster Whisper cannot use NPU (CPU-only via CTranslate2).
- Tool development pipeline: Specify → Develop → Review → Approve → Deploy lifecycle. Tools start at Tier 2, promote to Tier 1/0 after supervised successful executions. Sandbox testing via bubblewrap, version-controlled with rollback.
- Context Assembly Pipeline: prompts built in priority order (P1 system → P2 request → P3 tools → P4 auto-injected memories → P5 rolling summary → P6 recent turns → P7 older history). On 4K local NPU: ~200+150+150+200+150+400 = ~1,250 tok overhead, leaving ~2,750 for generation. Cloud providers skip summary, include full history.
- Rolling conversation summary: generated during TTS playback (NPU idle), ~100 tokens, updated every 3 exchanges. Hides latency. Abandoned if user interrupts — fallback to raw recent turns. Not required for correctness.
- Memory extraction: post-session LLM call extracts atomic facts + events from conversation summary → embeds on CPU → stores in sqlite-vec. Dedup via cosine similarity > 0.85. Also: regex-based in-conversation capture for explicit "remember..." requests.
- Embedding model: all-MiniLM-L6-v2 via ONNX Runtime on CPU (~22MB, 384-dim, ~10-20ms/embed). sqlite-vec brute-force KNN sufficient for <50K entries. NPU reserved for LLM/ASR/TTS.

## Open Questions (to resolve during Phase 0)
1. ~~Can SenseVoice + Qwen3-1.7B + Kokoro + SmolVLM2 all co-reside in 8GB NPU CMM?~~ Resolved: budget is ~4.75GB, fits with ~2.3GB headroom.
2. NPU model hot-swap latency?
3. ~~Wake word engine choice?~~ Resolved: removed entirely (DD-025). Button-only activation.
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
- **Session 2 (2026-02-27):** Created private GitHub repo (AndrewGraydon/Cortex). Evaluated MeloTTS vs Kokoro-82M for TTS — selected Kokoro (DD-011). Evaluated LCD display approaches — adapting whisplay-ai-chatbot Pillow+cairosvg renderer (DD-012). Deferred web UI framework choice to Phase 3 (DD-013). Revised NPU memory budget from ~4.8GB to ~4.25GB.
- **Session 3 (2026-02-27):** Refined agent architecture (Layer 4). Researched CAAL (single-agent, not multi-agent as expected), 8 agent frameworks (Qwen-Agent, smolagents, Swarm, ReAct, CrewAI, LangGraph, AutoGen), and 8 workflow engines (n8n, Node-RED, Temporal, Prefect, Windmill, Dagu, pypyr, custom). Designed 3-tier agent hierarchy: Orchestrator (classifier) → Super Agents (reasoning with cognitive tools) → Utility Agents (zero-LLM deterministic dispatch). Core principle: "unconstrained thinking, constrained acting." Custom Python action engine replaces n8n. Qwen-Agent used as library only for NousFnCallPrompt. Updated scope doc to v0.1.3 (DD-014 through DD-018).
- **Session 4 (2026-02-27):** Continued from Session 3. Added MCP protocol support — client discovers external tools, server exposes Cortex tools (DD-019). Added tiered VLM vision — SmolVLM2-500M always resident, hot-swap to larger VLMs, three image sources (DD-020). Redesigned interaction model to button-first — physical Pi uses Whisplay button (GPIO 11) with gesture recognition (hold=talk, double-click=camera, single-click=approve, long-press=deny, triple-click=menu), no VAD on Pi. Established Web UI parity principle: every physical capability has a software equivalent (DD-021). Updated scope doc to v0.1.6.
- **Session 5 (2026-02-27):** Added configurable model provider layer (DD-022). All model interactions (LLM, ASR, TTS, VLM) routed through provider-agnostic Protocol interfaces with 7 backend types (axcl, openai, anthropic, google, xai, ollama, openai_compatible). Per-profile provider chains with fallback and circuit breaker. Tool calling format auto-adapted per provider. Security layer updated for cloud provider network gating and data privacy controls. Default: fully offline (axcl only), cloud/remote opt-in. Updated scope doc to v0.1.7.
- **Session 6 (2026-02-27):** Five design corrections: (1) Camera service changed from USB/V4L2 to CSI/libcamera/picamera2 (DD-024). (2) SenseVoice ASR rationale documented — 10-20x faster than Whisper on NPU due to non-autoregressive architecture (DD-023). (3) Wake word removed entirely — unnecessary with button-first and no VAD (DD-025). (4) Context management simplified to provider-managed — no centralized budget scaling (DD-026). (5) Tool development pipeline added to Agent Factory — Specify→Develop→Review→Approve→Deploy lifecycle with promotion system (DD-027). Fixed stale Phase 1 (VAD→button, MeloTTS→Kokoro) and Phase 4 (wake word→tool pipeline) references. Updated scope doc to v0.1.8.
- **Session 7 (2026-02-27):** Designed complete conversation context and memory system (DD-028). Context Assembly Pipeline builds prompts in priority order with 7 tiers. Rolling conversation summary generated during TTS playback for 4K NPU coherence. Five memory tiers detailed: working (RAM), short-term (SQLite conversation summaries), long-term (sqlite-vec atomic facts with embeddings), episodic (events/outcomes), tool (filesystem). Post-session LLM-based extraction captures facts/events. Automatic semantic retrieval (~20-40ms, CPU-only embedding via all-MiniLM-L6-v2) injects relevant memories into every prompt. Cloud provider privacy: memories stripped unless allow_sensitive_data enabled. Updated scope doc to v0.1.9.
- **Session 8 (2026-02-27):** Confirmed NPU benchmarks from AXERA-TECH and M5Stack docs (DD-029). Qwen3-1.7B confirmed as primary: 7.38 tok/s, 3.3 GB CMM, 4K context. Qwen3-4B evaluated and rejected as primary: 3.65 tok/s, 6.2 GB CMM (fills NPU, only 691 MB remaining — can't co-reside with any model). Noted as future hot-swap option (Pulsar2 v4.2 required). Discovered AXERA-TECH catalog (148 models on HuggingFace) — broader than M5Stack's official list. Updated model allocation tables with confirmed benchmarks, corrected latency budget (7.38 tok/s, not 12-15). Added Qwen3-VL-4B-GPTQ-Int4 to vision hot-swap pool. Updated scope doc to v0.1.10.

### NEXT SESSION — Resume Here
**Topic:** TBD — discuss with user. Possible next topics:
- **Phase 0 hardware setup:** Begin actual hardware assembly and driver validation on the Pi 5
- **Detailed action template design:** Flesh out the built-in action templates for Phase 2
- **Security layer deep-dive:** Ensure §4.5 security architecture aligns with action engine and tool pipeline
- **Display UI deep-dive:** Detail the LCD render pipeline, display state machine, and status screen layouts
- **Super agent YAML definitions:** Draft the initial agent config files for `config/agents/`

---

*To resume a design session, share this file and state which phase/layer you want to work on.*
