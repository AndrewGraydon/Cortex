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
3. **Reasoning Core** — Qwen3-VL-2B with tool calling + vision
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
- **Primary VLM:** Qwen3-VL-2B (on NPU, text + vision)
- **Target OS:** Debian 12 (Bookworm) / Raspberry Pi OS

## Documentation

- [Scope Document](docs/design/scope-v0.1.md)
- [Phase 0 Setup Guide](docs/guides/phase-0-hardware-setup.md)
- [Project Context](context/project-context.md)
