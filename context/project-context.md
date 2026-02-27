# Project Cortex — AI Assistant Context File
# Last updated: 2026-02-27 (Session 2)

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
| DD-011 | Kokoro-82M as TTS engine | 2x faster than MeloTTS on NPU, #1 TTS Arena quality, 237MB NPU, already proven on LLM-8850 |
| DD-012 | Adapt whisplay-ai-chatbot for LCD | Proven Pillow+cairosvg renderer on this hardware; 30 FPS, SVG emoji, smooth scrolling |
| DD-013 | Defer web UI framework to Phase 3 | Voice-first; evaluate HTMX+DaisyUI vs NiceGUI vs Svelte later |

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
- Kokoro-82M TTS: RTF 0.067 on AX8850 (15x real-time), 237MB CMM, hybrid pipeline (3 axmodel NPU + ONNX vocoder CPU)
- Kokoro proven on LLM-8850: see https://github.com/AndrewGraydon/kokoro.LM8850
- Revised NPU memory budget: SenseVoice (~500MB) + Qwen3-1.7B (~3.5GB) + Kokoro (~237MB) = ~4.25GB (fits with ~3.5GB headroom)
- whisplay-ai-chatbot LCD architecture: TypeScript brain + Python display over TCP socket; Pillow + cairosvg rendering at 30 FPS; SPI at 100MHz; SVG emoji, LANCZOS resampling, line caching
- Cortex will adapt this approach, replacing TCP socket IPC with ZeroMQ to match the rest of the stack

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
- **Session 2 (2026-02-27):** Created private GitHub repo (AndrewGraydon/Cortex). Evaluated MeloTTS vs Kokoro-82M for TTS — selected Kokoro (DD-011). Evaluated LCD display approaches — adapting whisplay-ai-chatbot Pillow+cairosvg renderer (DD-012). Deferred web UI framework choice to Phase 3 (DD-013). Revised NPU memory budget from ~4.8GB to ~4.25GB.

---

*To resume a design session, share this file and state which phase/layer you want to work on.*
